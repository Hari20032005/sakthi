"""Counterfactual source degradation over real season records.

The calibration store for degraded provenance states cannot be populated from
nature: a season does not naturally arrive with its weather feed down. The only
way to obtain residuals in those states is to take held-out seasons and
re-run the whole pipeline against the system's own documented fallback chain.

Everything that can be real here is real:

* **Weather is real.** All 4,688 daily records from the Ariyalur station
  archive. Degradation substitutes or reweights real rows.
* **Yield targets are real.** All 36 published district crop-season yields.
* **Vegetation is simulated.** No NDVI time series exists for these farms --
  the production database holds exactly one observed row. The phenology curve
  and the canopy stress response below are constructed, so every result that
  depends on the vegetation axis is a simulation result and is reported as such.
* **Forecast is a persistence pseudo-forecast.** No archived numerical weather
  prediction output exists for this station. Its measured error by lead time is
  what supplies the horizon weights, so the weights are real measurements of a
  weak forecast rather than of the operational forecast a deployment would use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from backend.integrity.provenance import SourceCategory
from backend.integrity.thermal_time import DEFAULT_BASE_TEMPS, accumulate_gdd, daily_gdd
from backend.integrity.vegetation import DEFAULT_LADDER, LadderSample, simulate_ladder

#: Phenology: expected vegetation index as a function of the fraction of the
#: season's total thermal time that has elapsed. Interpolated. Constructed from
#: the six stage reference points already hard-coded in satellite_service.py,
#: re-expressed against accumulated thermal time rather than calendar week.
_PHENOLOGY_CURVE: Dict[str, Sequence[tuple]] = {
    "Rice": ((0.0, 0.10), (0.15, 0.38), (0.35, 0.58), (0.55, 0.76), (0.75, 0.71), (1.0, 0.45)),
    "Cotton(lint)": ((0.0, 0.12), (0.15, 0.34), (0.35, 0.55), (0.55, 0.74), (0.75, 0.68), (1.0, 0.40)),
}

REGIME_LIVE = "live_full"
REGIME_CACHED = "cached_aged"
REGIME_CLIMATOLOGY = "climatology_fallback"
REGIME_FORECAST_SHORT = "forecast_short_horizon"
REGIME_FORECAST_LONG = "forecast_long_horizon"
REGIME_NO_VEG = "no_vegetation"
REGIME_LOW_PIXEL = "low_valid_pixel"
REGIME_RADIUS_DISAGREE = "radius_disagreement"
REGIME_CONFLICT_WEATHER = "conflict_weather_stress_vegetation_normal"
REGIME_CONFLICT_VEG = "conflict_vegetation_decline_weather_normal"

ALL_REGIMES = (
    REGIME_LIVE,
    REGIME_CACHED,
    REGIME_CLIMATOLOGY,
    REGIME_FORECAST_SHORT,
    REGIME_FORECAST_LONG,
    REGIME_NO_VEG,
    REGIME_LOW_PIXEL,
    REGIME_RADIUS_DISAGREE,
    REGIME_CONFLICT_WEATHER,
    REGIME_CONFLICT_VEG,
)

REGIME_WEATHER_CATEGORY = {
    REGIME_LIVE: SourceCategory.LIVE,
    REGIME_CACHED: SourceCategory.CACHED,
    REGIME_CLIMATOLOGY: SourceCategory.HISTORICAL_FALLBACK,
    REGIME_FORECAST_SHORT: SourceCategory.LIVE,
    REGIME_FORECAST_LONG: SourceCategory.LIVE,
    REGIME_NO_VEG: SourceCategory.LIVE,
    REGIME_LOW_PIXEL: SourceCategory.LIVE,
    REGIME_RADIUS_DISAGREE: SourceCategory.LIVE,
    REGIME_CONFLICT_WEATHER: SourceCategory.LIVE,
    REGIME_CONFLICT_VEG: SourceCategory.LIVE,
}

SEASON_RANGES = {
    "Kharif": lambda y: (f"{y}-06-01", f"{y}-10-31"),
    "Rabi": lambda y: (f"{y}-11-01", f"{y+1}-03-31"),
    "Whole Year": lambda y: (f"{y}-01-01", f"{y}-12-31"),
    "Summer": lambda y: (f"{y}-03-01", f"{y}-06-15"),
    "Autumn": lambda y: (f"{y}-08-01", f"{y}-11-30"),
    "Winter": lambda y: (f"{y}-11-01", f"{y+1}-02-28"),
}


def expected_ndvi(crop: str, thermal_fraction: float) -> float:
    curve = _PHENOLOGY_CURVE.get(crop, _PHENOLOGY_CURVE["Rice"])
    xs = [p[0] for p in curve]
    ys = [p[1] for p in curve]
    return float(np.interp(min(max(thermal_fraction, 0.0), 1.0), xs, ys))


@dataclass
class SeasonRecord:
    """One real crop-season with its real daily weather."""

    crop: str
    season: str
    crop_year: int
    yield_t_per_ha: float
    daily: pd.DataFrame
    base_temp_c: float

    @property
    def key(self) -> str:
        return f"{self.crop}|{self.season}|{self.crop_year}"


@dataclass
class DegradedState:
    """The degraded inputs for one season under one regime."""

    observed: pd.DataFrame
    forecast: pd.DataFrame
    weather_category: SourceCategory
    ladder: Optional[List[LadderSample]]
    vegetation_deviation: Optional[float]
    valid_pixel_pct: Optional[float]
    forecast_horizon_days: Optional[int]
    weather_age_days: float
    vegetation_age_days: Optional[float]
    notes: List[str] = field(default_factory=list)


def build_season_records(yield_df: pd.DataFrame, weather: pd.DataFrame) -> List[SeasonRecord]:
    weather = weather.copy()
    weather["date"] = pd.to_datetime(weather["date"])
    records: List[SeasonRecord] = []
    for _, row in yield_df.iterrows():
        season = row["Season"]
        if season not in SEASON_RANGES:
            continue
        start, end = SEASON_RANGES[season](int(row["Crop_Year"]))
        mask = (weather["date"] >= start) & (weather["date"] <= end)
        window = weather.loc[mask].sort_values("date").reset_index(drop=True)
        if len(window) < 30:
            continue
        crop = row["Crop"]
        records.append(
            SeasonRecord(
                crop=crop,
                season=season,
                crop_year=int(row["Crop_Year"]),
                yield_t_per_ha=float(row["Yield"]),
                daily=window,
                base_temp_c=DEFAULT_BASE_TEMPS.get(crop, 10.0),
            )
        )
    return records


def climatology_lookup(weather: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Month-day climatology from the full archive, as the live service does.

    Deliberately pooled across all years, so the fallback has no year
    dimension and therefore carries no interannual spread -- this is the
    weakness that motivates classifying it as degraded provenance.
    """

    frame = weather.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["mmdd"] = frame["date"].dt.strftime("%m-%d")
    grouped = frame.groupby("mmdd").agg(
        tmax=("temperature_2m_max", "mean"),
        tmin=("temperature_2m_min", "mean"),
        rain=("precipitation_sum", "mean"),
        et0=("et0_fao_evapotranspiration", "mean"),
    )
    return grouped.to_dict("index")


