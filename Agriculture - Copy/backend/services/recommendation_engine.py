"""Transparent rule-and-scenario recommendation layer for the academic twin.

Rules identify current risks; the existing scenario engine estimates the
expected impact of actions where a matching simulation is available.  This is
deliberately not a prescription engine: every result includes data status and
an explicit field-verification reminder.
"""
from backend.models.scenario_engine import scenario_simulation_engine


RULE_PROFILE = {
    "dry_spell_7d_mm": 15.0,
    "heat_stress_c": 35.0,
    "low_ndvi": 0.35,
    "wide_yield_interval_t_ha": 2.5,
    "source": "Academic prototype rule profile; thresholds require TNAU/ICAR local validation before field deployment.",
}


class RecommendationEngine:
    @staticmethod
    def _scenario_effect(baseline, candidate):
        if not baseline or not candidate:
            return None
        base_yield = baseline["predicted_yield_t_ha"]
        yield_change = round(candidate["predicted_yield_t_ha"] - base_yield, 2)
        profit_change = round(
            candidate["financial_estimates"]["net_profit_inr"] - baseline["financial_estimates"]["net_profit_inr"], 2
        )
        return {
            "comparison": candidate["label"],
            "yield_change_t_ha": yield_change,
            "profit_change_inr": profit_change,
            "candidate_yield_interval": candidate["confidence_interval"],
        }

    def recommend(self, twin_state):
        crop = twin_state["farm_specs"]["active_crop"]
        season = twin_state["farm_specs"]["active_season"]
        area = twin_state["farm_specs"]["size_hectares"]
        weather = twin_state.get("weather", {}).get("forecast", [])
        satellite = twin_state.get("satellite_vegetation", {})
        forecast = twin_state.get("current_yield_forecast", {})
        total_rain = sum(day.get("rainfall_mm") or 0 for day in weather)
        max_temp = max((day.get("temp_max") or 0 for day in weather), default=0)
        interval = forecast.get("conformal_interval", {})
        interval_width = (interval.get("upper_bound", 0) - interval.get("lower_bound", 0))
        recommendations = []

        # Scenario comparison is only computed when a weather-risk rule needs
        # it. It uses the existing academic simulator, not a new ML claim.
        scenarios = None
        def scenario(label_prefix):
            nonlocal scenarios
            if scenarios is None:
                scenarios = scenario_simulation_engine.run_comparative_simulations(crop, season, area)
            items = scenarios["scenarios"]
            baseline = next((item for item in items if item["label"].startswith("Baseline")), None)
            candidate = next((item for item in items if item["label"].startswith(label_prefix)), None)
            return self._scenario_effect(baseline, candidate)

        if weather and total_rain < RULE_PROFILE["dry_spell_7d_mm"]:
            recommendations.append({
                "id": "water-check", "priority": "HIGH", "rank": 1,
                "action": "Inspect field moisture and plan supplemental irrigation if the root zone is dry.",
                "reason": f"Only {round(total_rain, 1)} mm rain is forecast in the next 7 days, below the academic dry-spell threshold of {RULE_PROFILE['dry_spell_7d_mm']} mm.",
                "expected_effect": scenario("Scenario B:"),
                "confidence": "MODERATE — weather forecast is current; effect is an academic scenario estimate.",
                "data_sources": ["Farm weather forecast", "Scenario B: supplemental micro-irrigation", RULE_PROFILE["source"]],
                "requires_field_verification": True,
            })

        if weather and max_temp >= RULE_PROFILE["heat_stress_c"]:
            recommendations.append({
                "id": "heat-check", "priority": "HIGH", "rank": 2,
                "action": "Inspect for heat stress and avoid unnecessary midday field operations; verify irrigation need in the evening.",
                "reason": f"Forecast maximum temperature reaches {max_temp}°C, meeting the academic heat-alert threshold of {RULE_PROFILE['heat_stress_c']}°C.",
                "expected_effect": None,
                "confidence": "MODERATE — based on forecast weather; no heat-treatment effect is modelled.",
                "data_sources": ["Farm weather forecast", RULE_PROFILE["source"]],
                "requires_field_verification": True,
            })

        if satellite.get("is_live_satellite_observation") and satellite.get("current_ndvi", 1) < RULE_PROFILE["low_ndvi"]:
            recommendations.append({
                "id": "vegetation-check", "priority": "MEDIUM", "rank": 3,
                "action": "Inspect the field for water stress, nutrient deficiency, pest damage, or incomplete canopy cover.",
                "reason": f"Real Sentinel-2 NDVI is {satellite['current_ndvi']}, below the academic attention threshold of {RULE_PROFILE['low_ndvi']}.",
                "expected_effect": None,
                "confidence": "MODERATE — satellite evidence is real, but NDVI alone cannot diagnose a cause.",
                "data_sources": [satellite.get("sensor_source", "Sentinel-2"), "Valid-pixel quality", RULE_PROFILE["source"]],
                "requires_field_verification": True,
            })

        if interval_width >= RULE_PROFILE["wide_yield_interval_t_ha"]:
            recommendations.append({
                "id": "forecast-verify", "priority": "MEDIUM", "rank": 4,
                "action": "Use the forecast as a planning range and verify crop condition in the field before committing high-cost inputs.",
                "reason": f"The 90% yield interval spans {round(interval_width, 2)} t/ha, indicating material forecast uncertainty.",
                "expected_effect": None,
                "confidence": "HIGH — directly derived from the model's reported uncertainty interval.",
                "data_sources": ["Yield model conformal interval"],
                "requires_field_verification": True,
            })

        if not recommendations:
            recommendations.append({
                "id": "monitor-normal", "priority": "LOW", "rank": 1,
                "action": "Continue routine crop monitoring and synchronize the twin after a material weather or field change.",
                "reason": "No current academic weather, real-NDVI, or uncertainty trigger exceeded its configured threshold.",
                "expected_effect": None,
                "confidence": "MODERATE — absence of an alert is not proof of absence of a field issue.",
                "data_sources": ["Current twin state", RULE_PROFILE["source"]],
                "requires_field_verification": True,
            })
        return sorted(recommendations, key=lambda item: item["rank"])


recommendation_engine = RecommendationEngine()
