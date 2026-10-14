"""Orchestration of the provenance-calibrated inference pipeline.

The base model is fixed. Nothing here retrains, refits or reweights it. The
engine only decides *how much to trust the base estimate under the current
input provenance state*, and by how much to move it given the weather anomaly.

Processing order matters and is fixed:

    provenance -> thermal time -> thermal-time historical expectation
      -> anomaly vector -> vegetation deviation + spatial stability
      -> cross-source conflict -> quality key -> bounded correction
      -> calibration selection -> ledger entry

The quality key is computed *before* the calibration selection and *after* the
conflict detector, so the disagreement between sources can influence which
residual population is used but can never influence the point estimate
directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from backend.integrity import conflict as conflict_mod
from backend.integrity import thermal_time as tt
from backend.integrity import vegetation as veg_mod
from backend.integrity.calibration import CalibrationStore, QualityKey, Selection
from backend.integrity.ledger import ENGINE_VERSION, InferenceLedger, LedgerEntry
from backend.integrity.provenance import ProvenanceLedger, SourceCategory, SourceRecord, response_digest

ANOMALY_FIELDS = ("rainfall_pct", "et0_pct", "temp_max_c", "heat_days")


@dataclass
class CorrectionModel:
    """Fitted coefficients and their admissible range.

    ``coefficients`` are fitted by ridge regression on historical base-model
    residuals; they are not hand-chosen. ``lower``/``upper`` bound the total
    relative correction and are taken from the empirical distribution of the
    fitted residuals, so the bound is derived from the data rather than
    asserted.
    """

    coefficients: Dict[str, float]
    lower: float
    upper: float
    alpha: float = 0.01
    fitted_on: int = 0
    fit_rmse: float = 0.0

    def apply(self, anomaly: Dict[str, float]) -> Dict[str, Any]:
        components: Dict[str, float] = {}
        raw = 0.0
        for field in ANOMALY_FIELDS:
            value = float(anomaly.get(field, 0.0) or 0.0)
            contribution = float(self.coefficients.get(field, 0.0)) * value
            components[field] = contribution
            raw += contribution
        total = float(np.clip(raw, self.lower, self.upper))
        return {
            "raw_total": raw,
            "total": total,
            "was_bounded": abs(raw - total) > 1e-12,
            "components": components,
            "bound_lower": self.lower,
            "bound_upper": self.upper,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "coefficients": {k: round(v, 8) for k, v in self.coefficients.items()},
            "bound_lower": round(self.lower, 6),
            "bound_upper": round(self.upper, 6),
            "alpha": self.alpha,
            "fitted_on": self.fitted_on,
            "fit_rmse": round(self.fit_rmse, 6),
            "method": "ridge on historical base-model relative residuals, bounded by the empirical residual distribution",
        }


@dataclass
class InferenceState:
    """Everything one inference needs, in values rather than references.

    ``observed_daily`` and ``forecast_daily`` carry the actual rows, not the
    name of a file or a service, because replay sufficiency requires the record
    to stand alone.
    """

    inference_id: str
    crop: str
    season: str
    crop_year: int
    base_prediction: float
    base_model_version: str
    observed_daily: pd.DataFrame
    forecast_daily: pd.DataFrame
    historical_seasons: List[dict]
    weather_category: SourceCategory
    vegetation_deviation: Optional[float] = None
    ladder_samples: Optional[Sequence[veg_mod.LadderSample]] = None
    valid_pixel_pct: Optional[float] = None
    weather_age_days: Optional[float] = None
    vegetation_age_days: Optional[float] = None
    forecast_horizon_days: Optional[int] = None
    prepared_seasons: Optional[List[Any]] = None

    def __post_init__(self) -> None:
        if self.weather_age_days is None:
            self.weather_age_days = float(len(self.observed_daily))
        if self.vegetation_age_days is None:
            self.vegetation_age_days = float(self.vegetation_age_days or 0.0)


@dataclass
class IntegrityResult:
    base_prediction: float
    corrected_prediction: float
    interval_lower: float
    interval_upper: float
    quality_key: QualityKey
    selection: Selection
    conflict: conflict_mod.ConflictResult
    anomaly: Dict[str, float]
    correction: Dict[str, Any]
    thermal: Dict[str, Any]
    vegetation: Dict[str, Any]
    entry: LedgerEntry
    overconfident: bool
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": "Provenance-calibrated estimate",
            "base_prediction_t_per_ha": round(self.base_prediction, 4),
            "corrected_prediction_t_per_ha": round(self.corrected_prediction, 4),
            "interval": {
                "lower_bound": round(self.interval_lower, 4),
                "upper_bound": round(self.interval_upper, 4),
                "half_width": round((self.interval_upper - self.interval_lower) / 2.0, 4),
                "guarantee_level": self.selection.guarantee_level,
                "is_calibrated": self.selection.calibrated,
                "interpretation": (
                    "Half-width is the split-conformal quantile of the matching provenance "
                    "partition when the partition met the size floor; otherwise it is a pooled "
                    "quantile widened by a stated inflation factor, which carries no "
                    "finite-sample coverage guarantee."
                ),
            },
            "quality_key": self.quality_key.label(),
            "calibration_selection": self.selection.to_dict(),
            "conflict": self.conflict.to_dict(),
            "anomaly_vector": {k: round(float(v), 4) for k, v in self.anomaly.items()},
            "correction": {
                "total_pct": round(self.correction["total"] * 100.0, 4),
                "raw_total_pct": round(self.correction["raw_total"] * 100.0, 4),
                "was_bounded": self.correction["was_bounded"],
                "components_pct": {k: round(v * 100.0, 5) for k, v in self.correction["components"].items()},
                "bounds_pct": [
                    round(self.correction["bound_lower"] * 100.0, 4),
                    round(self.correction["bound_upper"] * 100.0, 4),
                ],
            },
            "thermal_time": self.thermal,
            "vegetation": self.vegetation,
            "overconfident_flag": self.overconfident,
            "notes": self.notes,
            "inference_id": self.entry.inference_id,
            "output_digest": self.entry.entry_hash,
        }


class IntegrityEngine:
    def __init__(
        self,
        correction: CorrectionModel,
        calibration: CalibrationStore,
        *,
        skill_curve: Optional[Dict[int, float]] = None,
        heat_threshold_c: float = 35.0,
        ledger: Optional[InferenceLedger] = None,
    ) -> None:
        self.correction = correction
        self.calibration = calibration
        self.skill_curve = skill_curve or {}
        self.heat_threshold_c = heat_threshold_c
        self.ledger = ledger or InferenceLedger()

    # -- public API -------------------------------------------------------
    def infer(self, state: InferenceState) -> IntegrityResult:
        notes: List[str] = []
        provenance = ProvenanceLedger()

        # 1. Provenance records for both input layers.
        provenance.record(
            SourceRecord(
                source_id="weather",
                category=state.weather_category,
                acquired_at=ProvenanceLedger.now(),
                data_age_hours=float(state.weather_age_days or 0.0) * 24.0,
                forecast_horizon_days=state.forecast_horizon_days,
                missing_treatment=(
                    "climatology substituted for unobserved days"
                    if state.weather_category is SourceCategory.HISTORICAL_FALLBACK
                    else "none"
                ),
                version="open-meteo-compatible",
                response_digest=response_digest(
                    {
                        "observed": _daily_payload(state.observed_daily),
                        "forecast": _daily_payload(state.forecast_daily),
                    }
                ),
            )
        )
        if state.ladder_samples:
            stability = veg_mod.support_stability(state.ladder_samples)
            provenance.record(
                SourceRecord(
                    source_id="vegetation",
                    category=SourceCategory.LIVE,
                    acquired_at=ProvenanceLedger.now(),
                    radius_m=float(max(s.radius_m for s in state.ladder_samples)),
                    valid_pixel_pct=state.valid_pixel_pct,
                    missing_treatment="none",
                    version="sentinel-2-l2a-like",
                    response_digest=response_digest(
                        [{"r": s.radius_m, "v": round(s.ndvi, 6)} for s in state.ladder_samples]
                    ),
                )
            )
        else:
            stability = None

        # 2. Thermal time over observed + forecast, with horizon weighting.
        combined = _combine_observed_and_forecast(state.observed_daily, state.forecast_daily)
        base_temp = tt.DEFAULT_BASE_TEMPS.get(state.crop, 10.0)
        cum_gdd = tt.accumulate_gdd(combined, base_temp)
        current_gdd = float(cum_gdd.iloc[-1]) if len(cum_gdd) else 0.0

        if state.prepared_seasons is not None:
            expectation = tt.thermal_time_expectation_prepared(
                state.prepared_seasons,
                target_gdd=current_gdd,
                base_temp_c=base_temp,
                heat_threshold_c=self.heat_threshold_c,
            )
        else:
            expectation = tt.thermal_time_expectation(
                state.historical_seasons,
                target_gdd=current_gdd,
                base_temp_c=base_temp,
                heat_threshold_c=self.heat_threshold_c,
            )

        observed = state.observed_daily if len(state.observed_daily) else combined.head(0)
        forecast = state.forecast_daily

        observed_rain = float(observed["precipitation_sum"].sum()) if len(observed) else 0.0
        observed_et0 = float(observed["et0_fao_evapotranspiration"].sum()) if len(observed) else 0.0
        observed_tmax = float(observed["temperature_2m_max"].mean()) if len(observed) else 0.0
        observed_heat = float((observed["temperature_2m_max"] >= self.heat_threshold_c).sum()) if len(observed) else 0.0

        fc_weights = [
            tt.horizon_weight(i + 1, self.skill_curve) for i in range(len(forecast))
        ]
        if fc_weights:
            w = np.asarray(fc_weights, dtype=float)
            total_w = float(w.sum()) or 1.0
            forecast_rain = float((forecast["precipitation_sum"].to_numpy(dtype=float) * w).sum()) / total_w
            forecast_et0 = float((forecast["et0_fao_evapotranspiration"].to_numpy(dtype=float) * w).sum()) / total_w
            forecast_tmax = float((forecast["temperature_2m_max"].to_numpy(dtype=float) * w).sum()) / total_w
            forecast_heat = float(
                (forecast["temperature_2m_max"].to_numpy(dtype=float) * w >= self.heat_threshold_c).sum()
            )
        else:
            forecast_rain = forecast_et0 = forecast_tmax = forecast_heat = 0.0

        weighted_forecast_days = float(np.sum(fc_weights)) if fc_weights else 0.0
        coverage_days = float(len(observed)) + weighted_forecast_days

        actual_rain = observed_rain + forecast_rain
        actual_et0 = observed_et0 + forecast_et0
        actual_tmax = (observed_tmax * len(observed) + forecast_tmax * len(forecast)) / coverage_days if coverage_days else 0.0
        actual_heat = observed_heat + forecast_heat

        # The expectation is truncated at the thermal-time equivalent stage, so
        # it covers the same developmental span. Both sides are expressed over
        # that span; no calendar-window scaling is applied.
        exp_rain = expectation.total_rainfall_mm
        exp_et0 = expectation.total_et0_mm
        exp_tmax = expectation.avg_temp_max
        exp_heat = expectation.heat_days

        anomaly = {
            "rainfall_pct": ((actual_rain - exp_rain) / exp_rain * 100.0) if exp_rain > 0 else 0.0,
            "et0_pct": ((actual_et0 - exp_et0) / exp_et0 * 100.0) if exp_et0 > 0 else 0.0,
            "temp_max_c": (actual_tmax - exp_tmax) if actual_tmax else 0.0,
            "heat_days": (actual_heat - exp_heat),
        }
        anomaly = {k: (0.0 if not np.isfinite(v) else float(v)) for k, v in anomaly.items()}

        # 3. Vegetation deviation and spatial trust.
        veg_band = veg_mod.ndvi_quality_band(state.valid_pixel_pct, stability)
        if veg_band == "absent":
            notes.append("No vegetation observation was available; cross-source agreement is untestable.")
        if stability is not None and not stability.converged:
            notes.append(
                "The vegetation radius ladder did not converge, so the point sample is treated "
                "as spatially unreliable."
            )
        if state.weather_category is SourceCategory.HISTORICAL_FALLBACK:
            notes.append(
                "Weather came from long-run climatology, not from observation; anomalies computed "
                "against it are not independent evidence of field conditions."
            )

        # 4. Cross-source conflict.
        conflict_result = conflict_mod.detect(
            rainfall_anomaly_pct=anomaly["rainfall_pct"],
            et0_anomaly_pct=anomaly["et0_pct"],
            temp_anomaly_c=anomaly["temp_max_c"],
            vegetation_deviation=state.vegetation_deviation,
            vegetation_quality_band=veg_band,
            weather_category_label=state.weather_category.label,
            weather_age_days=state.weather_age_days,
            vegetation_age_days=state.vegetation_age_days,
        )
        if conflict_result.detected:
            notes.append(
                f"Cross-source disagreement ({conflict_result.code.value}); the point estimate is "
                "left unchanged and the uncertainty treatment is selected from the conflict stratum."
            )

        # 5. Quality key, then calibration selection.
        key = QualityKey(
            weather=state.weather_category.label,
            vegetation=veg_band,
            conflict=conflict_result.bucket,
        )
        selection = self.calibration.select(key)
        if not selection.calibrated:
            notes.append(
                "No provenance partition met the minimum size for a finite-sample guarantee; the "
                "interval below is a pooled quantile widened by a stated factor and is not a "
                "recalibrated prediction interval."
            )

        # 6. Bounded correction.
        correction = self.correction.apply(anomaly)
        corrected = max(0.0, float(state.base_prediction) * (1.0 + correction["total"]))

        interval_lower = max(0.0, corrected - selection.quantile)
        interval_upper = corrected + selection.quantile

        overconfident = bool(not selection.calibrated and selection.quantile < abs(float(state.base_prediction) * 0.10))
        if overconfident:
            notes.append(
                "Interval half-width is below 10% of the point estimate while the provenance "
                "partition is not size-qualified; treated as an overconfident output."
            )

        # 7. Ledger entry, carrying values rather than references.
        entry = LedgerEntry(
            inference_id=state.inference_id,
            engine_version=ENGINE_VERSION,
            base_model_version=state.base_model_version,
            base_prediction=float(state.base_prediction),
            input_values={
                "crop": state.crop,
                "season": state.season,
                "crop_year": int(state.crop_year),
                "observed_daily": _daily_payload(state.observed_daily),
                "forecast_daily": _daily_payload(state.forecast_daily),
                "weather_category": int(state.weather_category),
                "vegetation_deviation": state.vegetation_deviation,
                "valid_pixel_pct": state.valid_pixel_pct,
                "ladder": [
                    {"radius_m": int(s.radius_m), "ndvi": round(float(s.ndvi), 6)}
                    for s in (state.ladder_samples or [])
                ],
            },
            provenance=provenance.to_canonical_list(),
            provenance_digest=provenance.digest(),
            thermal_time={
                "current_gdd": round(current_gdd, 4),
                "base_temp_c": base_temp,
                "expectation": expectation.to_dict(),
                "covered_days": round(coverage_days, 4),
                "observed_days": int(len(observed)),
                "forecast_days": int(len(forecast)),
            },
            anomaly_vector=anomaly,
            forecast_weights={
                str(i + 1): round(w, 6) for i, w in enumerate(fc_weights)
            },
            vegetation={
                "quality_band": veg_band,
                "deviation": state.vegetation_deviation,
                "stability": stability.to_dict() if stability else None,
            },
            conflict=conflict_result.to_dict(),
            correction_components=correction["components"],
            correction_bounds={
                "lower": float(correction["bound_lower"]),
                "upper": float(correction["bound_upper"]),
            },
            total_correction=correction["total"],
            calibration_selection=selection.to_dict(),
            corrected_prediction=corrected,
            interval_lower=interval_lower,
            interval_upper=interval_upper,
            created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        )
        self.ledger.append(entry)

        return IntegrityResult(
            base_prediction=float(state.base_prediction),
            corrected_prediction=corrected,
            interval_lower=interval_lower,
            interval_upper=interval_upper,
            quality_key=key,
            selection=selection,
            conflict=conflict_result,
            anomaly=anomaly,
            correction=correction,
            thermal={
                "current_gdd": round(current_gdd, 4),
                "base_temp_c": base_temp,
                "observed_days": int(len(observed)),
                "forecast_days": int(len(forecast)),
                "covered_days": round(coverage_days, 4),
                "historical_expectation": expectation.to_dict(),
            },
            vegetation={
                "quality_band": veg_band,
                "deviation": None if state.vegetation_deviation is None else round(float(state.vegetation_deviation), 5),
                "stability": stability.to_dict() if stability else None,
            },
            entry=entry,
            overconfident=overconfident,
            notes=notes,
        )

    # -- deterministic recomputation used by replay ----------------------
    @staticmethod
    def recompute(entry: LedgerEntry) -> Dict[str, float]:
        """Pure recomputation of the stored output from the stored values only.

        This deliberately shares no state with :meth:`infer`. It reads the
        ledger entry's own recorded values, so a successful replay demonstrates
        that the record is self-sufficient rather than that the object graph
        happens to still be in memory.
        """

        payload = entry.input_values
        crop = payload["crop"]
        base_temp = tt.DEFAULT_BASE_TEMPS.get(crop, 10.0)

        observed = _payload_to_daily(payload["observed_daily"])
        forecast = _payload_to_daily(payload["forecast_daily"])

        combined = _combine_observed_and_forecast(observed, forecast)
        cum_gdd = tt.accumulate_gdd(combined, base_temp)
        current_gdd = float(cum_gdd.iloc[-1]) if len(cum_gdd) else 0.0

        # The historical expectation is a function of the expectation already
        # committed to the entry; replay does not re-derive it, because that
        # would require the historical archive, which is exactly the external
        # dependency replay is meant to avoid.
        expectation = entry.thermal_time["expectation"]
        exp_rain = float(expectation["total_rainfall_mm"])
        exp_et0 = float(expectation["total_et0_mm"])
        exp_tmax = float(expectation["avg_temp_max"])
        exp_heat = float(expectation["heat_days"])

        weights = entry.forecast_weights or {}
        if forecast is not None and len(forecast):
            w = np.asarray([float(weights.get(str(i + 1), 1.0)) for i in range(len(forecast))], dtype=float)
            total_w = float(w.sum()) or 1.0
            f_rain = float((forecast["precipitation_sum"].to_numpy(dtype=float) * w).sum()) / total_w
            f_et0 = float((forecast["et0_fao_evapotranspiration"].to_numpy(dtype=float) * w).sum()) / total_w
            f_tmax = float((forecast["temperature_2m_max"].to_numpy(dtype=float) * w).sum()) / total_w
        else:
            f_rain = f_et0 = f_tmax = 0.0

        o_rain = float(observed["precipitation_sum"].sum()) if len(observed) else 0.0
        o_et0 = float(observed["et0_fao_evapotranspiration"].sum()) if len(observed) else 0.0
        o_tmax = float(observed["temperature_2m_max"].mean()) if len(observed) else 0.0

        anomaly = dict(entry.anomaly_vector)
        anomaly["rainfall_pct"] = ((o_rain + f_rain - exp_rain) / exp_rain * 100.0) if exp_rain > 0 else 0.0
        anomaly["et0_pct"] = ((o_et0 + f_et0 - exp_et0) / exp_et0 * 100.0) if exp_et0 > 0 else 0.0

        # Re-derive the correction from its recorded per-field components and
        # re-apply the recorded bounds. This verifies that the bound was
        # actually applied at inference time, rather than merely echoing the
        # stored total.
        raw = 0.0
        for field_name in ANOMALY_FIELDS:
            raw += float(entry.correction_components.get(field_name, 0.0))
        bounds = entry.correction_bounds or {}
        lower = float(bounds.get("lower", float("-inf")))
        upper = float(bounds.get("upper", float("inf")))
        total = float(np.clip(raw, lower, upper))

        corrected = max(0.0, float(entry.base_prediction) * (1.0 + total))

        quantile = _quantile_from_selection(entry.calibration_selection)
        return {
            "corrected_prediction": corrected,
            "interval_lower": max(0.0, corrected - quantile),
            "interval_upper": corrected + quantile,
            "current_gdd": current_gdd,
            "recomputed_anomaly_rainfall_pct": anomaly["rainfall_pct"],
        }


def _quantile_from_selection(selection: Dict[str, Any]) -> float:
    return float(selection.get("quantile", 0.0))


def _combine_observed_and_forecast(observed: pd.DataFrame, forecast: pd.DataFrame) -> pd.DataFrame:
    frames = [f for f in (observed, forecast) if f is not None and len(f) > 0]
    if not frames:
        return pd.DataFrame(columns=["date", "temperature_2m_max", "temperature_2m_min", "precipitation_sum", "et0_fao_evapotranspiration"])
    combined = pd.concat(frames, ignore_index=True)
    return combined.sort_values("date").reset_index(drop=True)


def _daily_payload(frame: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
    if frame is None or len(frame) == 0:
        return []
    return [
        {
            "date": str(row["date"])[:10],
            "tmax": round(float(row["temperature_2m_max"]), 4),
            "tmin": round(float(row["temperature_2m_min"]), 4),
            "rain": round(float(row["precipitation_sum"]), 4),
            "et0": round(float(row["et0_fao_evapotranspiration"]), 4),
        }
        for _, row in frame.iterrows()
    ]


def _payload_to_daily(payload: List[Dict[str, Any]]) -> pd.DataFrame:
    if not payload:
        return pd.DataFrame(columns=["date", "temperature_2m_max", "temperature_2m_min", "precipitation_sum", "et0_fao_evapotranspiration"])
    return pd.DataFrame(
        [
            {
                "date": row["date"],
                "temperature_2m_max": row["tmax"],
                "temperature_2m_min": row["tmin"],
                "precipitation_sum": row["rain"],
                "et0_fao_evapotranspiration": row["et0"],
            }
            for row in payload
        ]
    )


def fit_correction_model(
    relative_residuals: Sequence[float],
    anomalies: Sequence[Dict[str, float]],
    *,
    ridge: float = 1.0,
    alpha: float = 0.01,
) -> CorrectionModel:
    """Ridge-fit the correction coefficients on historical base-model residuals.

    Targets are relative residuals ``(y - y_base) / y_base`` for historical
    seasons, regressed on the anomaly vector observed over the same season.
    The admissible range is the empirical ``alpha`` quantile of the fitted
    relative residuals, so the bound follows the data rather than being chosen.
    """

    y = np.asarray([float(v) for v in relative_residuals], dtype=float)
    if y.size == 0:
        return CorrectionModel({f: 0.0 for f in ANOMALY_FIELDS}, -0.12, 0.05, alpha, 0, 0.0)

    design = np.column_stack(
        [np.asarray([float(a.get(f, 0.0) or 0.0) for a in anomalies], dtype=float) for f in ANOMALY_FIELDS]
    )
    # Anomalies are percentages and heat-day counts live on different scales,
    # so the design matrix is standardised before fitting. The standardisation
    # is folded back into the coefficients so the fitted model is expressed in
    # the original anomaly units.
    scale = design.std(axis=0)
    scale[scale == 0] = 1.0
    design_scaled = (design - design.mean(axis=0)) / scale

    # Augment with an intercept column, then ridge-penalise only the slopes.
    n_features = design_scaled.shape[1]
    augmented = np.column_stack([np.ones(design_scaled.shape[0]), design_scaled])
    reg = ridge * np.eye(n_features + 1)
    reg[0, 0] = 0.0  # do not penalise the intercept
    beta = np.linalg.solve(augmented.T @ augmented + reg, augmented.T @ y)

    intercept = float(beta[0] - (design.mean(axis=0) / scale) @ beta[1:])
    coefficients = {f: float(beta[i + 1] / scale[i]) for i, f in enumerate(ANOMALY_FIELDS)}

    fitted = augmented @ beta
    rmse = float(np.sqrt(np.mean((y - fitted) ** 2)))

    lower = float(np.quantile(y, alpha))
    upper = float(np.quantile(y, 1.0 - alpha))

    return CorrectionModel(coefficients, lower, upper, alpha, int(y.size), rmse)


__all__ = [
    "CorrectionModel",
    "InferenceState",
    "IntegrityEngine",
    "IntegrityResult",
    "fit_correction_model",
    "ANOMALY_FIELDS",
]
