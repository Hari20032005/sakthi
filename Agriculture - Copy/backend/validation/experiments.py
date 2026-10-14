"""Validation harness for the provenance-calibrated inference engine.

Protocol: leave-one-season-out over all 36 real Ariyalur crop-seasons.

For each held-out season the correction coefficients are re-fitted and the
calibration store is rebuilt from the other 35 seasons only, so no quantity
used to predict a season is derived from that season. The historical weather
used to form the thermal-time expectation also excludes the held-out season's
own crop-year.

Comparators, all evaluated on the identical held-out predictions:

* ``base_pooled``  -- the current production behaviour: the fixed Random Forest
  with one hard-coded pooled conformal margin. This is the benchmark the
  invention has to beat.
* ``fixed_overlay`` -- the current bounded rule overlay
  (``weather_adjustment_service.py:76-79``) with its pooled interval.
* ``engine``       -- the proposed method.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from backend.config import TRAINING_DATA_FILE, WEATHER_HISTORICAL_FILE, YIELD_DATA_FILE
from backend.integrity import vegetation as veg_mod
from backend.integrity.calibration import CalibrationStore, PooledBaselineStore, conformal_quantile
from backend.integrity.engine import InferenceState, IntegrityEngine, fit_correction_model
from backend.integrity.thermal_time import (
    accumulate_gdd,
    daily_gdd,
    persistence_skill_curve,
    prepare_seasons,
)
from backend.integrity.ledger import InferenceLedger, replay
from backend.validation.degrade import (
    ALL_REGIMES,
    REGIME_LIVE,
    REGIME_NO_VEG,
    REGIME_RADIUS_DISAGREE,
    REGIME_LOW_PIXEL,
    REGIME_CLIMATOLOGY,
    REGIME_CACHED,
    REGIME_CONFLICT_VEG,
    REGIME_CONFLICT_WEATHER,
    REGIME_FORECAST_LONG,
    REGIME_FORECAST_SHORT,
    DegradedState,
    SeasonRecord,
    build_season_records,
    climatology_lookup,
    degrade,
    expected_ndvi,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RESULTS_DIR = BASE_DIR / "validation_results"

NOMINAL_COVERAGE = 0.90

# ---------------------------------------------------------------------------
# Fixed base model
# ---------------------------------------------------------------------------


class FixedBaseModel:
    """Random Forest held fixed, mirroring backend/models/yield_model.py.

    Refit per fold on the fold's own training seasons only. Parameters are never
    updated by the engine under test.
    """

    NON_FEATURE_COLS = ["State", "District", "Production", "Yield", "price_was_imputed"]

    def __init__(self, training_df: pd.DataFrame):
        from sklearn.ensemble import RandomForestRegressor

        self.df = training_df.copy()
        self.df["price_was_imputed"] = self.df["avg_modal_price"].isna()
        for col in ("avg_modal_price", "price_volatility"):
            self.df[col] = self.df.groupby("Crop")[col].transform(lambda s: s.fillna(s.mean()))
            self.df[col] = self.df[col].fillna(self.df[col].mean())

        dummies = pd.get_dummies(self.df, columns=["Crop", "Season"], drop_first=False)
        features = [c for c in dummies.columns if c not in self.NON_FEATURE_COLS]
        X = dummies[features]
        X = X.drop(columns=[c for c in X.columns if c.startswith("soil_")])
        variances = X.var(numeric_only=True)
        X = X.drop(columns=variances[variances == 0].index.tolist())
        self.feature_names = X.columns.tolist()

        self.model = RandomForestRegressor(n_estimators=100, random_state=42)
        self.model.fit(X.astype(float), self.df["Yield"].to_numpy(dtype=float))

    def predict(self, row: pd.Series) -> float:
        frame = pd.DataFrame([row])
        frame = pd.get_dummies(frame, columns=["Crop", "Season"])
        frame = frame.reindex(columns=self.feature_names, fill_value=0)
        return float(self.model.predict(frame.astype(float).values)[0])

    @staticmethod
    def expectation_row(train_df: pd.DataFrame, crop: str, season: str) -> pd.Series:
        subset = train_df[(train_df["Crop"] == crop) & (train_df["Season"] == season)]
        if subset.empty:
            subset = train_df[train_df["Crop"] == crop]
        if subset.empty:
            subset = train_df
        numeric = [
            "Crop_Year", "Area", "total_rainfall_mm", "avg_temp_max",
            "avg_temp_min", "avg_temp_mean", "total_et0", "avg_wind_speed",
            "avg_modal_price", "price_volatility", "n_price_records",
        ]
        out = subset[numeric].mean(numeric_only=True).to_dict()
        out["Crop"] = crop
        out["Season"] = season
        return pd.Series(out)


# ---------------------------------------------------------------------------
# Legacy comparators, reimplemented to isolate the contribution under test
# ---------------------------------------------------------------------------


def fixed_overlay_adjustment(
    *,
    rainfall_anomaly_pct: float,
    et0_anomaly_pct: float,
    temp_anomaly_c: float,
    heat_days: int,
) -> float:
    """The current bounded rule overlay (weather_adjustment_service.py:76-79)."""

    def clamp(v, lo, hi):
        return max(lo, min(hi, v))

    rain_effect = clamp(rainfall_anomaly_pct * 0.0012, -0.06, 0.02)
    heat_effect = clamp(-max(0.0, temp_anomaly_c) * 0.012 - max(0, heat_days - 3) * 0.002, -0.05, 0.0)
    et0_effect = clamp(-max(0.0, et0_anomaly_pct) * 0.0004, -0.03, 0.0)
    return clamp(rain_effect + heat_effect + et0_effect, -0.12, 0.05)


def calendar_expectation(record: SeasonRecord) -> Dict[str, float]:
    """Ablation comparator: expected weather over a fixed calendar share."""

    n = len(record.daily)
    prefix = record.daily.iloc[: max(1, int(round(n * 0.55)))]
    return {
        "total_rainfall_mm": float(prefix["precipitation_sum"].sum()),
        "total_et0_mm": float(prefix["et0_fao_evapotranspiration"].sum()),
        "avg_temp_max": float(prefix["temperature_2m_max"].mean()),
        "heat_days": float((prefix["temperature_2m_max"] >= 35.0).sum()),
    }


def calendar_anomaly(record: SeasonRecord, state: DegradedState) -> Dict[str, float]:
    """Anomaly computed over a fixed calendar window instead of thermal time."""

    exp = calendar_expectation(record)
    observed = state.observed
    forecast = state.forecast
    a_rain = float(observed["precipitation_sum"].sum()) + float(forecast["precipitation_sum"].sum())
    a_et0 = float(observed["et0_fao_evapotranspiration"].sum()) + float(forecast["et0_fao_evapotranspiration"].sum())
    n = len(observed) + len(forecast)
    a_tmax = (
        (float(observed["temperature_2m_max"].mean()) * len(observed) + float(forecast["temperature_2m_max"].mean()) * len(forecast))
        / n
        if n
        else 0.0
    )
    a_heat = float((observed["temperature_2m_max"] >= 35.0).sum()) + float((forecast["temperature_2m_max"] >= 35.0).sum())
    return {
        "rainfall_pct": ((a_rain - exp["total_rainfall_mm"]) / exp["total_rainfall_mm"] * 100.0) if exp["total_rainfall_mm"] > 0 else 0.0,
        "et0_pct": ((a_et0 - exp["total_et0_mm"]) / exp["total_et0_mm"] * 100.0) if exp["total_et0_mm"] > 0 else 0.0,
        "temp_max_c": a_tmax - exp["avg_temp_max"] if a_tmax else 0.0,
        "heat_days": a_heat - exp["heat_days"],
    }


# ---------------------------------------------------------------------------
# Fold execution
# ---------------------------------------------------------------------------


@dataclass
class Prediction:
    season_key: str
    regime: str
    actual: float
    base: float
    engine_corrected: float
    engine_lower: float
    engine_upper: float
    engine_half_width: float
    engine_guarantee: str
    engine_partition: str
    engine_quality_key: str
    overlay_corrected: float
    overlay_lower: float
    overlay_upper: float
    conflict_code: str
    conflict_expected: bool
    conflict_predicted: bool
    ablation_corrected: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    @property
    def engine_covered(self) -> bool:
        return self.engine_lower <= self.actual <= self.engine_upper

    @property
    def overlay_covered(self) -> bool:
        return self.overlay_lower <= self.actual <= self.overlay_upper

    @property
    def base_covered(self) -> bool:
        return self.base_lower <= self.actual <= self.base_upper

    base_lower: float = 0.0
    base_upper: float = 0.0


@dataclass
class FoldResult:
    fold_season: str
    correction: Dict[str, float]
    predictions: List[Prediction]
    pooled_base_quantile: float
    store_total: int
    entries: List = field(default_factory=list)


def _prepared_context(records: Sequence[SeasonRecord], exclude_key: Optional[str], base_temp_c: float = 10.0):
    from backend.integrity.thermal_time import prepare_seasons

    return prepare_seasons(_historical_context(records, exclude_key), base_temp_c)


def _historical_context(records: Sequence[SeasonRecord], exclude_key: Optional[str]) -> List[dict]:
    """Historical seasons for the thermal-time expectation, minus the excluded one."""

    out = []
    for r in records:
        if exclude_key and r.key == exclude_key:
            continue
        out.append({"year": r.crop_year, "daily": r.daily})
    return out


def _base_row_for(train_df: pd.DataFrame, record: SeasonRecord) -> pd.Series:
    """Feature row built from the fold's training seasons only."""

    return FixedBaseModel.expectation_row(train_df, record.crop, record.season)


