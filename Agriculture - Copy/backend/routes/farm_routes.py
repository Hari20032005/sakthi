from flask import Blueprint, request, jsonify
from backend.services.digital_twin import digital_twin_service
from backend.services.farm_repository import farm_repository, INITIAL_FARMS

farm_bp = Blueprint("farms", __name__, url_prefix="/api/farms")

# Backward-compatible name for any external academic material that imports it.
DEMO_FARMS = INITIAL_FARMS

@farm_bp.route("", methods=["GET"])
def get_farms():
    return jsonify({"success": True, "farms": farm_repository.list_farms()})

@farm_bp.route("/<int:farm_id>", methods=["GET"])
def get_farm(farm_id):
    farm = farm_repository.get_farm(farm_id)
    if farm:
        return jsonify({"success": True, "farm": farm})
    return jsonify({"success": False, "error": "Farm not found"}), 404

@farm_bp.route("/<int:farm_id>/digital-shadow", methods=["GET"])
def get_digital_shadow(farm_id):
    try:
        shadow = digital_twin_service.get_farm_digital_shadow(farm_id)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    return jsonify({"success": True, "digital_shadow": shadow})

@farm_bp.route("/<int:farm_id>/digital-shadow/history", methods=["GET"])
def get_digital_shadow_history(farm_id):
    if not farm_repository.get_farm(farm_id):
        return jsonify({"success": False, "error": "Farm not found"}), 404
    return jsonify({"success": True, "snapshots": farm_repository.recent_snapshots(farm_id)})

@farm_bp.route("/<int:farm_id>/weather-adjusted-yield", methods=["GET"])
def get_weather_adjusted_yield(farm_id):
    """Expose the labelled weather overlay without presenting it as retrained ML."""
    try:
        shadow = digital_twin_service.get_farm_digital_shadow(farm_id)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    return jsonify({"success": True, "weather_adjusted_yield": shadow["weather_adjusted_yield_forecast"]})

@farm_bp.route("", methods=["POST"])
def create_farm():
    data = request.get_json() or {}
    try:
        new_farm = {
        "owner_id": data.get("owner_id", 1),
        "owner_name": data.get("owner_name", "Farmer"),
        "farm_name": data.get("farm_name", "New Farm Plot"),
        "latitude": float(data.get("latitude", 11.140)),
        "longitude": float(data.get("longitude", 79.080)),
        "district": data.get("district", "Ariyalur"),
        "state": "Tamil Nadu",
        "size_hectares": float(data.get("size_hectares", 2.0)),
        "soil_type": data.get("soil_type", "Clay loam"),
        "primary_crop": data.get("primary_crop", "Rice"),
        "current_season": data.get("current_season", "Kharif"),
        "sowing_date": data.get("sowing_date", "2026-06-15")
        }
        if not (-90 <= new_farm["latitude"] <= 90 and -180 <= new_farm["longitude"] <= 180):
            raise ValueError("Latitude or longitude is outside its valid range.")
        if new_farm["size_hectares"] <= 0:
            raise ValueError("Farm size must be greater than zero.")
    except (TypeError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    new_farm = farm_repository.create_farm(new_farm)
    return jsonify({"success": True, "farm": new_farm}), 201
