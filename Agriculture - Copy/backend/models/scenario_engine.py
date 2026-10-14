from backend.models.yield_model import yield_forecaster
from backend.models.price_model import price_forecaster
from backend.models.shap_engine import shap_engine

# Agronomic cultivation cost estimates per hectare (Tamil Nadu agricultural department benchmarks)
ESTIMATED_INPUT_COST_PER_HA = {
    "Rice": 38000.0,    # Seed, SRI labor, nursery, fertilization, irrigation, harvest
    "Cotton": 42000.0,  # Bt seed, pest management, weeding, picking
    "Cotton(lint)": 42000.0
}

class ScenarioSimulationEngine:
    def __init__(self, forecaster=yield_forecaster):
        self.forecaster = forecaster

    def simulate_scenario(self, label: str, crop: str, season: str, area_ha: float = 2.0, overrides: dict = None):
        prediction = self.forecaster.predict(crop, season, overrides)
        yield_val = prediction["predicted_yield_t_per_ha"]
        conf_interval = prediction["conformal_interval"]

        # Production calculation
        production_tonnes = round(yield_val * area_ha, 2)
        production_lower = round(conf_interval["lower_bound"] * area_ha, 2)
        production_upper = round(conf_interval["upper_bound"] * area_ha, 2)

        # Financial modeling based on forecasted commodity price
        price_crop = "Rice" if "rice" in crop.lower() else "Cotton"
        price_info = price_forecaster.forecast_prices(price_crop, months_ahead=3)
        expected_price_per_quintal = price_info["forecast"][2]["projected_price"] # 3-month forecast
        price_per_tonne = expected_price_per_quintal * 10.0 # 1 tonne = 10 quintals

        gross_revenue = round(production_tonnes * price_per_tonne, 2)
        input_cost = round(ESTIMATED_INPUT_COST_PER_HA.get(crop, 38000.0) * area_ha, 2)
        net_profit = round(gross_revenue - input_cost, 2)

        # Risk scoring
        interval_spread = conf_interval["upper_bound"] - conf_interval["lower_bound"]
        if interval_spread > 1.8 or yield_val < 1.0:
            risk_level = "High Uncertainty / Stress"
        elif interval_spread > 1.0:
            risk_level = "Moderate Risk"
        else:
            risk_level = "Low Risk / Stable"

        # Feature explanation for this scenario
        explanation = shap_engine.explain_prediction(crop, season, overrides, top_k=3)

        return {
            "label": label,
            "crop": crop,
            "season": season,
            "farm_area_ha": area_ha,
            "overrides": overrides or {},
            "predicted_yield_t_ha": yield_val,
            "confidence_interval": {
                "lower": conf_interval["lower_bound"],
                "upper": conf_interval["upper_bound"],
                "confidence": conf_interval["confidence_level"]
            },
            "expected_production_tonnes": {
                "expected": production_tonnes,
                "lower": production_lower,
                "upper": production_upper
            },
            "financial_estimates": {
                "projected_mandi_price_quintal": expected_price_per_quintal,
                "gross_revenue_inr": gross_revenue,
                "estimated_input_cost_inr": input_cost,
                "net_profit_inr": net_profit,
                "profit_margin_pct": round((net_profit / gross_revenue * 100), 1) if gross_revenue > 0 else 0
            },
            "risk_assessment": risk_level,
            "key_driving_factors": explanation["top_factors"],
            "explanation_text": explanation["plain_language_explanation"]
        }

    def compute_anomaly_overrides(self, baseline_row: dict, rainfall_anomaly: float = 0.0, temperature_anomaly: float = 0.0) -> dict:
        """
        Derive physically sound weather feature overrides from user-selected anomalies.
        Rainfall anomaly is in percent (-50% to +50%).
        Temperature anomaly is in degrees Celsius (-2°C to +5°C).
        """
        base_rainfall = baseline_row.get("total_rainfall_mm", 459.88)
        base_temp_mean = baseline_row.get("avg_temp_mean", 29.55)
        base_temp_max = baseline_row.get("avg_temp_max", 34.70)
        base_temp_min = baseline_row.get("avg_temp_min", 25.76)
        base_et0 = baseline_row.get("total_et0", 796.09)

        # Scale seasonal rainfall
        new_rainfall = max(0.0, base_rainfall * (1.0 + (rainfall_anomaly / 100.0)))

        # Shift thermal regime across mean, max, and min
        new_temp_mean = base_temp_mean + temperature_anomaly
        new_temp_max = base_temp_max + temperature_anomaly
        new_temp_min = base_temp_min + temperature_anomaly

        # Reference evapotranspiration ET0 adjustment (FAO-56 agrometeorological scaling)
        # Higher temperatures and lower rainfall increase atmospheric evaporative demand
        et0_temp_factor = 0.025 * temperature_anomaly
        et0_rain_factor = -0.0015 * rainfall_anomaly
        new_et0 = max(100.0, base_et0 * (1.0 + et0_temp_factor + et0_rain_factor))

        return {
            "total_rainfall_mm": round(new_rainfall, 2),
            "avg_temp_mean": round(new_temp_mean, 2),
            "avg_temp_max": round(new_temp_max, 2),
            "avg_temp_min": round(new_temp_min, 2),
            "total_et0": round(new_et0, 2)
        }

    def simulate_custom_scenario(self, crop: str = "Rice", season: str = "Kharif", area_ha: float = 2.0, rainfall_anomaly: float = 0.0, temperature_anomaly: float = 0.0):
        """Simulate a single custom scenario with explicit anomaly inputs and comparison to baseline."""
        baseline_row = self.forecaster.get_baseline_row(crop, season)
        overrides = self.compute_anomaly_overrides(baseline_row, rainfall_anomaly, temperature_anomaly)

        baseline_result = self.simulate_scenario(
            label="Baseline (Normal Historical Conditions)",
            crop=crop,
            season=season,
            area_ha=area_ha,
            overrides={}
        )

        custom_result = self.simulate_scenario(
            label="Custom Farmer What-If Scenario",
            crop=crop,
            season=season,
            area_ha=area_ha,
            overrides=overrides
        )
        custom_result["rainfall_anomaly"] = rainfall_anomaly
        custom_result["temperature_anomaly"] = temperature_anomaly

        base_yield = baseline_result["predicted_yield_t_ha"]
        base_profit = baseline_result["financial_estimates"]["net_profit_inr"]
        yield_diff = round(custom_result["predicted_yield_t_ha"] - base_yield, 2)
        yield_pct = round(((custom_result["predicted_yield_t_ha"] / base_yield) - 1.0) * 100, 1) if base_yield > 0 else 0.0
        profit_diff = round(custom_result["financial_estimates"]["net_profit_inr"] - base_profit, 2)
        profit_pct = round(((custom_result["financial_estimates"]["net_profit_inr"] / base_profit) - 1.0) * 100, 1) if base_profit != 0 else 0.0

        diff = {
            "yield_diff_t_ha": yield_diff,
            "yield_change_pct": yield_pct,
            "profit_diff_inr": profit_diff,
            "profit_change_pct": profit_pct
        }
        custom_result["difference_from_baseline"] = diff

        return {
            "baseline": baseline_result,
            "custom_scenario": custom_result,
            "difference_from_baseline": diff
        }

    def run_comparative_simulations(self, crop: str, season: str, area_ha: float = 2.0, custom_overrides: dict = None):
        """Simulate 4 structured real-world scenarios side-by-side, plus user-defined custom scenario."""
        baseline_row = self.forecaster.get_baseline_row(crop, season)
        base_rainfall = baseline_row.get("total_rainfall_mm", 600.0)
        base_temp = baseline_row.get("avg_temp_mean", 28.5)
        base_et0 = baseline_row.get("total_et0", 750.0)

        results = []

        # 1. Baseline
        baseline_sim = self.simulate_scenario(
            label="Baseline (Normal Historical Conditions)",
            crop=crop,
            season=season,
            area_ha=area_ha,
            overrides={}
        )
        results.append(baseline_sim)

        # 2. Drought Shock (-35% Monsoon Deficit)
        drought_overrides = {
            "total_rainfall_mm": base_rainfall * 0.65,
            "avg_temp_max": base_temp + 1.8,
            "total_et0": base_et0 * 1.12
        }
        results.append(self.simulate_scenario(
            label="Scenario A: Drought Deficit (-35% Rainfall)",
            crop=crop,
            season=season,
            area_ha=area_ha,
            overrides=drought_overrides
        ))

        # 3. Supplemental Micro-Irrigation (+25% Water Availability)
        irrigation_overrides = {
            "total_rainfall_mm": base_rainfall * 1.25,
            "total_et0": base_et0 * 0.95
        }
        results.append(self.simulate_scenario(
            label="Scenario B: Supplemental Micro-Irrigation (+25% Water)",
            crop=crop,
            season=season,
            area_ha=area_ha,
            overrides=irrigation_overrides
        ))

        # 4. Delayed Sowing (+2°C Heat Exposure, Shorter Window)
        delay_overrides = {
            "total_rainfall_mm": base_rainfall * 0.85,
            "avg_temp_mean": base_temp + 2.2,
            "avg_temp_max": base_temp + 3.0,
            "total_et0": base_et0 * 1.15
        }
        results.append(self.simulate_scenario(
            label="Scenario C: Delayed Sowing by 3 Weeks (Heat Exposure)",
            crop=crop,
            season=season,
            area_ha=area_ha,
            overrides=delay_overrides
        ))

        # 5. Alternate Crop Comparison (Rice vs Cotton)
        alt_crop = "Cotton(lint)" if "rice" in crop.lower() else "Rice"
        results.append(self.simulate_scenario(
            label=f"Scenario D: Switch Crop to {alt_crop}",
            crop=alt_crop,
            season=season,
            area_ha=area_ha,
            overrides={}
        ))

        # 6. Custom Scenario if user provided overrides
        custom_result = None
        if custom_overrides is not None:
            c_crop = custom_overrides.get("crop", crop)
            c_season = custom_overrides.get("season", season)
            c_area = float(custom_overrides.get("area_ha", custom_overrides.get("area", area_ha)))

            rain_anom = float(custom_overrides.get("rainfall_anomaly", 0.0))
            temp_anom = float(custom_overrides.get("temperature_anomaly", 0.0))

            if "parameters" in custom_overrides and custom_overrides["parameters"]:
                overrides = custom_overrides["parameters"]
            else:
                c_baseline = self.forecaster.get_baseline_row(c_crop, c_season)
                overrides = self.compute_anomaly_overrides(c_baseline, rain_anom, temp_anom)

            custom_sim = self.simulate_scenario(
                label="Custom Farmer What-If Scenario",
                crop=c_crop,
                season=c_season,
                area_ha=c_area,
                overrides=overrides
            )
            custom_sim["rainfall_anomaly"] = rain_anom
            custom_sim["temperature_anomaly"] = temp_anom

            # Compute difference from baseline
            base_yield = baseline_sim["predicted_yield_t_ha"]
            base_profit = baseline_sim["financial_estimates"]["net_profit_inr"]
            yield_diff = round(custom_sim["predicted_yield_t_ha"] - base_yield, 2)
            yield_pct = round(((custom_sim["predicted_yield_t_ha"] / base_yield) - 1.0) * 100, 1) if base_yield > 0 else 0.0
            profit_diff = round(custom_sim["financial_estimates"]["net_profit_inr"] - base_profit, 2)
            profit_pct = round(((custom_sim["financial_estimates"]["net_profit_inr"] / base_profit) - 1.0) * 100, 1) if base_profit != 0 else 0.0

            custom_sim["difference_from_baseline"] = {
                "yield_diff_t_ha": yield_diff,
                "yield_change_pct": yield_pct,
                "profit_diff_inr": profit_diff,
                "profit_change_pct": profit_pct
            }
            results.append(custom_sim)
            custom_result = custom_sim

        return {
            "crop": crop,
            "season": season,
            "farm_area_ha": area_ha,
            "scenarios": results,
            "custom_scenario": custom_result
        }

scenario_simulation_engine = ScenarioSimulationEngine()