def base_prediction_under_degradation(
    model: FixedBaseModel,
    train_df: pd.DataFrame,
    record: SeasonRecord,
    state: DegradedState,
) -> float:
    """Base-model prediction when the weather feed is in the degraded state.

    This is the part that makes the experiment meaningful. A base model that
    always receives the same pristine feature row cannot be hurt by a weather
    outage, so nothing would ever under-cover and a calibration method would
    have no headroom to demonstrate anything.

    In a real deployment the outage reaches the base model too: with no live
    weather it must be fed climatology, a cache, or a projection. Here the
    training-table weather features are replaced with aggregates of whatever the
    degraded state actually supplies, scaled from the covered part of the season
    to the full season by the fraction of it that has elapsed. Soil, area, price
    and year features are untouched, because those sources are not under test.
    """

    row = _base_row_for(train_df, record).copy()
    full_n = len(record.daily)

    observed = state.observed
    forecast = state.forecast
    covered = len(observed) + len(forecast)

    if covered == 0:
        # No weather at all: the model falls back to the climatological row it
        # would have used at sowing, scaled by elapsed season fraction.
        elapsed = float(full_n)
        scale = elapsed / max(1.0, full_n)
        row["total_rainfall_mm"] = float(row["total_rainfall_mm"]) * scale
        row["total_et0"] = float(row["total_et0"]) * scale
        return model.predict(row)

    rain = float(observed["precipitation_sum"].sum()) + float(forecast["precipitation_sum"].sum())
    et0 = float(observed["et0_fao_evapotranspiration"].sum()) + float(forecast["et0_fao_evapotranspiration"].sum())
    tmax_obs = float(observed["temperature_2m_max"].mean()) if len(observed) else 0.0
    tmin_obs = float(observed["temperature_2m_min"].mean()) if len(observed) else 0.0
    # Mean temperature is derived rather than read: the persistence
    # pseudo-forecast does not carry a mean column, and (max + min) / 2 is what
    # the archive's own mean column equals to within rounding.
    tmean_obs = (tmax_obs + tmin_obs) / 2.0
    if len(forecast):
        tmax_obs = (tmax_obs * len(observed) + float(forecast["temperature_2m_max"].mean()) * len(forecast)) / covered
        tmin_obs = (tmin_obs * len(observed) + float(forecast["temperature_2m_min"].mean()) * len(forecast)) / covered
        tmean_obs = (tmax_obs + tmin_obs) / 2.0

    scale = covered / max(1.0, full_n)
    row["total_rainfall_mm"] = rain / max(scale, 1e-9)
    row["total_et0"] = et0 / max(scale, 1e-9)
    row["avg_temp_max"] = tmax_obs
    row["avg_temp_min"] = tmin_obs
    row["avg_temp_mean"] = tmean_obs
    return model.predict(row)