def _substitute_climatology(daily: pd.DataFrame, clim: Dict[str, Dict[str, float]]) -> pd.DataFrame:
    out = daily.copy()
    mmdd = pd.to_datetime(out["date"]).dt.strftime("%m-%d")
    out["temperature_2m_max"] = mmdd.map(lambda k: clim.get(k, {}).get("tmax", np.nan))
    out["temperature_2m_min"] = mmdd.map(lambda k: clim.get(k, {}).get("tmin", np.nan))
    out["precipitation_sum"] = mmdd.map(lambda k: clim.get(k, {}).get("rain", 0.0))
    out["et0_fao_evapotranspiration"] = mmdd.map(lambda k: clim.get(k, {}).get("et0", np.nan))
    return out.dropna(subset=["temperature_2m_max", "et0_fao_evapotranspiration"]).reset_index(drop=True)


def _persistence_forecast(daily: pd.DataFrame, horizon: int, issue_at: int) -> pd.DataFrame:
    """Carry the last observed day's values forward for ``horizon`` days."""

    if issue_at >= len(daily):
        return daily.head(0).copy()
    last = daily.iloc[issue_at]
    last_date = pd.Timestamp(daily["date"].iloc[issue_at])
    rows = []
    for step in range(1, horizon + 1):
        rows.append(
            {
                "date": last_date + pd.Timedelta(days=step),
                "temperature_2m_max": float(last["temperature_2m_max"]),
                "temperature_2m_min": float(last["temperature_2m_min"]),
                "precipitation_sum": float(last["precipitation_sum"]),
                "et0_fao_evapotranspiration": float(last["et0_fao_evapotranspiration"]),
            }
        )
    return pd.DataFrame(rows)


