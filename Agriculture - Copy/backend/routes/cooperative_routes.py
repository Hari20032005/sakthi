from flask import Blueprint, jsonify
from backend.services.farm_repository import farm_repository
from backend.models.yield_model import yield_forecaster
from backend.models.price_model import price_forecaster

cooperative_bp = Blueprint("cooperative", __name__, url_prefix="/api/cooperative")

@cooperative_bp.route("/summary", methods=["GET"])
def get_cooperative_summary():
    farms = farm_repository.list_farms()
    total_farms = len(farms)
    total_hectares = sum(f["size_hectares"] for f in farms)
    
    # Calculate aggregate production
    farm_details = []
    total_expected_tonnes = 0.0
    total_lower_tonnes = 0.0
    total_upper_tonnes = 0.0
    total_revenue_inr = 0.0

    price_rice = price_forecaster.forecast_prices("Rice", months_ahead=3)["forecast"][2]["projected_price"] * 10
    price_cotton = price_forecaster.forecast_prices("Cotton", months_ahead=3)["forecast"][2]["projected_price"] * 10

    for f in farms:
        crop_clean = "Rice" if "rice" in f["primary_crop"].lower() else "Cotton(lint)"
        pred = yield_forecaster.predict(crop_clean, "Kharif")
        y_val = pred["predicted_yield_t_per_ha"]
        c_low = pred["conformal_interval"]["lower_bound"]
        c_high = pred["conformal_interval"]["upper_bound"]
        
        prod = round(y_val * f["size_hectares"], 2)
        prod_low = round(c_low * f["size_hectares"], 2)
        prod_high = round(c_high * f["size_hectares"], 2)
        
        p_tonne = price_rice if "rice" in crop_clean.lower() else price_cotton
        rev = round(prod * p_tonne, 2)

        total_expected_tonnes += prod
        total_lower_tonnes += prod_low
        total_upper_tonnes += prod_high
        total_revenue_inr += rev

        farm_details.append({
            **f,
            "predicted_yield_t_ha": y_val,
            "confidence_range": [c_low, c_high],
            "expected_production_tonnes": prod,
            "estimated_mandi_value_inr": rev,
            "health_status": "Normal" if y_val >= 2.0 else "Low Yield Alert"
        })

    return jsonify({
        "success": True,
        "cooperative_name": "Ariyalur District Farmers Cooperative Federation",
        "district": "Ariyalur",
        "state": "Tamil Nadu",
        "metrics": {
            "enrolled_farms": total_farms,
            "total_cultivated_hectares": round(total_hectares, 1),
            "total_cultivated_acres": round(total_hectares * 2.47105, 1),
            "aggregate_expected_harvest_tonnes": round(total_expected_tonnes, 1),
            "aggregate_harvest_confidence_range": [
                round(total_lower_tonnes, 1),
                round(total_upper_tonnes, 1)
            ],
            "total_estimated_market_value_inr": round(total_revenue_inr, 2),
            "total_estimated_market_value_lakhs": round(total_revenue_inr / 100000, 2)
        },
        "crops_breakdown": {
            "Rice": sum(f["size_hectares"] for f in farms if "rice" in f["primary_crop"].lower()),
            "Cotton": sum(f["size_hectares"] for f in farms if "cotton" in f["primary_crop"].lower())
        },
        "regional_risk_alerts": [
            {
                "level": "INFO",
                "cluster": "Ariyalur Central Mandi",
                "message": "Paddy arrivals expected to peak in 4 weeks. Cooperative storage silos open for booking."
            },
            {
                "level": "CAUTION",
                "cluster": "Sendurai & Udayarpalayam Blocks",
                "message": "Dry spell forecast for upcoming fortnight. Advisory sent to prioritize alternate wetting & drying."
            }
        ],
        "farms": farm_details
    })