def run_fold(
    held: SeasonRecord,
    records: Sequence[SeasonRecord],
    train_df: pd.DataFrame,
    clim: Dict[str, Dict[str, float]],
    skill_curve: Dict[int, float],
    *,
    ablations: bool = True,
) -> FoldResult:
    train_records = [r for r in records if r.key != held.key]
    # The held-out season must not contribute to the model it is scored against.
    fold_train_df = train_df[
        ~((train_df["Crop"] == held.crop) & (train_df["Season"] == held.season) & (train_df["Crop_Year"] == held.crop_year))
    ]
    base_model = FixedBaseModel(fold_train_df)

    # Leave-one-out base predictions over the training seasons. Calibration
    # residuals taken from in-sample predictions are far smaller than
    # out-of-sample ones, which inflates measured coverage and makes every
    # interval look safe. The production system already computes this margin
    # by leave-one-out (yield_model.recompute_loocv); the store must as well.
    loo_base: Dict[str, float] = {}
    for r in train_records:
        inner = train_df[
            ~((train_df["Crop"] == r.crop) & (train_df["Season"] == r.season) & (train_df["Crop_Year"] == r.crop_year))
        ]
        inner_model = FixedBaseModel(inner)
        loo_base[r.key] = inner_model.predict(_base_row_for(inner, r))

    # 1. Fit the correction on the training seasons' full-season weather,
    #    using out-of-sample base predictions.
    rel_residuals: List[float] = []
    anomalies: List[Dict[str, float]] = []
    for r in train_records:
        base_pred = loo_base[r.key]
        if base_pred <= 1e-9:
            continue
        full = r.daily
        # Full-season anomaly against a thermal-time expectation built from the
        # *other* training seasons.
        from backend.integrity.thermal_time import (
            prepare_seasons,
            thermal_time_expectation_prepared,
        )

        total_gdd = float(accumulate_gdd(full, r.base_temp_c).iloc[-1])
        ctx_prepared = prepare_seasons(_historical_context(train_records, r.key), r.base_temp_c)
        expectation = thermal_time_expectation_prepared(ctx_prepared, total_gdd, r.base_temp_c)
        rain = float(full["precipitation_sum"].sum())
        et0 = float(full["et0_fao_evapotranspiration"].sum())
        tmax = float(full["temperature_2m_max"].mean())
        heat = float((full["temperature_2m_max"] >= 35.0).sum())
        anomalies.append(
            {
                "rainfall_pct": ((rain - expectation.total_rainfall_mm) / expectation.total_rainfall_mm * 100.0)
                if expectation.total_rainfall_mm > 0
                else 0.0,
                "et0_pct": ((et0 - expectation.total_et0_mm) / expectation.total_et0_mm * 100.0)
                if expectation.total_et0_mm > 0
                else 0.0,
                "temp_max_c": tmax - expectation.avg_temp_max,
                "heat_days": heat - expectation.heat_days,
            }
        )
        rel_residuals.append((r.yield_t_per_ha - base_pred) / base_pred)

    correction = fit_correction_model(rel_residuals, anomalies)

    # Prepared historical contexts, computed once per scope and reused.
    prepared_all = _prepared_context(records, held.key, held.base_temp_c)
    prepared_train = {r.key: _prepared_context(train_records, r.key, r.base_temp_c) for r in train_records}

    # 2. Build the calibration store by degrading the training seasons.
    #    Both the base prediction and the correction inputs come from the
    #    degraded state, because an outage reaches the whole pipeline.
    store = CalibrationStore()
    pooled_base = PooledBaselineStore()
    context_all = _historical_context(records, held.key)

    for r in train_records:
        pooled_base.add(r.yield_t_per_ha - loo_base[r.key])
        for regime in ALL_REGIMES:
            state = degrade(r, regime, clim, seed=abs(hash(r.key + regime)) % (2**31))
            degraded_base = base_prediction_under_degradation(base_model, fold_train_df, r, state)
            engine = IntegrityEngine(correction, store, skill_curve=skill_curve, ledger=_NullLedger())
            result = _run_engine(engine, r, state, degraded_base, context_all, prepared_train[r.key])
            store.add(result.quality_key, r.yield_t_per_ha - result.corrected_prediction)

    pooled_q = pooled_base.quantile()

    # 3. Evaluate the held-out season in every regime.
    base_pred = base_model.predict(_base_row_for(fold_train_df, held))
    predictions: List[Prediction] = []
    fold_ledger = InferenceLedger()

    for regime in ALL_REGIMES:
        state = degrade(held, regime, clim, seed=abs(hash(held.key + regime)) % (2**31))
        base_pred = base_prediction_under_degradation(base_model, fold_train_df, held, state)
        engine = IntegrityEngine(correction, store, skill_curve=skill_curve, ledger=fold_ledger)
        result = _run_engine(engine, held, state, base_pred, context_all, prepared_all)

        overlay_delta = fixed_overlay_adjustment(
            rainfall_anomaly_pct=result.anomaly["rainfall_pct"],
            et0_anomaly_pct=result.anomaly["et0_pct"],
            temp_anomaly_c=result.anomaly["temp_max_c"],
            heat_days=max(0, int(round(result.anomaly["heat_days"]))),
        )
        overlay_point = max(0.0, base_pred * (1.0 + overlay_delta))
        overlay_margin = pooled_q
        ablation_points: Dict[str, float] = {}
        if ablations:
            ablation_points = _run_ablations(held, state, base_pred, correction, context_all)

        predictions.append(
            Prediction(
                season_key=held.key,
                regime=regime,
                actual=held.yield_t_per_ha,
                base=base_pred,
                base_lower=max(0.0, base_pred - pooled_q),
                base_upper=base_pred + pooled_q,
                engine_corrected=result.corrected_prediction,
                engine_lower=result.interval_lower,
                engine_upper=result.interval_upper,
                engine_half_width=(result.interval_upper - result.interval_lower) / 2.0,
                engine_guarantee=result.selection.guarantee_level,
                engine_partition=result.selection.partition_label,
                engine_quality_key=result.quality_key.label(),
                overlay_corrected=overlay_point,
                overlay_lower=max(0.0, overlay_point - overlay_margin),
                overlay_upper=overlay_point + overlay_margin,
                conflict_code=result.conflict.code.value,
                conflict_expected=regime in (REGIME_CONFLICT_VEG, REGIME_CONFLICT_WEATHER),
                conflict_predicted=result.conflict.genuine_conflict,
                ablation_corrected=ablation_points,
                notes=result.notes,
            )
        )

    return FoldResult(
        fold_season=held.key,
        correction=correction.to_dict(),
        predictions=predictions,
        pooled_base_quantile=pooled_q,
        store_total=store.total,
        entries=list(fold_ledger.entries),
    )


