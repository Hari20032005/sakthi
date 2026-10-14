from flask import Blueprint, request, jsonify
from backend.models.scenario_engine import scenario_simulation_engine

scenario_bp = Blueprint("scenarios", __name__, url_prefix="/api/scenarios")

@scenario_bp.route("/simulate", methods=["POST"])
def simulate():
    data = request.get_json() or {}
    crop = data.get("crop", "Rice")
    season = data.get("season", "Kharif")
    try:
        area_ha = float(data.get("area_ha", data.get("area", 2.0)))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Farm area must be a valid positive number."}), 400

    if area_ha <= 0:
        return jsonify({"success": False, "error": "Farm area must be greater than 0 hectares."}), 400

    custom_overrides = data.get("custom_scenario", None)
    if custom_overrides is not None:
        try:
            rain_anom = float(custom_overrides.get("rainfall_anomaly", 0.0))
            if rain_anom < -50 or rain_anom > 50:
                return jsonify({"success": False, "error": "Rainfall anomaly must be between -50% and +50%."}), 400
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Rainfall anomaly must be a valid number between -50% and +50%."}), 400

        try:
            temp_anom = float(custom_overrides.get("temperature_anomaly", 0.0))
            if temp_anom < -2 or temp_anom > 5:
                return jsonify({"success": False, "error": "Temperature anomaly must be between -2°C and +5°C."}), 400
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Temperature anomaly must be a valid number between -2°C and +5°C."}), 400

    try:
        comparison = scenario_simulation_engine.run_comparative_simulations(
            crop=crop,
            season=season,
            area_ha=area_ha,
            custom_overrides=custom_overrides
        )
        return jsonify({"success": True, "simulation": comparison})
    except Exception as e:
        return jsonify({"success": False, "error": f"Scenario simulation failed: {str(e)}"}), 500

@scenario_bp.route("/custom", methods=["POST"])
def simulate_custom():
    data = request.get_json() or {}
    crop = data.get("crop", "Rice")
    season = data.get("season", "Kharif")
    try:
        area_ha = float(data.get("area_ha", data.get("area", 2.0)))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Farm area must be a valid positive number."}), 400

    if area_ha <= 0:
        return jsonify({"success": False, "error": "Farm area must be greater than 0 hectares."}), 400

    try:
        rain_anom = float(data.get("rainfall_anomaly", 0.0))
        if rain_anom < -50 or rain_anom > 50:
            return jsonify({"success": False, "error": "Rainfall anomaly must be between -50% and +50%."}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Rainfall anomaly must be a valid number between -50% and +50%."}), 400

    try:
        temp_anom = float(data.get("temperature_anomaly", 0.0))
        if temp_anom < -2 or temp_anom > 5:
            return jsonify({"success": False, "error": "Temperature anomaly must be between -2°C and +5°C."}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Temperature anomaly must be a valid number between -2°C and +5°C."}), 400

    try:
        res = scenario_simulation_engine.simulate_custom_scenario(
            crop=crop,
            season=season,
            area_ha=area_ha,
            rainfall_anomaly=rain_anom,
            temperature_anomaly=temp_anom
        )
        return jsonify({
            "success": True,
            "custom_scenario": res["custom_scenario"],
            "baseline": res["baseline"],
            "difference_from_baseline": res["difference_from_baseline"]
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Custom scenario simulation failed: {str(e)}"}), 500

@scenario_bp.route("/single", methods=["POST"])
def simulate_single():
    data = request.get_json() or {}
    label = data.get("label", "Custom What-If Scenario")
    crop = data.get("crop", "Rice")
    season = data.get("season", "Kharif")
    area_ha = float(data.get("area_ha", 2.0))
    overrides = data.get("overrides", {})

    result = scenario_simulation_engine.simulate_scenario(
        label=label,
        crop=crop,
        season=season,
        area_ha=area_ha,
        overrides=overrides
    )

    return jsonify({"success": True, "scenario_result": result})
