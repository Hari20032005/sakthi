"""Cross-source conflict detection between weather and vegetation evidence.

Two independent sensors describe the same crop: a weather record supplies
water and heat stress, a vegetation index supplies the canopy's response. When
they disagree, at least one of them is unreliable, but which one is not known.

The detector emits a machine-readable code. The code never changes the
point estimate. It selects the uncertainty treatment, which is the defensible
use: the disagreement itself is evidence that the input set is degraded.

Note that asynchrony between meteorological and vegetation drought is a
published finding, so *detecting* the disagreement is not new. Using the
disagreement as a key that routes the prediction to a different conditional
calibration pool is the step claimed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

# Thresholds are expressed as percentages of the historical expectation so
# they scale with season length and crop.
WEATHER_STRESS_RAINFALL_PCT = -20.0
WEATHER_STRESS_ET0_PCT = 25.0
WEATHER_STRESS_TEMP_C = 2.0
VEGETATION_DECLINE = -0.08
VEGETATION_NORMAL = -0.02
TIMESTAMP_TOLERANCE_DAYS = 2.0


class ConflictCode(str, Enum):
    NONE = "NONE"
    WEATHER_STRESS_NDVI_NORMAL = "WEATHER_STRESS_NDVI_NORMAL"
    NDVI_DECLINE_WEATHER_NORMAL = "NDVI_DECLINE_WEATHER_NORMAL"
    LOW_QUALITY_NDVI = "LOW_QUALITY_NDVI"
    FALLBACK_WEATHER_HIGH_VEGETATION_UNCERTAINTY = "FALLBACK_WEATHER_HIGH_VEGETATION_UNCERTAINTY"
    INSUFFICIENT_MULTI_SOURCE_EVIDENCE = "INSUFFICIENT_MULTI_SOURCE_EVIDENCE"
    SOURCE_TIMESTAMP_MISMATCH = "SOURCE_TIMESTAMP_MISMATCH"


#: Conflict codes that must be pooled separately, because a disagreement
#: between independent sensors invalidates the assumption that the input set is
#: internally consistent.
CONFLICT_BEARING = {
    ConflictCode.WEATHER_STRESS_NDVI_NORMAL,
    ConflictCode.NDVI_DECLINE_WEATHER_NORMAL,
}


@dataclass
class ConflictResult:
    code: ConflictCode
    detail: str
    weather_flag: str
    vegetation_flag: str

    @property
    def detected(self) -> bool:
        return self.code is not ConflictCode.NONE

    @property
    def genuine_conflict(self) -> bool:
        """True only where two present, usable sources actively disagree.

        Quality and coverage codes (low quality, absent, timestamp mismatch) are
        excluded: they say an input is weak, not that two inputs contradict each
        other. Those are already carried by the vegetation quality band, and
        folding them in here would double-count one fact.
        """

        return self.code in CONFLICT_BEARING

    @property
    def bucket(self) -> str:
        """Collapsed to the value used as a calibration key."""

        return "conflict" if self.genuine_conflict else "clean"

    def to_dict(self) -> Dict[str, str]:
        return {
            "code": self.code.value,
            "detail": self.detail,
            "weather_flag": self.weather_flag,
            "vegetation_flag": self.vegetation_flag,
            "bucket": self.bucket,
        }


def detect(
    *,
    rainfall_anomaly_pct: Optional[float] = None,
    et0_anomaly_pct: Optional[float] = None,
    temp_anomaly_c: Optional[float] = None,
    vegetation_deviation: Optional[float] = None,
    vegetation_quality_band: str = "absent",
    weather_category_label: str = "historical_fallback",
    weather_age_days: Optional[float] = None,
    vegetation_age_days: Optional[float] = None,
) -> ConflictResult:
    """Classify agreement between weather-derived stress and vegetation state.

    ``vegetation_deviation`` is the observed vegetation index minus the index
    expected at the same accumulated thermal time. Negative means the canopy is
    behind where it should be for its developmental stage.
    """

    weather_flag = _weather_flag(rainfall_anomaly_pct, et0_anomaly_pct, temp_anomaly_c)
    vegetation_flag = _vegetation_flag(vegetation_deviation)

    if weather_age_days is not None and vegetation_age_days is not None:
        if abs(float(weather_age_days) - float(vegetation_age_days)) > TIMESTAMP_TOLERANCE_DAYS:
            return ConflictResult(
                ConflictCode.SOURCE_TIMESTAMP_MISMATCH,
                (
                    f"weather record is {float(weather_age_days):.1f} d old while vegetation "
                    f"observation is {float(vegetation_age_days):.1f} d old; the two do not "
                    "describe the same crop state"
                ),
                weather_flag,
                vegetation_flag,
            )

    if vegetation_quality_band == "absent" or vegetation_deviation is None:
        return ConflictResult(
            ConflictCode.INSUFFICIENT_MULTI_SOURCE_EVIDENCE,
            "no usable vegetation observation, so cross-source agreement cannot be established",
            weather_flag,
            "absent",
        )

    if vegetation_quality_band == "degraded":
        return ConflictResult(
            ConflictCode.LOW_QUALITY_NDVI,
            (
                "vegetation observation fell in the degraded quality band, so it cannot be "
                "used to corroborate or contradict the weather record"
            ),
            weather_flag,
            vegetation_flag,
        )

    if weather_flag == "stress" and vegetation_flag == "normal":
        return ConflictResult(
            ConflictCode.WEATHER_STRESS_NDVI_NORMAL,
            (
                "weather record indicates water or heat stress but the vegetation index is at "
                "or above its thermal-time expectation"
            ),
            weather_flag,
            vegetation_flag,
        )

    if weather_flag == "normal" and vegetation_flag == "decline":
        return ConflictResult(
            ConflictCode.NDVI_DECLINE_WEATHER_NORMAL,
            (
                "vegetation index is behind its thermal-time expectation while the weather "
                "record shows no comparable stress"
            ),
            weather_flag,
            vegetation_flag,
        )

    if weather_category_label == "historical_fallback" and vegetation_flag == "decline":
        return ConflictResult(
            ConflictCode.FALLBACK_WEATHER_HIGH_VEGETATION_UNCERTAINTY,
            (
                "weather came from a historical fallback rather than an observation while the "
                "vegetation index shows decline, so the decline cannot be attributed"
            ),
            weather_flag,
            vegetation_flag,
        )

    return ConflictResult(ConflictCode.NONE, "weather and vegetation evidence are consistent", weather_flag, vegetation_flag)


def _weather_flag(rainfall_pct, et0_pct, temp_c) -> str:
    stressed = False
    if rainfall_pct is not None and float(rainfall_pct) <= WEATHER_STRESS_RAINFALL_PCT:
        stressed = True
    if et0_pct is not None and float(et0_pct) >= WEATHER_STRESS_ET0_PCT:
        stressed = True
    if temp_c is not None and float(temp_c) >= WEATHER_STRESS_TEMP_C:
        stressed = True
    return "stress" if stressed else "normal"


def _vegetation_flag(deviation) -> str:
    if deviation is None:
        return "absent"
    d = float(deviation)
    if d <= VEGETATION_DECLINE:
        return "decline"
    if d < VEGETATION_NORMAL:
        return "lagging"
    return "normal"


def known_codes() -> List[str]:
    return [c.value for c in ConflictCode]
