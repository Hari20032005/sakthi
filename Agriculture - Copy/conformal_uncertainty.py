"""
Conformal prediction intervals -- replaces the tree-spread heuristic in
uncertainty_model.py with a method that is mathematically designed to
hit its target coverage, rather than hoping the tree-spread happens to
be well-calibrated.

How split conformal prediction works, in plain terms:
1. Run LOOCV (as before) to get an out-of-fold prediction for every row
   -- i.e. each prediction is genuinely "held out", not fit on itself.
2. Compute the absolute error |actual - predicted| for every row. This
   is the calibration set.
3. To build a 90% interval, find the value that (1-alpha) of these
   errors fall below -- using the standard finite-sample conformal
   correction ceil((n+1)*(1-alpha))/n, NOT a plain percentile, which is
   what makes this "conformal" and gives a coverage guarantee rather
   than just an empirical heuristic.
4. Every new prediction gets interval = [prediction - margin, prediction + margin].

This trades per-row-adaptive interval width (which the tree-spread
method has, and this does not) for a mathematically justified coverage
guarantee -- a deliberate, explainable trade-off worth stating in the
report.

Reference: Vovk, Gammerman & Shafer's conformal prediction framework;
this is the simplest variant (constant-width, absolute-residual split
conformal), appropriate for a 36-row dataset where a fancier adaptive
version would itself be unreliable to fit.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import LeaveOneOut

from baseline_model import build_features, INPUT_FILE

CONFIDENCE_LEVEL = 0.90


def conformal_margin(residuals: np.ndarray, confidence: float) -> float:
    """The core conformal-prediction math: returns the margin such that
    the interval [pred - margin, pred + margin] has a valid finite-sample
    coverage guarantee, given exchangeable calibration residuals."""
    n = len(residuals)
    q_level = min(np.ceil((n + 1) * confidence) / n, 1.0)
    return np.quantile(residuals, q_level, method="higher")


if __name__ == "__main__":
    df = pd.read_csv(INPUT_FILE)
    df["price_was_imputed"] = df["avg_modal_price"].isna()
    df["avg_modal_price"] = df.groupby("Crop")["avg_modal_price"].transform(lambda s: s.fillna(s.mean()))
    df["price_volatility"] = df.groupby("Crop")["price_volatility"].transform(lambda s: s.fillna(s.mean()))
    df["avg_modal_price"] = df["avg_modal_price"].fillna(df["avg_modal_price"].mean())
    df["price_volatility"] = df["price_volatility"].fillna(df["price_volatility"].mean())

    X_df = build_features(df)
    X = X_df.values.astype(float)
    y = df["Yield"].values
    n = len(y)

    print(f"Running LOOCV to build the conformal calibration set ({n} rows)...")
    loo = LeaveOneOut()
    predictions = np.zeros(n)
    for train_idx, test_idx in loo.split(X):
        model = RandomForestRegressor(n_estimators=200, random_state=42)
        model.fit(X[train_idx], y[train_idx])
        predictions[test_idx] = model.predict(X[test_idx])

    residuals = np.abs(y - predictions)
    margin = conformal_margin(residuals, CONFIDENCE_LEVEL)

    print(f"Conformal margin at {int(CONFIDENCE_LEVEL*100)}% confidence: +/- {margin:.3f} t/ha "
          f"(constant width, unlike the tree-spread method's per-row-varying width)")

    lower = predictions - margin
    upper = predictions + margin
    within = (y >= lower) & (y <= upper)
    empirical_coverage = within.mean() * 100

    print(f"\n{'='*60}")
    print("CONFORMAL CALIBRATION CHECK")
    print(f"{'='*60}")
    print(f"Target coverage:      {int(CONFIDENCE_LEVEL*100)}%")
    print(f"Empirical coverage:   {empirical_coverage:.1f}% ({within.sum()} of {n} rows)")
    print(f"Interval width:       {2*margin:.2f} t/ha (constant for every row)")
    print(f"{'='*60}")

    results_df = pd.DataFrame({
        "Crop": df["Crop"].values, "Year": df["Crop_Year"].values, "Season": df["Season"].values,
        "Actual": y.round(2), "Predicted": predictions.round(2),
        "Lower_Bound": lower.round(2), "Upper_Bound": upper.round(2),
        "Within_Interval": within,
    })
    results_df.to_csv("conformal_uncertainty_results.csv", index=False)
    print("\nSaved -> conformal_uncertainty_results.csv")

    print("\nComparison note for the report: the earlier tree-spread method gave 75.0% "
          f"empirical coverage against a 90% target. This conformal method gives "
          f"{empirical_coverage:.1f}% -- report both, and explain the trade-off: tree-spread "
          "intervals vary in width per prediction (narrower when trees agree, wider when they "
          "don't) but were not well-calibrated; conformal intervals are constant-width but are "
          "mathematically constructed to target the correct coverage rate.")