"""Conservative live-weather overlay for the historic yield baseline.

This is deliberately not a second ML model.  The training set is small, so the
Random Forest remains the forecast baseline and this service only applies a
bounded, inspectable adjustment based on season-to-date weather.
"""

from datetime import datetime

from backend.models.yield_model import yield_forecaster
from backend.services.weather_service import weather_service


class WeatherAdjustmentService:
    """Build a transparent weather-adjusted yield *baseline* for the twin."""

    # A crop season normally covers roughly four months in the supplied data.
    # This is used only to scale historical full-season totals to elapsed days.
    SEASON_LENGTH_DAYS = {"Kharif": 120, "Rabi": 120, "Whole Year": 180}
    MAX_NEGATIVE_ADJUSTMENT = -0.12
    MAX_POSITIVE_ADJUSTMENT = 0.05

    @staticmethod
    def _clamp(value, lower, upper):
        return max(lower, min(upper, value))

    @staticmethod
    def _number(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def build(self, farm_info: dict, baseline_forecast: dict, forecast_days: list) -> dict:
        """Return the weather overlay and its evidence for one farm state."""
        crop = farm_info["primary_crop"]
        season = farm_info["current_season"]
        historic = yield_forecaster.get_baseline_row(crop, season)
        observed = weather_service.get_season_to_date_weather(
            farm_info["latitude"], farm_info["longitude"], farm_info.get("sowing_date")
        )

        forecast_rain = sum(self._number(day.get("rainfall_mm")) for day in forecast_days)
        forecast_et0 = sum(self._number(day.get("et0_mm")) for day in forecast_days)
        forecast_temps = [self._number(day.get("temp_max")) for day in forecast_days if day.get("temp_max") is not None]
        forecast_heat_days = sum(temp >= 35 for temp in forecast_temps)

        observed_days = int(observed.get("days", 0) or 0)
        outlook_days = len(forecast_days)
        covered_days = min(
            observed_days + outlook_days,
            self.SEASON_LENGTH_DAYS.get(season, 120),
        )
        season_days = self.SEASON_LENGTH_DAYS.get(season, 120)
        expected_fraction = covered_days / season_days if season_days else 0

        weather_rain = self._number(observed.get("rainfall_mm")) + forecast_rain
        weather_et0 = self._number(observed.get("et0_mm")) + forecast_et0
        all_temp_days = observed_days + len(forecast_temps)
        weather_avg_max = (
            (self._number(observed.get("avg_temp_max")) * observed_days + sum(forecast_temps)) / all_temp_days
            if all_temp_days else 0.0
        )
        weather_heat_days = int(observed.get("heat_days", 0) or 0) + forecast_heat_days

        expected_rain = self._number(historic.get("total_rainfall_mm")) * expected_fraction
        expected_et0 = self._number(historic.get("total_et0")) * expected_fraction
        historic_max = self._number(historic.get("avg_temp_max"))
        rain_anomaly_pct = ((weather_rain - expected_rain) / expected_rain * 100) if expected_rain > 0 else 0.0
        et0_anomaly_pct = ((weather_et0 - expected_et0) / expected_et0 * 100) if expected_et0 > 0 else 0.0
        temp_anomaly_c = weather_avg_max - historic_max if weather_avg_max else 0.0

        # Small, one-directional penalties avoid overstating weather sensitivity.
        # The RF is not retrained: these are explicit academic rules, kept within
        # -12% to +5% because the available ML evidence for weather is weak.
        rain_effect = self._clamp(rain_anomaly_pct * 0.0012, -0.06, 0.02)
        heat_effect = self._clamp(-max(0.0, temp_anomaly_c) * 0.012 - max(0, weather_heat_days - 3) * 0.002, -0.05, 0.0)
        et0_effect = self._clamp(-max(0.0, et0_anomaly_pct) * 0.0004, -0.03, 0.0)
        adjustment_pct = self._clamp(rain_effect + heat_effect + et0_effect, self.MAX_NEGATIVE_ADJUSTMENT, self.MAX_POSITIVE_ADJUSTMENT)

        baseline_yield = self._number(baseline_forecast.get("predicted_yield_t_per_ha"))
        adjusted_yield = max(0.0, baseline_yield * (1 + adjustment_pct))
        base_margin = self._number(baseline_forecast.get("conformal_interval", {}).get("margin"))
        extra_margin = min(0.60, abs(adjustment_pct) * baseline_yield + (0.15 if observed_days == 0 else 0.0))
        adjusted_margin = base_margin + extra_margin
        is_live_history = observed.get("source") == "Open-Meteo historical weather API"

        return {
            "label": "Weather-adjusted baseline",
            "method": "Bounded season-to-date weather overlay on the historic Random Forest baseline; not a retrained model prediction.",
            "baseline_ml_yield_t_per_ha": round(baseline_yield, 2),
            "weather_adjusted_yield_t_per_ha": round(adjusted_yield, 2),
            "adjustment_pct": round(adjustment_pct * 100, 1),
            "adjustment_t_per_ha": round(adjusted_yield - baseline_yield, 2),
            "interval": {
                "lower_bound": round(max(0.0, adjusted_yield - adjusted_margin), 2),
                "upper_bound": round(adjusted_yield + adjusted_margin, 2),
                "baseline_margin": round(base_margin, 2),
                "additional_weather_margin": round(extra_margin, 2),
                "interpretation": "Baseline 90% interval widened for weather anomaly; it is not a recalibrated 90% prediction interval.",
            },
            "weather_evidence": {
                "source": observed.get("source"),
                "source_status": "live historical weather plus current forecast" if is_live_history else "historical climatology fallback plus current forecast",
                "observed_days_since_sowing": observed_days,
                "forecast_days_included": outlook_days,
                "covered_days": covered_days,
                "season_days_assumed": season_days,
                "weather_to_date_plus_forecast": {
                    "rainfall_mm": round(weather_rain, 1), "et0_mm": round(weather_et0, 1),
                    "avg_temp_max_c": round(weather_avg_max, 1), "heat_days_at_or_above_35c": weather_heat_days,
                },
                "historic_crop_season_expected_for_same_period": {
                    "rainfall_mm": round(expected_rain, 1), "et0_mm": round(expected_et0, 1),
                    "avg_temp_max_c": round(historic_max, 1),
                },
                "anomalies": {
                    "rainfall_pct": round(rain_anomaly_pct, 1), "et0_pct": round(et0_anomaly_pct, 1),
                    "avg_temp_max_c": round(temp_anomaly_c, 1),
                },
            },
            "limitations": [
                "The Random Forest is unchanged and remains the primary historic-data baseline.",
                "Weather effects are intentionally bounded because the training data has limited rows and weak continuous-weather evidence.",
                "Confirm crop condition in the field before management decisions.",
            ],
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }


weather_adjustment_service = WeatherAdjustmentService()
