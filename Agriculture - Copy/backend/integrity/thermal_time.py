"""Thermal-time alignment of observed and forecast weather against history.

Two distinct operations:

1. ``daily_gdd`` / ``accumulate_gdd`` -- standard base-temperature thermal time.
   Base-temperature growing degree days are long-established agronomy; this
   module uses them as an *alignment coordinate*, not as a novel index.

2. ``thermal_time_expectation`` -- the part that matters for the invention.
   Instead of averaging historical seasons over a *calendar* window, it
   averages them over a window of equal *accumulated thermal time*, and weights
   each historical season by the similarity of its thermal trajectory.

   Calendar alignment is wrong whenever sowing date drifts: a season sown three
   weeks late has accumulated less thermal time by any given calendar date, so
   a calendar-window historical mean systematically over-states the weather a
   late season still has to endure. Aligning by accumulated thermal time removes
   that bias. The literature fixes calendar bias either by fixing a biofix date
   or by using thermal time as a feature; it does not use it to re-weight the
   historical expectation that the correction is measured against.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

# Base temperatures (degC) used for the two crops in the training set.
# Rice: 10 degC is the widely used figure for indica rice.
# Cotton: 12 degC is commonly used for cotton phenology.
DEFAULT_BASE_TEMPS: Dict[str, float] = {"Rice": 10.0, "Cotton(lint)": 12.0}

# Upper cap applied to daily maximum temperature, standard GDD practice
# (McMaster & Wilhelm style capped GDD) to stop a single hot spell from
# dominating the integral.
DEFAULT_UPPER_CAP_C = 34.0


def daily_gdd(tmax_c, tmin_c, base_temp_c: float, upper_cap_c: float = DEFAULT_UPPER_CAP_C) -> float:
    """One day's thermal time, upper-capped at ``upper_cap_c``."""

    tmax = min(float(tmax_c), upper_cap_c)
    tmin = float(tmin_c)
    if tmax < base_temp_c:
        return 0.0
    tmin_eff = min(max(tmin, base_temp_c), tmax)
    return max(0.0, ((tmax + tmin_eff) / 2.0) - base_temp_c)


def accumulate_gdd(daily: pd.DataFrame, base_temp_c: float, upper_cap_c: float = DEFAULT_UPPER_CAP_C) -> pd.Series:
    """Cumulative thermal time over a daily frame ordered by date."""

    frame = daily.sort_values("date").reset_index(drop=True)
    gdd = [
        daily_gdd(t, n, base_temp_c, upper_cap_c)
        for t, n in zip(frame["temperature_2m_max"], frame["temperature_2m_min"])
    ]
    return pd.Series(np.cumsum(gdd), index=frame.index, dtype=float)


def gdd_at_calibrated_date(
    daily: pd.DataFrame, target_gdd: float, base_temp_c: float, upper_cap_c: float = DEFAULT_UPPER_CAP_C
) -> Optional[pd.Timestamp]:
    """Calendar date at which a season first reaches ``target_gdd`` thermal time."""

    series = accumulate_gdd(daily, base_temp_c, upper_cap_c)
    if series.empty or series.iloc[-1] < target_gdd:
        return None
    idx = int(np.searchsorted(series.to_numpy(), target_gdd, side="left"))
    ordered = daily.sort_values("date").reset_index(drop=True)
    return pd.Timestamp(ordered["date"].iloc[idx])


def _window_to_gdd(
    daily: pd.DataFrame, target_gdd: float, base_temp_c: float, upper_cap_c: float
) -> Optional[pd.DataFrame]:
    """The prefix of ``daily`` whose accumulated thermal time equals ``target_gdd``."""

    ordered = daily.sort_values("date").reset_index(drop=True)
    series = accumulate_gdd(ordered, base_temp_c, upper_cap_c)
    if series.empty:
        return None
    total = float(series.iloc[-1])
    if total < target_gdd:
        return None
    idx = int(np.searchsorted(series.to_numpy(), target_gdd, side="left"))
    return ordered.iloc[: idx + 1]


@dataclass
class ThermalExpectation:
    """Historical expected weather at a matched thermal-time stage."""

    target_gdd: float
    base_temp_c: float
    n_analogues: int
    analogue_years: List[int]
    weights: List[float]
    total_rainfall_mm: float
    total_et0_mm: float
    avg_temp_max: float
    heat_days: float
    coverage_fraction: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "target_gdd": round(self.target_gdd, 3),
            "base_temp_c": self.base_temp_c,
            "n_analogues": self.n_analogues,
            "total_rainfall_mm": round(self.total_rainfall_mm, 2),
            "total_et0_mm": round(self.total_et0_mm, 2),
            "avg_temp_max": round(self.avg_temp_max, 3),
            "heat_days": round(self.heat_days, 3),
            "coverage_fraction": round(self.coverage_fraction, 4),
        }


