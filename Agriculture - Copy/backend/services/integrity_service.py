"""Serve the provenance-calibrated estimate from the running application.

This wraps :mod:`backend.integrity.engine` so that a live farm request is
processed through the same path that was validated, and so that the inputs
actually used are recorded in a ledger entry rather than described in prose.

The calibration store is a build artefact. It is produced by

    python3 -m backend.validation.experiments

which populates it by degrading held-out seasons through the fallback chain.
When that artefact is absent the service refuses to invent an interval and
reports the pooled baseline with an explicit notice that no provenance
partition is available, rather than presenting a heuristic widening as a
calibrated one.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from backend.config import BASE_DIR, TRAINING_DATA_FILE, WEATHER_HISTORICAL_FILE
from backend.integrity.calibration import CalibrationStore, PooledBaselineStore, QualityKey
from backend.integrity.engine import (
    InferenceState,
    IntegrityEngine,
    fit_correction_model,
)
from backend.integrity.ledger import InferenceLedger
from backend.integrity.provenance import SourceCategory
from backend.integrity.thermal_time import (
    DEFAULT_BASE_TEMPS,
    accumulate_gdd,
    persistence_skill_curve,
    prepare_seasons,
    thermal_time_expectation_prepared,
)
from backend.integrity.vegetation import LadderSample, support_stability

CALIBRATION_ARTEFACT = BASE_DIR / "validation_results" / "calibration_store.json"

SEASON_RANGES = {
    "Kharif": lambda y: (f"{y}-06-01", f"{y}-10-31"),
    "Rabi": lambda y: (f"{y}-11-01", f"{y+1}-03-31"),
    "Whole Year": lambda y: (f"{y}-01-01", f"{y}-12-31"),
    "Summer": lambda y: (f"{y}-03-01", f"{y}-06-15"),
    "Autumn": lambda y: (f"{y}-08-01", f"{y}-11-30"),
    "Winter": lambda y: (f"{y}-11-01", f"{y+1}-02-28"),
}


class CalibrationArtefactMissing(RuntimeError):
    pass


class IntegrityService:
    def __init__(self) -> None:
        self._store: Optional[CalibrationStore] = None
        self._skill_curve: Optional[Dict[int, float]] = None
        self._archive: Optional[pd.DataFrame] = None
        self._seasons: Optional[List[dict]] = None
        self.ledger = InferenceLedger()

    # -- lazily built build-time state -----------------------------------
    @property
    def archive(self) -> pd.DataFrame:
        if self._archive is None:
            frame = pd.read_csv(WEATHER_HISTORICAL_FILE)
            frame["date"] = pd.to_datetime(frame["date"])
            self._archive = frame.sort_values("date").reset_index(drop=True)
        return self._archive

    @property
    def skill_curve(self) -> Dict[int, float]:
        if self._skill_curve is None:
            self._skill_curve = persistence_skill_curve(self.archive, horizons=[1, 3, 5, 7, 10, 14, 16, 21])
        return self._skill_curve

    def historical_seasons(self) -> List[dict]:
        if self._seasons is None:
            df = pd.read_csv(TRAINING_DATA_FILE)
            seasons: List[dict] = []
            seen = set()
            for _, row in df.iterrows():
                key = (int(row["Crop_Year"]), row["Season"])
                if key in seen or row["Season"] not in SEASON_RANGES:
                    continue
                seen.add(key)
                start, end = SEASON_RANGES[row["Season"]](int(row["Crop_Year"]))
                window = self.archive[(self.archive["date"] >= start) & (self.archive["date"] <= end)]
                if len(window) < 30:
                    continue
                seasons.append({"year": int(row["Crop_Year"]), "daily": window.reset_index(drop=True)})
            self._seasons = seasons
        return self._seasons

    def store(self) -> CalibrationStore:
        if self._store is not None:
            return self._store
        if not CALIBRATION_ARTEFACT.exists():
            raise CalibrationArtefactMissing(
                f"{CALIBRATION_ARTEFACT.name} not found. Build it with "
                "`python3 -m backend.validation.experiments`. Without it there are no "
                "residuals for any provenance partition, and any interval produced would be "
                "an unvalidated widening."
            )
        payload = json.loads(CALIBRATION_ARTEFACT.read_text())
        store = CalibrationStore(
            alpha=payload.get("alpha", 0.10),
            min_partition=payload.get("min_partition", 20),
            inflation=payload.get("inflation", 1.35),
        )
        for label, values in payload["partitions"].items():
            weather, veg, conflict = _parse_label(label)
            key = QualityKey(weather, veg, conflict)
            for value in values:
                store.add(key, value)
        self._store = store
        return store

    def correction_model(self):
        payload = json.loads(CALIBRATION_ARTEFACT.read_text())
        fitted = payload["correction"]
        return fit_correction_model(
            payload["fit_relative_residuals"],
            payload["fit_anomalies"],
            ridge=payload.get("ridge", 1.0),
            alpha=payload.get("bound_alpha", 0.01),
        )

    # -- live inference ---------------------------------------------------
    def build_state(
        self,
        *,
        crop: str,
        season: str,
        base_prediction: float,
        base_model_version: str,
        observed_daily: pd.DataFrame,
        forecast_daily: pd.DataFrame,
        weather_category: SourceCategory,
        weather_age_days: float,
        forecast_horizon_days: Optional[int],
        vegetation_deviation: Optional[float] = None,
        ladder_samples: Optional[List[LadderSample]] = None,
        valid_pixel_pct: Optional[float] = None,
        vegetation_age_days: Optional[float] = None,
        inference_id: Optional[str] = None,
    ) -> InferenceState:
        base_temp = DEFAULT_BASE_TEMPS.get(crop, 10.0)
        prepared = prepare_seasons(self.historical_seasons(), base_temp)
        return InferenceState(
            inference_id=inference_id or f"{crop}|{season}|{datetime.now(timezone.utc).date()}",
            crop=crop,
            season=season,
            crop_year=int(datetime.now(timezone.utc).year),
            base_prediction=float(base_prediction),
            base_model_version=base_model_version,
            observed_daily=observed_daily,
            forecast_daily=forecast_daily,
            historical_seasons=self.historical_seasons(),
            weather_category=weather_category,
            vegetation_deviation=vegetation_deviation,
            ladder_samples=ladder_samples,
            valid_pixel_pct=valid_pixel_pct,
            weather_age_days=weather_age_days,
            vegetation_age_days=vegetation_age_days,
            forecast_horizon_days=forecast_horizon_days,
            prepared_seasons=prepared,
        )

    def infer(self, state: InferenceState) -> Dict:
        engine = IntegrityEngine(
            self.correction_model(),
            self.store(),
            skill_curve=self.skill_curve,
            ledger=self.ledger,
        )
        result = engine.infer(state)
        payload = result.to_dict()
        payload["ledger_head"] = self.ledger.head
        payload["ledger_entries"] = len(self.ledger.entries)
        payload["base_model_unchanged"] = True
        return payload

    def chain_status(self) -> Dict:
        return self.ledger.verify()


def _parse_label(label: str):
    """Inverse of QualityKey.label, tolerating the wildcard strata."""

    parts = label.split("|")
    if len(parts) != 3:
        return ("live", "high", "clean")
    weather = parts[0][1:]
    veg = parts[1][1:]
    conflict = parts[2][1:]
    if "*" in (weather, veg, conflict):
        return ("live", "high", "clean")
    return (weather, veg, conflict)


integrity_service = IntegrityService()