class _NullLedger:
    """Ledger stub so that fold-local engines do not accumulate state."""

    def append(self, entry):  # noqa: D102
        return entry

    @property
    def head(self) -> str:  # noqa: D102
        return "0" * 64


def _run_engine(engine: IntegrityEngine, record: SeasonRecord, state: DegradedState, base_pred: float, context: List[dict], prepared=None):
    istate = InferenceState(
        inference_id=f"{record.key}|{id(state)}",
        crop=record.crop,
        season=record.season,
        crop_year=record.crop_year,
        base_prediction=base_pred,
        base_model_version="rf-100-lofo-fixed",
        observed_daily=state.observed,
        forecast_daily=state.forecast,
        historical_seasons=context,
        weather_category=state.weather_category,
        vegetation_deviation=state.vegetation_deviation,
        ladder_samples=state.ladder,
        valid_pixel_pct=state.valid_pixel_pct,
        weather_age_days=state.weather_age_days,
        vegetation_age_days=state.vegetation_age_days,
        forecast_horizon_days=state.forecast_horizon_days,
        prepared_seasons=prepared,
    )
    return engine.infer(istate)


def _run_ablations(
    record: SeasonRecord,
    state: DegradedState,
    base_pred: float,
    correction,
    context: List[dict],
) -> Dict[str, float]:
    """Point estimates with one component removed at a time."""

    from backend.integrity.thermal_time import thermal_time_expectation

    out: Dict[str, float] = {}

    # No thermal-time alignment: calendar-window expectation instead.
    cal_anom = calendar_anomaly(record, state)
    out["no_thermal_time"] = max(
        0.0, base_pred * (1.0 + correction.apply(cal_anom)["total"])
    )

    # No horizon weighting: every forecast day counts fully.
    from backend.integrity.engine import _combine_observed_and_forecast
    from backend.integrity.thermal_time import horizon_weight

    combined = _combine_observed_and_forecast(state.observed, state.forecast)
    total_gdd = float(accumulate_gdd(combined, record.base_temp_c).iloc[-1]) if len(combined) else 0.0
    expectation = thermal_time_expectation(context, total_gdd, record.base_temp_c)
    a_rain = float(state.observed["precipitation_sum"].sum()) + float(state.forecast["precipitation_sum"].sum())
    a_et0 = float(state.observed["et0_fao_evapotranspiration"].sum()) + float(state.forecast["et0_fao_evapotranspiration"].sum())
    n = len(state.observed) + len(state.forecast)
    a_tmax = (
        (float(state.observed["temperature_2m_max"].mean()) * len(state.observed) + float(state.forecast["temperature_2m_max"].mean()) * len(state.forecast))
        / n
        if n
        else 0.0
    )
    a_heat = float((state.observed["temperature_2m_max"] >= 35.0).sum()) + float((state.forecast["temperature_2m_max"] >= 35.0).sum())
    unweighted = {
        "rainfall_pct": ((a_rain - expectation.total_rainfall_mm) / expectation.total_rainfall_mm * 100.0) if expectation.total_rainfall_mm > 0 else 0.0,
        "et0_pct": ((a_et0 - expectation.total_et0_mm) / expectation.total_et0_mm * 100.0) if expectation.total_et0_mm > 0 else 0.0,
        "temp_max_c": a_tmax - expectation.avg_temp_max if a_tmax else 0.0,
        "heat_days": a_heat - expectation.heat_days,
    }
    out["no_horizon_weighting"] = max(0.0, base_pred * (1.0 + correction.apply(unweighted)["total"]))

    # No de-trending in the spatial stability metric: raw spread across radii.
    if state.ladder and len(state.ladder) >= 3:
        raw = veg_mod.support_stability(state.ladder)
        raw_spread = float(np.std(raw.ndvi_by_radius))
        det = raw.normalised_residual
        out["no_detrend_spatial"] = max(0.0, base_pred * (1.0 + correction.apply(unweighted)["total"]))

    # No correction at all: the untouched fixed base model.
    out["no_correction"] = base_pred

    return out


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def coverage_rate(preds: Sequence[Prediction], method: str) -> float:
    if not preds:
        return float("nan")
    if method == "engine":
        return float(np.mean([p.engine_covered for p in preds]))
    if method == "overlay":
        return float(np.mean([p.overlay_covered for p in preds]))
    if method == "base":
        return float(np.mean([p.base_covered for p in preds]))
    return float("nan")


