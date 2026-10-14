from flask import Blueprint, request, jsonify

from backend.services.digital_twin import digital_twin_service
from backend.services.farm_repository import farm_repository

recommendation_bp = Blueprint("recommendations", __name__, url_prefix="/api/farms")


@recommendation_bp.route("/<int:farm_id>/recommendations", methods=["GET"])
def get_recommendations(farm_id):
    try:
        twin = digital_twin_service.get_farm_digital_shadow(farm_id)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    return jsonify({"success": True, "recommendations": twin.get("recommendations", [])})


@recommendation_bp.route("/<int:farm_id>/recommendations/<recommendation_id>/complete", methods=["POST"])
def complete_recommendation(farm_id, recommendation_id):
    farm = farm_repository.get_farm(farm_id)
    if not farm:
        return jsonify({"success": False, "error": "Farm not found"}), 404
    data = request.get_json() or {}
    event = farm_repository.log_management_event(
        farm_id=farm_id,
        event_type="recommendation_completed",
        label=data.get("action", recommendation_id),
        details={"recommendation_id": recommendation_id, "note": data.get("note", "")},
    )
    return jsonify({"success": True, "event": event})
