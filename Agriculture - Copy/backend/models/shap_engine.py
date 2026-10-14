import numpy as np
import pandas as pd
import shap
from backend.models.yield_model import yield_forecaster

FEATURE_FRIENDLY_NAMES = {
    "total_rainfall_mm": "Seasonal Rainfall",
    "avg_temp_max": "Maximum Daytime Temperature",
    "avg_temp_min": "Minimum Nighttime Temperature",
    "avg_temp_mean": "Mean Temperature",
    "total_et0": "Evapotranspiration (Water Demand)",
    "avg_wind_speed": "Wind Speed",
    "avg_modal_price": "Mandi Market Price",
    "price_volatility": "Price Volatility",
    "Crop_Rice": "Crop Variety: Rice",
    "Crop_Cotton(lint)": "Crop Variety: Cotton",
    "Season_Kharif": "Kharif Monsoon Season",
    "Season_Rabi": "Rabi Winter Season",
    "Season_Whole Year": "Whole Year Cycle",
    "Area": "Cultivated Land Area",
    "Crop_Year": "Climate Cycle Year"
}

class ShapExplainEngine:
    def __init__(self, forecaster=yield_forecaster):
        self.forecaster = forecaster
        self.explainer = None
        self.base_value = None
        self.initialize_explainer()

    def initialize_explainer(self):
        if self.forecaster.rf_model is not None:
            self.explainer = shap.TreeExplainer(self.forecaster.rf_model)
            base_val = self.explainer.expected_value
            if isinstance(base_val, (list, np.ndarray)):
                self.base_value = float(base_val[0])
            else:
                self.base_value = float(base_val)

    def get_global_importance(self, top_n: int = 8):
        if self.explainer is None:
            self.initialize_explainer()

        X_df = self.forecaster.build_features(self.forecaster.df)
        X = X_df.values.astype(float)
        shap_vals = self.explainer.shap_values(X)
        mean_abs_shap = np.abs(shap_vals).mean(axis=0)

        importance_list = []
        for name, score in zip(self.forecaster.feature_names, mean_abs_shap):
            friendly = FEATURE_FRIENDLY_NAMES.get(name, name)
            importance_list.append({
                "feature": name,
                "friendly_name": friendly,
                "importance_score": round(float(score), 4)
            })

        importance_list.sort(key=lambda x: x["importance_score"], reverse=True)
        return {
            "baseline_mean_yield": round(self.base_value, 2),
            "top_features": importance_list[:top_n]
        }

    def explain_prediction(self, crop: str, season: str, overrides: dict = None, top_k: int = 5):
        if self.explainer is None:
            self.initialize_explainer()

        baseline = self.forecaster.get_baseline_row(crop, season)
        x_vec = self.forecaster.build_input_vector(baseline, overrides)
        
        # Exact SHAP attributions
        shap_vals = self.explainer.shap_values(x_vec.reshape(1, -1))[0]
        actual_pred = float(self.forecaster.rf_model.predict(x_vec.reshape(1, -1))[0])

        factors = []
        for name, val in zip(self.forecaster.feature_names, shap_vals):
            friendly = FEATURE_FRIENDLY_NAMES.get(name, name)
            factors.append({
                "feature": name,
                "friendly_name": friendly,
                "impact": round(float(val), 3),
                "direction": "positive" if val > 0 else "negative" if val < 0 else "neutral",
                "abs_impact": abs(float(val))
            })

        factors.sort(key=lambda x: x["abs_impact"], reverse=True)
        top_factors = factors[:top_k]

        # Generate plain-language summary for smallholder farmers
        explanations = []
        for factor in top_factors:
            f_name = factor["friendly_name"]
            impact = factor["impact"]
            if impact > 0:
                explanations.append(f"✓ {f_name} provided a boost of +{abs(impact):.2f} t/ha to your expected yield.")
            elif impact < 0:
                explanations.append(f"⚠️ {f_name} reduced your predicted yield by -{abs(impact):.2f} t/ha.")

        summary_text = (
            f"Predicted harvest is {actual_pred:.2f} t/ha compared to the regional benchmark of {self.base_value:.2f} t/ha. "
            + " ".join(explanations)
        )

        return {
            "predicted_yield": round(actual_pred, 2),
            "baseline_yield": round(self.base_value, 2),
            "net_difference": round(actual_pred - self.base_value, 2),
            "top_factors": top_factors,
            "plain_language_explanation": summary_text,
            "factors_bullet_points": explanations
        }

shap_engine = ShapExplainEngine()