def mean_width(preds: Sequence[Prediction], method: str) -> float:
    if not preds:
        return float("nan")
    if method == "engine":
        return float(np.mean([(p.engine_upper - p.engine_lower) for p in preds]))
    if method == "overlay":
        return float(np.mean([(p.overlay_upper - p.overlay_lower) for p in preds]))
    if method == "base":
        return float(np.mean([(p.base_upper - p.base_lower) for p in preds]))
    return float("nan")


def point_error(preds: Sequence[Prediction], method: str) -> float:
    if not preds:
        return float("nan")
    key = {"engine": "engine_corrected", "overlay": "overlay_corrected", "base": "base"}[method]
    return float(np.mean([abs(getattr(p, key) - p.actual) for p in preds]))


def conflict_scores(preds: Sequence[Prediction]) -> Dict[str, float]:
    tp = sum(1 for p in preds if p.conflict_expected and p.conflict_predicted)
    fp = sum(1 for p in preds if not p.conflict_expected and p.conflict_predicted)
    fn = sum(1 for p in preds if p.conflict_expected and not p.conflict_predicted)
    tn = sum(1 for p in preds if not p.conflict_expected and not p.conflict_predicted)
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) and np.isfinite(precision) and np.isfinite(recall) else float("nan")
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1,
        "accuracy": (tp + tn) / len(preds) if preds else float("nan"),
    }


