from flask import Blueprint, request, jsonify
from backend.models.yield_model import yield_forecaster
from backend.models.price_model import price_forecaster
from backend.models.deep_model import deep_evaluator

forecast_bp = Blueprint("forecast", __name__, url_prefix="/api/forecast")

@forecast_bp.route("/yield", methods=["POST"])
def predict_yield():
    data = request.get_json() or {}
    crop = data.get("crop", "Rice")
    season = data.get("season", "Kharif")
    overrides = data.get("overrides", {})

    result = yield_forecaster.predict(crop, season, overrides)
    return jsonify({"success": True, "forecast": result})

@forecast_bp.route("/price", methods=["GET"])
def predict_price():
    crop = request.args.get("crop", "Rice")
    months = int(request.args.get("months", 6))

    result = price_forecaster.forecast_prices(crop, months_ahead=months)
    return jsonify({"success": True, "price_forecast": result})

@forecast_bp.route("/benchmark", methods=["GET"])
def model_benchmark():
    # Return LOOCV evaluation metrics comparing RF, GB, and notes on Deep Learning
    metrics = yield_forecaster.loocv_metrics
    return jsonify({
        "success": True,
        "methodology": "Leave-One-Out Cross-Validation (LOOCV)",
        "benchmarks": metrics,
        "deep_learning_note": "LSTM / Transformer architectures were implemented and evaluated; tree-based ensembles (Random Forest / Gradient Boosting) paired with Conformal Prediction demonstrate lower error and rigorous finite-sample coverage on small tabular agricultural records."
    })