def _thermal_fraction(record: SeasonRecord, day_index: int) -> float:
    series = accumulate_gdd(record.daily.iloc[: day_index + 1], record.base_temp_c)
    total = float(accumulate_gdd(record.daily, record.base_temp_c).iloc[-1]) or 1.0
    return min(1.0, float(series.iloc[-1]) / total) if len(series) else 0.0


def _simulated_canopy(record: SeasonRecord, day_index: int, seed: int, stress_gain: float = 1.0) -> float:
    """Simulated vegetation index for the season at ``day_index``.

    A phenology baseline is depressed by the accumulated water-and-heat stress
    of the season so far, plus multiplicative observation noise.
    """

    fraction = _thermal_fraction(record, day_index)
    baseline = expected_ndvi(record.crop, fraction)

    window = record.daily.iloc[: day_index + 1]
    rain = float(window["precipitation_sum"].sum())
    et0 = float(window["et0_fao_evapotranspiration"].sum())
    heat = float((window["temperature_2m_max"] >= 35.0).sum())

    # Reference seasonal demand over the same share of the season.
    share = max(1, day_index + 1)
    ref_rain = float(record.daily["precipitation_sum"].sum()) * (share / len(record.daily))
    ref_et0 = float(record.daily["et0_fao_evapotranspiration"].sum()) * (share / len(record.daily))
    ref_heat = float((record.daily["temperature_2m_max"] >= 35.0).sum()) * (share / len(record.daily))

    water_deficit = max(0.0, (ref_et0 - et0) / max(ref_et0, 1.0))
    water_surplus_deficit = max(0.0, (ref_rain - rain) / max(ref_rain, 1.0))
    heat_stress = max(0.0, (heat - ref_heat)) / 10.0

    penalty = stress_gain * (0.45 * water_deficit + 0.30 * water_surplus_deficit + 0.06 * heat_stress)
    rng = np.random.default_rng(seed)
    noise = float(rng.normal(0.0, 0.018))
    return float(max(0.02, baseline - penalty + noise))