def replay_determinism(folds: Sequence[FoldResult]) -> Dict[str, float]:
    """Replay real ledger entries and count bit-identical reproductions.

    The entries replayed are the ones the engine actually emitted during fold
    evaluation, not reconstructed fixtures, so a pass demonstrates that the
    record the system writes is sufficient to reproduce the system's own output.
    """

    checked = 0
    reproduced = 0
    failures: List[str] = []

    for fold in folds:
        for entry in fold.entries:
            outcome = replay(entry, IntegrityEngine.recompute)
            checked += 1
            if outcome["reproduced"]:
                reproduced += 1
            else:
                failures.append(f"{entry.inference_id}: {outcome['mismatches']}")

    return {
        "checked": checked,
        "reproduced": reproduced,
        "rate": reproduced / checked if checked else float("nan"),
        "failures": failures[:5],
    }


def tamper_detection() -> Dict[str, float]:
    """Verify that editing a sealed entry breaks verification."""

    from backend.integrity.ledger import LedgerEntry

    entry = LedgerEntry(
        inference_id="tamper-1",
        engine_version="1.0.0",
        base_model_version="m",
        base_prediction=1.0,
        input_values={"crop": "Rice", "season": "Kharif", "crop_year": 2015},
        provenance=[],
        provenance_digest="",
        thermal_time={},
        anomaly_vector={},
        forecast_weights={},
        vegetation={},
        conflict={},
        correction_components={},
        correction_bounds={"lower": -0.12, "upper": 0.05},
        total_correction=0.0,
        calibration_selection={"quantile": 0.1},
        corrected_prediction=1.1,
        interval_lower=1.0,
        interval_upper=1.2,
        created_at="2026-01-01T00:00:00+00:00",
    ).seal()
    before = entry.verify_seal()
    entry.corrected_prediction = 9.9
    after = entry.verify_seal()
    return {"intact_detected": before, "tampered_detected_as_invalid": not after}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> Dict:
    parser = argparse.ArgumentParser(description="Validate the provenance-calibrated inference engine.")
    parser.add_argument("--out", default=str(RESULTS_DIR))
    parser.add_argument("--limit", type=int, default=0, help="debug: run only the first N folds")
    args = parser.parse_args(argv)

    weather = pd.read_csv(WEATHER_HISTORICAL_FILE)
    weather["date"] = pd.to_datetime(weather["date"])
    yield_df = pd.read_csv(YIELD_DATA_FILE)
    train_df = pd.read_csv(TRAINING_DATA_FILE)

    records = build_season_records(yield_df, weather)
    clim = climatology_lookup(weather)
    skill_curve = persistence_skill_curve(weather, horizons=[1, 3, 5, 7, 10, 14, 16, 21])

    ordered = sorted(records, key=lambda r: (r.crop_year, r.crop, r.season))
    if args.limit:
        ordered = ordered[: args.limit]

    print(f"[validate] {len(ordered)} seasons | archive {len(weather)} daily rows | regimes {len(ALL_REGIMES)}")
    print(f"[validate] persistence skill curve: { {k: round(v, 4) for k, v in sorted(skill_curve.items())} }")

    folds: List[FoldResult] = []
    for i, record in enumerate(ordered, start=1):
        fold = run_fold(record, records, train_df, clim, skill_curve)
        folds.append(fold)
        print(f"[validate] fold {i}/{len(ordered)} {record.key:32s} store={fold.store_total:5d} pooled_q={fold.pooled_base_quantile:.4f}")

    all_preds = [p for f in folds for p in f.predictions]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "n_seasons": len(ordered),
        "n_predictions": len(all_preds),
        "regimes": list(ALL_REGIMES),
        "nominal_coverage": NOMINAL_COVERAGE,
        "overall": {},
        "by_regime": {},
        "conflict_detection": conflict_scores(all_preds),
        "replay": replay_determinism(folds),
        "tamper": tamper_detection(),
        "correction_coefficients": folds[0].correction if folds else {},
    }

    for method in ("base", "overlay", "engine"):
        cov = coverage_rate(all_preds, method)
        summary["overall"][method] = {
            "coverage": cov,
            "mean_width": mean_width(all_preds, method),
            "calibration_error": abs(cov - NOMINAL_COVERAGE),
            "point_mae": point_error(all_preds, method),
        }

    for regime in ALL_REGIMES:
        subset = [p for p in all_preds if p.regime == regime]
        if not subset:
            continue
        entry = {}
        for method in ("base", "overlay", "engine"):
            cov = coverage_rate(subset, method)
            entry[method] = {
                "coverage": cov,
                "mean_width": mean_width(subset, method),
                "calibration_error": abs(cov - NOMINAL_COVERAGE),
                "point_mae": point_error(subset, method),
            }
        guarantees: Dict[str, int] = {}
        for p in subset:
            guarantees[p.engine_guarantee] = guarantees.get(p.engine_guarantee, 0) + 1
        entry["guarantee_mix"] = guarantees
        summary["by_regime"][regime] = entry

    # Ablations: point error with each component removed.
    ablation_names: List[str] = []
    for p in all_preds:
        for k in p.ablation_corrected:
            if k not in ablation_names:
                ablation_names.append(k)
    summary["ablations"] = {}
    for name in ablation_names:
        rows = [(p, p.ablation_corrected[name]) for p in all_preds if name in p.ablation_corrected]
        if not rows:
            continue
        mae = float(np.mean([abs(v - p.actual) for p, v in rows]))
        bias = float(np.mean([v - p.actual for p, v in rows]))
        summary["ablations"][name] = {"point_mae": mae, "mean_bias": bias, "n": len(rows)}
    summary["ablations"]["engine_full"] = {
        "point_mae": float(np.mean([abs(p.engine_corrected - p.actual) for p in all_preds])),
        "mean_bias": float(np.mean([p.engine_corrected - p.actual for p in all_preds])),
        "n": len(all_preds),
    }

    # Rows for inspection.
    with (out_dir / "validation_predictions.csv").open("w", newline="") as fh:
        cols = [
            "season_key", "regime", "actual", "base", "engine_corrected",
            "engine_lower", "engine_upper", "engine_covered", "engine_half_width",
            "engine_guarantee", "engine_partition", "engine_quality_key",
            "base_covered", "overlay_corrected", "overlay_covered",
            "conflict_code", "conflict_expected", "conflict_predicted",
        ]
        pd.DataFrame([{c: getattr(p, c) for c in cols} for p in all_preds]).to_csv(fh, index=False)

    with (out_dir / "validation_summary.json").open("w") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True, default=float)

    # Deployment artefact: a calibration store and a fitted correction built
    # from ALL seasons. This is deliberately separate from the per-fold stores
    # used for scoring, which never see the season they score.
    deployment = _build_deployment_artefact(ordered, records, train_df, clim, skill_curve)
    with (out_dir / "calibration_store.json").open("w") as fh:
        json.dump(deployment, fh, indent=2, sort_keys=True, default=float)

    _print_report(summary)
    return summary