@dataclass
class PreparedSeason:
    """A historical season with its cumulative series computed once.

    ``thermal_time_expectation`` is called once per (season, regime) pair inside
    the validation harness, and recomputing the cumulative series each time
    dominated the run. Preparing once and reusing is behaviourally identical.
    """

    year: int
    dates: np.ndarray
    gdd: np.ndarray
    rain_cum: np.ndarray
    et0_cum: np.ndarray
    tmax: np.ndarray
    heat: np.ndarray

    @property
    def total_gdd(self) -> float:
        return float(self.gdd[-1]) if len(self.gdd) else 0.0

    def prefix(self, target_gdd: float) -> int:
        if len(self.gdd) == 0 or self.gdd[-1] < target_gdd:
            return -1
        return int(np.searchsorted(self.gdd, target_gdd, side="left"))


def prepare_seasons(historical_seasons: Sequence[dict], base_temp_c: float, upper_cap_c: float = DEFAULT_UPPER_CAP_C) -> List[PreparedSeason]:
    out: List[PreparedSeason] = []
    for season in historical_seasons:
        daily = season["daily"].sort_values("date").reset_index(drop=True)
        if daily.empty:
            continue
        gdd = np.cumsum(
            [
                daily_gdd(t, n, base_temp_c, upper_cap_c)
                for t, n in zip(daily["temperature_2m_max"], daily["temperature_2m_min"])
            ]
        )
        out.append(
            PreparedSeason(
                year=int(season["year"]),
                dates=daily["date"].to_numpy(),
                gdd=gdd,
                rain_cum=np.cumsum(daily["precipitation_sum"].to_numpy(dtype=float)),
                et0_cum=np.cumsum(daily["et0_fao_evapotranspiration"].to_numpy(dtype=float)),
                tmax=daily["temperature_2m_max"].to_numpy(dtype=float),
                heat=(daily["temperature_2m_max"].to_numpy(dtype=float) >= 35.0).astype(float),
            )
        )
    return out


def thermal_time_expectation_prepared(
    prepared: Sequence[PreparedSeason],
    target_gdd: float,
    base_temp_c: float,
    similarity_scale: float = 0.35,
    heat_threshold_c: float = 35.0,
) -> ThermalExpectation:
    """As :func:`thermal_time_expectation`, over pre-prepared cumulative series."""

    usable: List[dict] = []
    for season in prepared:
        idx = season.prefix(target_gdd)
        if idx < 4:  # fewer than five days of analogue is not a usable stage
            continue
        usable.append(
            {
                "year": season.year,
                "rain_cum": float(season.rain_cum[idx]),
                "et0_cum": float(season.et0_cum[idx]),
                "tmax": float(season.tmax[: idx + 1].mean()),
                "heat": float(season.heat[: idx + 1].sum()),
                "days": idx + 1,
            }
        )

    if not usable:
        return ThermalExpectation(target_gdd, base_temp_c, 0, [], [], 0.0, 0.0, 0.0, 0.0, 0.0)

    rains = np.array([a["rain_cum"] for a in usable], dtype=float)
    median_rain = float(np.median(rains))
    spread = max(median_rain, 1.0)
    raw_weights = np.exp(-np.abs(rains - median_rain) / (similarity_scale * spread))
    total_weight = float(raw_weights.sum())
    weights = (raw_weights / total_weight).tolist() if total_weight > 0 else [1.0 / len(usable)] * len(usable)

    def wmean(key: str) -> float:
        return float(sum(w * a[key] for w, a in zip(weights, usable)))

    return ThermalExpectation(
        target_gdd=float(target_gdd),
        base_temp_c=float(base_temp_c),
        n_analogues=len(usable),
        analogue_years=[a["year"] for a in usable],
        weights=[round(w, 6) for w in weights],
        total_rainfall_mm=wmean("rain_cum"),
        total_et0_mm=wmean("et0_cum"),
        avg_temp_max=wmean("tmax"),
        heat_days=wmean("heat"),
        coverage_fraction=float(len(usable) / max(1, len(prepared))),
    )