def degrade(
    record: SeasonRecord,
    regime: str,
    clim: Dict[str, Dict[str, float]],
    *,
    observation_fraction: float = 0.55,
    seed: int = 0,
) -> DegradedState:
    """Produce the degraded input state for one season under one regime."""

    n = len(record.daily)
    issue_at = max(1, min(n - 1, int(round(n * observation_fraction))))
    observed = record.daily.iloc[:issue_at].copy().reset_index(drop=True)
    remainder = record.daily.iloc[issue_at:].reset_index(drop=True)

    notes: List[str] = []
    category = REGIME_WEATHER_CATEGORY[regime]

    forecast = _persistence_forecast(record.daily, 7, issue_at)
    horizon = 7

    if regime == REGIME_CACHED:
        # Served from a cache: values are the real observations, but they are
        # stale relative to the query, and no fresh retrieval is possible.
        observed = observed.copy()
        notes.append("weather served from cache; values real but aged")
        age = float(n - issue_at)
    elif regime == REGIME_CLIMATOLOGY:
        observed = _substitute_climatology(observed, clim)
        forecast = _persistence_forecast(
            observed if len(observed) else record.daily, 7, max(0, len(observed) - 1)
        )
        notes.append("observed weather replaced by month-day climatology")
        age = float(n - issue_at)
    elif regime == REGIME_FORECAST_SHORT:
        forecast = _persistence_forecast(record.daily, 7, issue_at)
        horizon = 7
        age = float(n - issue_at)
    elif regime == REGIME_FORECAST_LONG:
        forecast = _persistence_forecast(record.daily, 16, issue_at)
        horizon = 16
        notes.append("forecast horizon extended beyond the 7-day window")
        age = float(n - issue_at)
    else:
        age = float(n - issue_at)

    vegetation_deviation: Optional[float] = None
    ladder: Optional[List[LadderSample]] = None
    valid_pixel: Optional[float] = None
    veg_age: Optional[float] = None

    if regime == REGIME_NO_VEG:
        notes.append("vegetation observation unavailable")
    elif regime == REGIME_LOW_PIXEL:
        observed_ndvi = _simulated_canopy(record, issue_at, seed)
        fraction = _thermal_fraction(record, issue_at)
        deviation = observed_ndvi - expected_ndvi(record.crop, fraction)
        vegetation_deviation = float(deviation)
        valid_pixel = 12.0
        ladder = simulate_ladder(observed_ndvi, 12.0, heterogeneity=0.010, seed=seed + 11)
        veg_age = age
        notes.append("cloud-contaminated observation: 12% valid pixels")
    elif regime == REGIME_RADIUS_DISAGREE:
        observed_ndvi = _simulated_canopy(record, issue_at, seed)
        fraction = _thermal_fraction(record, issue_at)
        vegetation_deviation = float(observed_ndvi - expected_ndvi(record.crop, fraction))
        valid_pixel = 88.0
        # High sub-pixel heterogeneity makes the radius ladder depart from the
        # pure scale trend, which is what the de-trended metric must catch.
        ladder = simulate_ladder(observed_ndvi, 88.0, heterogeneity=0.085, seed=seed + 23)
        veg_age = age
        notes.append("heterogeneous sub-pixel field; ladder departs from the scale trend")
    elif regime == REGIME_CONFLICT_WEATHER:
        # Severe water and heat stress is imposed on the weather side while the
        # canopy is left unstressed, producing a genuine disagreement.
        stressed = observed.copy()
        stressed["precipitation_sum"] = stressed["precipitation_sum"] * 0.25
        stressed["et0_fao_evapotranspiration"] = stressed["et0_fao_evapotranspiration"] * 1.45
        stressed["temperature_2m_max"] = stressed["temperature_2m_max"] + 4.0
        stressed["temperature_2m_min"] = stressed["temperature_2m_min"] + 2.0
        observed = stressed.reset_index(drop=True)
        vegetation_deviation = 0.06
        valid_pixel = 90.0
        ladder = simulate_ladder(
            expected_ndvi(record.crop, _thermal_fraction(record, issue_at)) + 0.06,
            90.0,
            heterogeneity=0.008,
            seed=seed + 37,
        )
        veg_age = age
        notes.append("injected conflict: severe weather stress with a normal canopy")
    elif regime == REGIME_CONFLICT_VEG:
        # A canopy decline is only a *conflict* if the weather record is
        # unremarkable. If the season really was hot and dry, decline and
        # weather agree and no conflict exists. The weather side is therefore
        # damped toward the climatological expectation, so the injected
        # disagreement is genuine by construction rather than by coincidence.
        ref = record.daily.iloc[: max(1, len(observed))]
        damped = observed.copy()
        for col, ref_col, strength in (
            ("precipitation_sum", "precipitation_sum", 0.75),
            ("et0_fao_evapotranspiration", "et0_fao_evapotranspiration", 0.75),
        ):
            damped[col] = observed[col] * (1.0 - strength) + ref[ref_col].mean() * strength
        damped["temperature_2m_max"] = observed["temperature_2m_max"] * 0.4 + ref["temperature_2m_max"].mean() * 0.6
        damped["temperature_2m_min"] = observed["temperature_2m_min"] * 0.4 + ref["temperature_2m_min"].mean() * 0.6
        observed = damped.reset_index(drop=True)

        vegetation_deviation = -0.16
        valid_pixel = 88.0
        ladder = simulate_ladder(
            expected_ndvi(record.crop, _thermal_fraction(record, issue_at)) - 0.16,
            88.0,
            heterogeneity=0.010,
            seed=seed + 41,
        )
        veg_age = age
        notes.append("injected conflict: canopy decline with damped, unremarkable weather")
    else:
        vegetation_deviation = float(
            _simulated_canopy(record, issue_at, seed) - expected_ndvi(record.crop, _thermal_fraction(record, issue_at))
        )
        valid_pixel = 92.0
        ladder = simulate_ladder(
            _simulated_canopy(record, issue_at, seed),
            92.0,
            heterogeneity=0.009,
            seed=seed + 5,
        )
        veg_age = age

    return DegradedState(
        observed=observed,
        forecast=forecast,
        weather_category=category,
        ladder=ladder,
        vegetation_deviation=vegetation_deviation,
        valid_pixel_pct=valid_pixel,
        forecast_horizon_days=horizon,
        weather_age_days=age,
        vegetation_age_days=veg_age,
        notes=notes,
    )