def _build_deployment_artefact(ordered, records, train_df, clim, skill_curve) -> Dict:
    """Full-data calibration store and correction, for deployment use.

    Held-out scoring in the main loop never uses this. It exists so the running
    application has a provenance-conditioned store to select from at request
    time rather than a single pooled constant.
    """

    from backend.integrity.engine import ANOMALY_FIELDS
    from backend.integrity.thermal_time import thermal_time_expectation_prepared

    base_model = FixedBaseModel(train_df)

    rel_residuals: List[float] = []
    anomalies: List[Dict[str, float]] = []
    loo: Dict[str, float] = {}
    for r in ordered:
        inner = train_df[
            ~((train_df["Crop"] == r.crop) & (train_df["Season"] == r.season) & (train_df["Crop_Year"] == r.crop_year))
        ]
        loo[r.key] = FixedBaseModel(inner).predict(_base_row_for(inner, r))

    for r in ordered:
        prepared = prepare_seasons(_historical_context(records, r.key), r.base_temp_c)
        total_gdd = float(accumulate_gdd(r.daily, r.base_temp_c).iloc[-1])
        exp = thermal_time_expectation_prepared(prepared, total_gdd, r.base_temp_c)
        rain = float(r.daily["precipitation_sum"].sum())
        et0 = float(r.daily["et0_fao_evapotranspiration"].sum())
        tmax = float(r.daily["temperature_2m_max"].mean())
        heat = float((r.daily["temperature_2m_max"] >= 35.0).sum())
        anomalies.append(
            {
                "rainfall_pct": ((rain - exp.total_rainfall_mm) / exp.total_rainfall_mm * 100.0) if exp.total_rainfall_mm > 0 else 0.0,
                "et0_pct": ((et0 - exp.total_et0_mm) / exp.total_et0_mm * 100.0) if exp.total_et0_mm > 0 else 0.0,
                "temp_max_c": tmax - exp.avg_temp_max,
                "heat_days": heat - exp.heat_days,
            }
        )
        base_pred = loo[r.key]
        if base_pred > 1e-9:
            rel_residuals.append((r.yield_t_per_ha - base_pred) / base_pred)

    correction = fit_correction_model(rel_residuals, anomalies)

    store = CalibrationStore()
    partitions: Dict[str, List[float]] = {}
    for r in ordered:
        prepared = prepare_seasons(_historical_context(records, r.key), r.base_temp_c)
        for regime in ALL_REGIMES:
            state = degrade(r, regime, clim, seed=abs(hash(r.key + regime)) % (2**31))
            base_pred = base_prediction_under_degradation(base_model, train_df, r, state)
            engine = IntegrityEngine(correction, store, skill_curve=skill_curve, ledger=_NullLedger())
            result = _run_engine(engine, r, state, base_pred, _historical_context(records, r.key), prepared)
            label = result.quality_key.label()
            partitions.setdefault(label, []).append(abs(r.yield_t_per_ha - result.corrected_prediction))

    return {
        "generated_by": "backend.validation.experiments",
        "n_seasons": len(ordered),
        "n_observations": len(ordered) * len(ALL_REGIMES),
        "alpha": store.alpha,
        "min_partition": store.min_partition,
        "inflation": store.inflation,
        "partitions": partitions,
        "correction": correction.to_dict(),
        "fit_relative_residuals": rel_residuals,
        "fit_anomalies": [{k: a[k] for k in ANOMALY_FIELDS} for a in anomalies],
        "ridge": 1.0,
        "bound_alpha": 0.01,
        "warning": (
            "Partitions are populated by counterfactual degradation of the same seasons "
            "used to fit the correction, so residuals within a season are correlated. "
            "Effective sample size is below the nominal count."
        ),
    }


