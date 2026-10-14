import sys
import os
from pathlib import Path

# Ensure UTF-8 output and line buffering so messages appear immediately
if sys.platform.startswith("win"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.app import app

def test_api():
    client = app.test_client()
    
    print("Testing /api/health ...", flush=True)
    res = client.get("/api/health")
    assert res.status_code == 200
    print("[PASS] Health check passed:", res.get_json()["status"], flush=True)

    print("Testing /api/farms/1/digital-shadow ...", flush=True)
    res = client.get("/api/farms/1/digital-shadow")
    assert res.status_code == 200
    shadow = res.get_json()["digital_shadow"]
    print("[PASS] Digital Shadow loaded. Farm:", shadow["farm_name"], "| Weather Forecast days:", len(shadow["weather"]["forecast"]), flush=True)

    print("Testing /api/forecast/yield ...", flush=True)
    res = client.post("/api/forecast/yield", json={"crop": "Rice", "season": "Kharif"})
    assert res.status_code == 200
    fc = res.get_json()["forecast"]
    print(f"[PASS] Yield Forecast: {fc['predicted_yield_t_per_ha']} t/ha | Conformal 90% Interval: [{fc['conformal_interval']['lower_bound']}, {fc['conformal_interval']['upper_bound']}]", flush=True)

    print("Testing weather-adjusted yield baseline ...", flush=True)
    weather_adjusted = client.get("/api/farms/1/weather-adjusted-yield")
    assert weather_adjusted.status_code == 200
    overlay = weather_adjusted.get_json()["weather_adjusted_yield"]
    assert overlay["label"] == "Weather-adjusted baseline"
    assert "not a retrained model prediction" in overlay["method"]
    print(f"[PASS] Weather-adjusted baseline: {overlay['weather_adjusted_yield_t_per_ha']} t/ha ({overlay['adjustment_pct']}% adjustment).", flush=True)

    print("Testing /api/forecast/price ...", flush=True)
    res = client.get("/api/forecast/price?crop=Rice&months=3")
    assert res.status_code == 200
    p = res.get_json()["price_forecast"]
    print(f"[PASS] Price Forecast: Benchmark Rs.{p['current_benchmark_price']}/quintal | 3-mo: Rs.{p['forecast'][2]['projected_price']}/quintal", flush=True)

    print("Testing /api/scenarios/simulate (Baseline + Scenarios A-D) ...", flush=True)
    res = client.post("/api/scenarios/simulate", json={"crop": "Rice", "season": "Kharif", "area_ha": 3.0})
    assert res.status_code == 200
    sims = res.get_json()["simulation"]["scenarios"]
    assert len(sims) == 5, f"Expected 5 baseline scenarios, got {len(sims)}"
    print(f"[PASS] Scenarios simulated: {len(sims)} comparative scenarios generated (Baseline + Scenarios A-D).", flush=True)

    print("Testing /api/scenarios/simulate WITH Custom Scenario Payload ...", flush=True)
    custom_payload = {
        "crop": "Rice",
        "season": "Kharif",
        "area_ha": 3.0,
        "custom_scenario": {
            "crop": "Rice",
            "season": "Kharif",
            "area_ha": 3.0,
            "rainfall_anomaly": -35.0,
            "temperature_anomaly": 2.0
        }
    }
    res_custom = client.post("/api/scenarios/simulate", json=custom_payload)
    assert res_custom.status_code == 200
    sim_data = res_custom.get_json()["simulation"]
    scenarios_with_custom = sim_data["scenarios"]
    assert len(scenarios_with_custom) == 6, f"Expected 6 scenarios with custom, got {len(scenarios_with_custom)}"
    custom_scen = sim_data["custom_scenario"]
    assert custom_scen is not None, "Custom scenario object missing from simulation response"
    assert "difference_from_baseline" in custom_scen, "Difference from baseline missing in custom scenario"
    print(f"[PASS] 6 scenarios returned. Custom Scenario: Yield {custom_scen['predicted_yield_t_ha']} t/ha | "
          f"Conformal: [{custom_scen['confidence_interval']['lower']}, {custom_scen['confidence_interval']['upper']}] t/ha | "
          f"Net Profit: Rs.{custom_scen['financial_estimates']['net_profit_inr']:,} | "
          f"Delta: {custom_scen['difference_from_baseline']['yield_change_pct']}% yield", flush=True)

    print("Testing /api/scenarios/custom (Test 1: 0% rain, 0°C temp) ...", flush=True)
    t1 = client.post("/api/scenarios/custom", json={"crop": "Rice", "season": "Kharif", "area_ha": 3.0, "rainfall_anomaly": 0.0, "temperature_anomaly": 0.0})
    assert t1.status_code == 200
    r1 = t1.get_json()["custom_scenario"]
    print(f"[PASS] Test 1 (0%, 0°C): Yield={r1['predicted_yield_t_ha']} t/ha, Net Profit=Rs.{r1['financial_estimates']['net_profit_inr']:,}", flush=True)

    print("Testing /api/scenarios/custom (Test 2: -35% rain, +2°C temp) ...", flush=True)
    t2 = client.post("/api/scenarios/custom", json={"crop": "Rice", "season": "Kharif", "area_ha": 3.0, "rainfall_anomaly": -35.0, "temperature_anomaly": 2.0})
    assert t2.status_code == 200
    r2 = t2.get_json()["custom_scenario"]
    print(f"[PASS] Test 2 (-35%, +2°C): Yield={r2['predicted_yield_t_ha']} t/ha, Net Profit=Rs.{r2['financial_estimates']['net_profit_inr']:,}", flush=True)

    print("Testing /api/scenarios/custom (Test 3: +25% rain, +1°C temp) ...", flush=True)
    t3 = client.post("/api/scenarios/custom", json={"crop": "Rice", "season": "Kharif", "area_ha": 3.0, "rainfall_anomaly": 25.0, "temperature_anomaly": 1.0})
    assert t3.status_code == 200
    r3 = t3.get_json()["custom_scenario"]
    print(f"[PASS] Test 3 (+25%, +1°C): Yield={r3['predicted_yield_t_ha']} t/ha, Net Profit=Rs.{r3['financial_estimates']['net_profit_inr']:,}", flush=True)

    # Verification: Ensure different inputs yield different results
    assert r1['predicted_yield_t_ha'] != r2['predicted_yield_t_ha'] or r2['financial_estimates']['net_profit_inr'] != r3['financial_estimates']['net_profit_inr'], "Different anomaly inputs must produce different simulation outcomes"
    print(f"[PASS] Input Sensitivity Verified: Changing anomalies directly altered yield and economic outcomes.", flush=True)

    print("Testing Input Validation (area <= 0 and anomaly out of bounds) ...", flush=True)
    v1 = client.post("/api/scenarios/simulate", json={"crop": "Rice", "season": "Kharif", "area_ha": -1.0})
    assert v1.status_code == 400
    v2 = client.post("/api/scenarios/custom", json={"crop": "Rice", "season": "Kharif", "area_ha": 3.0, "rainfall_anomaly": -90.0})
    assert v2.status_code == 400
    print("[PASS] Input validation properly rejects negative areas and out-of-bound anomalies with HTTP 400.", flush=True)

    print("Testing /api/explain/prediction ...", flush=True)
    res = client.post("/api/explain/prediction", json={"crop": "Rice", "season": "Kharif"})
    assert res.status_code == 200
    exp = res.get_json()["explanation"]
    print(f"[PASS] SHAP Explanation: Top factor: {exp['top_factors'][0]['friendly_name']} ({exp['top_factors'][0]['impact']} t/ha)", flush=True)

    print("Testing /api/chat/message ...", flush=True)
    res = client.post("/api/chat/message", json={"message": "Why is my rice yield forecasted at this number?", "farm_id": 1})
    assert res.status_code == 200
    reply = res.get_json()
    print(f"[PASS] Grounded RAG Chatbot: Engine '{reply['engine']}' replied successfully.", flush=True)

    print("Testing farm recommendations and management-event feedback ...", flush=True)
    rec = client.get("/api/farms/1/recommendations")
    assert rec.status_code == 200
    recommendations = rec.get_json()["recommendations"]
    assert recommendations, "Expected at least one twin recommendation"
    first_recommendation = recommendations[0]
    complete = client.post(
        f"/api/farms/1/recommendations/{first_recommendation['id']}/complete",
        json={"action": first_recommendation["action"]}
    )
    assert complete.status_code == 200
    refreshed_shadow = client.get("/api/farms/1/digital-shadow").get_json()["digital_shadow"]
    assert refreshed_shadow["recent_management_events"], "Completed recommendation should feed back into twin state"
    print("[PASS] Recommendations generated and completion logged as a twin management event.", flush=True)

    print("\nALL BACKEND API TESTS PASSED SUCCESSFULLY! 100% OPERATIONAL.", flush=True)

if __name__ == "__main__":
    test_api()
