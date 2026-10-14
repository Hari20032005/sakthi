"""
Second baseline: Gradient Boosting, compared head-to-head against the
Random Forest baseline -- same LOOCV methodology, same features, same
imputation/exclusion rules, so the comparison is fair (only the model
type differs). This matches the approach used in several of your
literature survey papers (e.g. Haji Seyed Asadollah et al. 2024;
Jacome Galarza et al. 2025), who also compare multiple model types
rather than reporting just one.

Reuses build_features() from baseline_model.py so both scripts define
"the model's inputs" identically -- if you change feature engineering,
change it once in baseline_model.py and both scripts stay in sync.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import LeaveOneOut
from sklearn.metrics import mean_absolute_error, r2_score

from baseline_model import build_features, INPUT_FILE  # reuse, don't duplicate


def run_loocv(model_class, model_kwargs, X, y):
    loo = LeaveOneOut()
    predictions = np.zeros(len(y))
    for train_idx, test_idx in loo.split(X):
        model = model_class(**model_kwargs)
        model.fit(X[train_idx], y[train_idx])
        predictions[test_idx] = model.predict(X[test_idx])
    return predictions


def summarize(name, y, predictions):
    mae = mean_absolute_error(y, predictions)
    r2 = r2_score(y, predictions)
    nonzero_mask = y != 0
    mape = np.mean(np.abs((y[nonzero_mask] - predictions[nonzero_mask]) / y[nonzero_mask])) * 100
    return {"Model": name, "MAE": round(mae, 3), "MAPE_%": round(mape, 1), "R2": round(r2, 3)}


if __name__ == "__main__":
    df = pd.read_csv(INPUT_FILE)

    df["price_was_imputed"] = df["avg_modal_price"].isna()
    df["avg_modal_price"] = df.groupby("Crop")["avg_modal_price"].transform(lambda s: s.fillna(s.mean()))
    df["price_volatility"] = df.groupby("Crop")["price_volatility"].transform(lambda s: s.fillna(s.mean()))
    df["avg_modal_price"] = df["avg_modal_price"].fillna(df["avg_modal_price"].mean())
    df["price_volatility"] = df["price_volatility"].fillna(df["price_volatility"].mean())

    X = build_features(df)
    feature_names = X.columns.tolist()
    y = df["Yield"].values
    X = X.values.astype(float)

    print(f"\nRunning LOOCV for both models on {len(y)} rows, {len(feature_names)} features...\n")

    rf_preds = run_loocv(RandomForestRegressor, {"n_estimators": 200, "random_state": 42}, X, y)
    gb_preds = run_loocv(GradientBoostingRegressor, {"n_estimators": 100, "max_depth": 3, "random_state": 42}, X, y)

    results = [
        summarize("Random Forest", y, rf_preds),
        summarize("Gradient Boosting", y, gb_preds),
    ]
    results_df = pd.DataFrame(results)

    print("=" * 55)
    print("MODEL COMPARISON (identical LOOCV methodology)")
    print("=" * 55)
    print(results_df.to_string(index=False))
    print("=" * 55)

    better = results_df.loc[results_df["MAE"].idxmin(), "Model"]
    print(f"\nLower MAE (better): {better}")

    # Per-row comparison, useful for spotting whether one model is
    # consistently better on a specific crop/season, not just on average
    comparison = pd.DataFrame({
        "Crop": df["Crop"].values,
        "Year": df["Crop_Year"].values,
        "Season": df["Season"].values,
        "Actual": y,
        "RF_Predicted": rf_preds.round(2),
        "GB_Predicted": gb_preds.round(2),
        "RF_Error": np.abs(y - rf_preds).round(2),
        "GB_Error": np.abs(y - gb_preds).round(2),
    })
    comparison.to_csv("model_comparison_results.csv", index=False)
    print("\nSaved per-row comparison -> model_comparison_results.csv")

    print("\nRows where Gradient Boosting beat Random Forest by a meaningful margin:")
    gb_wins = comparison[comparison["GB_Error"] < comparison["RF_Error"] - 0.2]
    print(gb_wins.to_string() if len(gb_wins) else "  (none)")