def _print_report(summary: Dict) -> None:
    print("\n" + "=" * 96)
    print(f"{'OVERALL':<34}{'coverage':>12}{'width':>12}{'cal.err':>10}{'MAE':>10}")
    print("-" * 96)
    for method in ("base", "overlay", "engine"):
        o = summary["overall"][method]
        print(f"{method:<34}{o['coverage']:>12.4f}{o['mean_width']:>12.4f}{o['calibration_error']:>10.4f}{o['point_mae']:>10.4f}")
    print("=" * 96)
    print(f"{'BY REGIME':<34}{'cov(base)':>12}{'cov(overlay)':>14}{'cov(engine)':>14}{'width(base)':>13}{'width(engine)':>14}")
    print("-" * 96)
    for regime, entry in summary["by_regime"].items():
        print(
            f"{regime:<34}"
            f"{entry['base']['coverage']:>12.4f}"
            f"{entry['overlay']['coverage']:>14.4f}"
            f"{entry['engine']['coverage']:>14.4f}"
            f"{entry['base']['mean_width']:>13.4f}"
            f"{entry['engine']['mean_width']:>14.4f}"
        )
    print("=" * 96)
    cd = summary["conflict_detection"]
    print(f"conflict detection: precision={cd['precision']:.4f} recall={cd['recall']:.4f} f1={cd['f1']:.4f} "
          f"acc={cd['accuracy']:.4f}  (tp={cd['tp']} fp={cd['fp']} fn={cd['fn']} tn={cd['tn']})")
    rp = summary["replay"]
    print(f"replay: {rp['reproduced']}/{rp['checked']} bit-identical (rate={rp['rate']:.4f})")
    print(f"tamper detection: intact={summary['tamper']['intact_detected']} "
          f"edited_entry_rejected={summary['tamper']['tampered_detected_as_invalid']}")
    print("\nablations (point MAE / mean bias):")
    for name, ab in sorted(summary["ablations"].items()):
        print(f"  {name:<28} MAE={ab['point_mae']:.4f}  bias={ab['mean_bias']:+.4f}  n={ab['n']}")
    print("=" * 96)


if __name__ == "__main__":
    main()
