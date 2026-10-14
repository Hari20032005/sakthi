from flask import Blueprint, request, jsonify
from backend.models.shap_engine import shap_engine

explain_bp = Blueprint("explain", __name__, url_prefix="/api/explain")

@explain_bp.route("/global", methods=["GET"])
def global_importance():
    top_n = int(request.args.get("top_n", 8))
    importance = shap_engine.get_global_importance(top_n=top_n)
    return jsonify({"success": True, "global_importance": importance})

@explain_bp.route("/prediction", methods=["POST"])
def explain_prediction():
    data = request.get_json() or {}
    crop = data.get("crop", "Rice")
    season = data.get("season", "Kharif")
    overrides = data.get("overrides", {})
    top_k = int(data.get("top_k", 5))

    explanation = shap_engine.explain_prediction(
        crop=crop,
        season=season,
        overrides=overrides,
        top_k=top_k
    )
    return jsonify({"success": True, "explanation": explanation})