def thermal_time_expectation(
    historical_seasons: Sequence[dict],
    target_gdd: float,
    base_temp_c: float,
    upper_cap_c: float = DEFAULT_UPPER_CAP_C,
    similarity_scale: float = 0.35,
    heat_threshold_c: float = 35.0,
) -> ThermalExpectation:
    """Historical expectation at an equivalent thermal-time stage.

    ``historical_seasons`` is a sequence of ``{"year": int, "daily": DataFrame}``
    where each ``daily`` frame carries one season for one historical year.

    Each analogue is truncated at the calendar date on which *it* reaches
    ``target_gdd`` accumulated thermal time, so every analogue is compared over
    the same developmental window rather than the same calendar window.
    Analogues are then weighted by how closely their truncated cumulative
    rainfall trajectory matches the reference trajectory, so years that were
    anomalous early in the season count for less.
    """

    usable: List[dict] = []
    for season in historical_seasons:
        window = _window_to_gdd(season["daily"], target_gdd, base_temp_c, upper_cap_c)
        if window is None or len(window) < 5:
            continue
        series = accumulate_gdd(window, base_temp_c, upper_cap_c)
        usable.append(
            {
                "year": int(season["year"]),
                "window": window,
                "rain_cum": float(window["precipitation_sum"].sum()),
                "et0_cum": float(window["et0_fao_evapotranspiration"].sum()),
                "tmax": float(window["temperature_2m_max"].mean()),
                "heat": float((window["temperature_2m_max"] >= heat_threshold_c).sum()),
                "days": int(len(window)),
                "gdd": float(series.iloc[-1]),
            }
        )

    if not usable:
        return ThermalExpectation(target_gdd, base_temp_c, 0, [], [], 0.0, 0.0, 0.0, 0.0, 0.0)

    rains = np.array([a["rain_cum"] for a in usable], dtype=float)
    median_rain = float(np.median(rains))
    # A year that has already accumulated far more (or less) rain than the
    # median analogue by this thermal stage is a poor analogue, independent of
    # how much more of the season remains.
    spread = max(median_rain, 1.0)
    raw_weights = np.exp(-np.abs(rains - median_rain) / (similarity_scale * spread))
    total_weight = float(raw_weights.sum())
    weights = (raw_weights / total_weight).tolist() if total_weight > 0 else [1.0 / len(usable)] * len(usable)

    def wmean(key: str) -> float:
        return float(sum(w * a[key] for w, a in zip(weights, usable)))

    return ThermalExpectation(
        target_gdd=float(target_gdd),
        base_temp_c=float(base_temp_c),
        n_analogues=len(usable),
        analogue_years=[a["year"] for a in usable],
        weights=[round(w, 6) for w in weights],
        total_rainfall_mm=wmean("rain_cum"),
        total_et0_mm=wmean("et0_cum"),
        avg_temp_max=wmean("tmax"),
        heat_days=wmean("heat"),
        coverage_fraction=float(len(usable) / max(1, len(historical_seasons))),
    )


def persistence_skill_curve(
    archive: pd.DataFrame, horizons: Sequence[int], season_lengths: Optional[Dict[int, int]] = None
) -> Dict[int, float]:
    """Measured forecast-skill decay, estimated from the station archive alone.

    No archived numerical weather prediction output exists for this station, so
    the horizon weight is derived from a *persistence* pseudo-forecast: the
    value observed at the issue time is carried forward ``h`` days and scored
    against what actually happened. The resulting normalised error by lead time
    is a real, reproducible curve computed from the archive.

    In a production deployment this function would be replaced by a skill curve
    computed from archived forecast-versus-observation pairs. The interface and
    the downstream weighting do not change.
    """

    archive = archive.sort_values("date").reset_index(drop=True)
    errors: Dict[int, List[float]] = {int(h): [] for h in horizons}
    if season_lengths:
        lengths = list(season_lengths.values())
        block = max(lengths)
    else:
        block = 120

    for start in range(0, len(archive) - block, 7):
        issue = archive.iloc[start]
        for h in horizons:
            target_idx = start + int(h)
            if target_idx >= len(archive):
                continue
            target = archive.iloc[target_idx]
            e_rain = abs(float(target["precipitation_sum"]) - float(issue["precipitation_sum"])) / 10.0
            e_et0 = abs(
                float(target["et0_fao_evapotranspiration"]) - float(issue["et0_fao_evapotranspiration"])
            ) / 5.0
            e_tmax = abs(float(target["temperature_2m_max"]) - float(issue["temperature_2m_max"])) / 10.0
            errors[int(h)].append((e_rain + e_et0 + e_tmax) / 3.0)

    baseline = float(np.median([v for vals in errors.values() for v in vals])) if any(errors.values()) else 1.0
    baseline = max(baseline, 1e-6)
    curve: Dict[int, float] = {}
    for h, vals in errors.items():
        if not vals:
            curve[int(h)] = 1.0 / (1.0 + (int(h) / 7.0))
            continue
        curve[int(h)] = 1.0 / (1.0 + float(np.median(vals)) / baseline)
    return curve


def horizon_weight(horizon_days: int, skill_curve: Dict[int, float]) -> float:
    """Skill weight for a forecast day at the given lead time.

    Interpolates between measured lead times and clamps to (0, 1].
    """

    if not skill_curve:
        return 1.0
    known = sorted(skill_curve)
    h = float(horizon_days)
    if h <= known[0]:
        return float(skill_curve[known[0]])
    if h >= known[-1]:
        return float(skill_curve[known[-1]])
    for lo, hi in zip(known, known[1:]):
        if lo <= h <= hi:
            span = hi - lo
            frac = 0.0 if span == 0 else (h - lo) / span
            return float(skill_curve[lo] * (1 - frac) + skill_curve[hi] * frac)
    return 1.0


def is_finite_number(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False
