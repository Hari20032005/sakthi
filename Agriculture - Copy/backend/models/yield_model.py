import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import LeaveOneOut
from sklearn.metrics import mean_absolute_error, r2_score
from backend.config import TRAINING_DATA_FILE

NON_FEATURE_COLS = ["State", "District", "Production", "Yield", "price_was_imputed"]
CONFIDENCE_LEVEL = 0.90

class YieldForecaster:
    def __init__(self, data_path=TRAINING_DATA_FILE):
        self.data_path = str(data_path)
        self.df = None
        self.feature_names = []
        self.rf_model = None
        self.gb_model = None
        self._loocv = None
        self._conformal_margin = None
        self.load_and_train()

    @property
    def conformal_margin(self) -> float:
        """Split-conformal margin, computed on first access.

        Exposed as a property so that a caller reaching ``predict()`` without
        first touching the metrics still gets a computed margin. As a plain
        attribute it defaulted to zero and silently collapsed every reported
        interval to a point.
        """

        if self._conformal_margin is None:
            self.loocv_evaluation()
        return float(self._conformal_margin or 0.0)

    def build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df = pd.get_dummies(df, columns=["Crop", "Season"], drop_first=False)
        feature_cols = [c for c in df.columns if c not in NON_FEATURE_COLS]
        X = df[feature_cols]

        # Exclude static single-farm soil properties to prevent zero/near-zero variance overfitting
        soil_cols = [c for c in X.columns if c.startswith("soil_")]
        if soil_cols:
            X = X.drop(columns=soil_cols)

        # Drop constant columns
        variances = X.var(numeric_only=True)
        constant_cols = variances[variances == 0].index.tolist()
        if constant_cols:
            X = X.drop(columns=constant_cols)

        return X

    def prepare_data(self):
        df = pd.read_csv(self.data_path)
        df["price_was_imputed"] = df["avg_modal_price"].isna()
        df["avg_modal_price"] = df.groupby("Crop")["avg_modal_price"].transform(
            lambda s: s.fillna(s.mean())
        )
        df["price_volatility"] = df.groupby("Crop")["price_volatility"].transform(
            lambda s: s.fillna(s.mean())
        )
        df["avg_modal_price"] = df["avg_modal_price"].fillna(df["avg_modal_price"].mean())
        df["price_volatility"] = df["price_volatility"].fillna(df["price_volatility"].mean())
        return df

    def load_and_train(self):
        self.df = self.prepare_data()
        X_df = self.build_features(self.df)
        self.feature_names = X_df.columns.tolist()
        X = X_df.values.astype(float)
        y = self.df["Yield"].values

        # Fast training on full historical dataset
        self.rf_model = RandomForestRegressor(n_estimators=100, random_state=42)
        self.rf_model.fit(X, y)
        self.gb_model = GradientBoostingRegressor(n_estimators=80, max_depth=3, random_state=42)
        self.gb_model.fit(X, y)

    def loocv_evaluation(self) -> dict:
        """Leave-one-out metrics, computed on demand and cached.

        These were previously hard-coded constants. They did not match the data:
        the stored margin of 1.769 is the 80 % conformal quantile (true value
        1.7753), while the 90 % quantile is 2.3967, so the interval that was
        labelled "90 % Finite-Sample Conformal Prediction" in fact covered 30 of
        36 leave-one-out residuals (83.3 %). The stored R2 of 0.412 was 0.1422
        and the stored MAE of 0.963 was 0.9954.

        Recomputing is the fix, but it also means the reported figures must be
        re-checked whenever the training table changes. Nothing here is a
        constant that can be trusted across a data refresh.
        """

        if self._loocv is not None:
            return self._loocv

        X_df = self.build_features(self.df)
        X = X_df.values.astype(float)
        y = self.df["Yield"].values.astype(float)

        n = len(y)
        loo = LeaveOneOut()
        rf_preds = np.zeros(n)
        gb_preds = np.zeros(n)
        for train_idx, test_idx in loo.split(X):
            rf = RandomForestRegressor(n_estimators=200, random_state=42)
            rf.fit(X[train_idx], y[train_idx])
            rf_preds[test_idx] = rf.predict(X[test_idx])
            gb = GradientBoostingRegressor(n_estimators=80, max_depth=3, random_state=42)
            gb.fit(X[train_idx], y[train_idx])
            gb_preds[test_idx] = gb.predict(X[test_idx])

        residuals = np.abs(y - rf_preds)
        q_level = min(np.ceil((n + 1) * CONFIDENCE_LEVEL) / n, 1.0)
        margin = float(np.quantile(residuals, q_level, method="higher"))

        nonzero = y > 0
        self._conformal_margin = margin

        self._loocv = {
            "random_forest": {
                "model": "Random Forest",
                "mae": round(float(mean_absolute_error(y, rf_preds)), 4),
                "mape": round(float(np.mean(np.abs((y[nonzero] - rf_preds[nonzero]) / y[nonzero])) * 100), 2),
                "r2": round(float(r2_score(y, rf_preds)), 4),
            },
            "gradient_boosting": {
                "model": "Gradient Boosting",
                "mae": round(float(mean_absolute_error(y, gb_preds)), 4),
                "mape": round(float(np.mean(np.abs((y[nonzero] - gb_preds[nonzero]) / y[nonzero])) * 100), 2),
                "r2": round(float(r2_score(y, gb_preds)), 4),
            },
            "conformal_target_coverage": f"{int(CONFIDENCE_LEVEL * 100)}%",
            "conformal_margin": round(margin, 4),
            "conformal_empirical_coverage": round(float(np.mean(residuals <= margin)), 4),
            "n_calibration": n,
            "note": (
                "Metrics recomputed by leave-one-out on the current training table. "
                "Empirical coverage above is in-sample over those same residuals and is "
                "therefore optimistic; it is reported so the gap against the nominal level "
                "is visible rather than implied."
            ),
        }
        return self._loocv

    @property
    def loocv_metrics(self) -> dict:
        return self.loocv_evaluation()

    def recompute_loocv(self):
        """Force a recomputation and return the conformal margin."""

        self._loocv = None
        return self.loocv_evaluation()["conformal_margin"]

    def get_baseline_row(self, crop: str, season: str) -> dict:
        subset = self.df[(self.df["Crop"] == crop) & (self.df["Season"] == season)]
        if subset.empty:
            subset = self.df[self.df["Crop"] == crop]
            if subset.empty:
                subset = self.df

        numeric_cols = [
            "Crop_Year", "Area", "total_rainfall_mm", "avg_temp_max",
            "avg_temp_min", "avg_temp_mean", "total_et0", "avg_wind_speed",
            "avg_modal_price", "price_volatility", "n_price_records"
        ]
        baseline = {col: float(subset[col].mean()) for col in numeric_cols}
        baseline["Crop"] = crop
        baseline["Season"] = season
        return baseline

    def build_input_vector(self, baseline_row: dict, overrides: dict = None) -> np.ndarray:
        row = {**baseline_row, **(overrides or {})}
        row_df = pd.DataFrame([row])
        row_df = pd.get_dummies(row_df, columns=["Crop", "Season"])
        row_df = row_df.reindex(columns=self.feature_names, fill_value=0)
        return row_df.values[0].astype(float)

    def predict(self, crop: str, season: str, overrides: dict = None) -> dict:
        baseline = self.get_baseline_row(crop, season)
        X_vec = self.build_input_vector(baseline, overrides)

        # 1. Ensemble point prediction
        rf_pred = float(self.rf_model.predict(X_vec.reshape(1, -1))[0])
        gb_pred = float(self.gb_model.predict(X_vec.reshape(1, -1))[0])

        # 2. Tree spread uncertainty (empirical)
        tree_preds = np.array([tree.predict(X_vec.reshape(1, -1))[0] for tree in self.rf_model.estimators_])
        tree_lower = float(np.percentile(tree_preds, (1 - CONFIDENCE_LEVEL) / 2 * 100))
        tree_upper = float(np.percentile(tree_preds, (1 + CONFIDENCE_LEVEL) / 2 * 100))
        tree_std = float(tree_preds.std())

        # 3. Conformal Prediction uncertainty (mathematical finite-sample guarantee)
        conf_lower = max(0.0, float(rf_pred - self.conformal_margin))
        conf_upper = float(rf_pred + self.conformal_margin)

        return {
            "crop": crop,
            "season": season,
            "predicted_yield_t_per_ha": round(rf_pred, 2),
            "gradient_boosting_yield": round(gb_pred, 2),
            "conformal_interval": {
                "lower_bound": round(conf_lower, 2),
                "upper_bound": round(conf_upper, 2),
                "margin": round(self.conformal_margin, 2),
                "confidence_level": f"{int(CONFIDENCE_LEVEL * 100)}%",
                "guarantee_type": "Finite-Sample Conformal Prediction"
            },
            "tree_spread_interval": {
                "lower_bound": round(max(0.0, tree_lower), 2),
                "upper_bound": round(tree_upper, 2),
                "std_dev": round(tree_std, 2),
                "confidence_level": f"{int(CONFIDENCE_LEVEL * 100)}%"
            },
            "baseline_factors": {
                "rainfall_mm": round(baseline.get("total_rainfall_mm", 0), 1),
                "avg_temp_c": round(baseline.get("avg_temp_mean", 0), 1),
                "avg_modal_price": round(baseline.get("avg_modal_price", 0), 0)
            },
            "applied_overrides": overrides or {},
            "evaluation_benchmarks": self.loocv_metrics
        }

# Singleton instance
yield_forecaster = YieldForecaster()
