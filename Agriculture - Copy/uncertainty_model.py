"""
Calibrated uncertainty for the yield model -- fulfills the project
objective of predicting yield WITH a confidence range, not a single
fixed number.

How it works: a Random Forest is really many individual decision trees
averaged together. Instead of only using the average (the normal
prediction), we look at ALL the individual trees' predictions for a
given input -- their spread tells us how confident the forest actually
is. If all trees agree, the range is narrow (high confidence). If trees
disagree a lot, the range is wide (low confidence) -- which is exactly
the honest behavior you want instead of a single potentially-misleading
number.

This is simpler than Monte Carlo Dropout (which is a neural-network-
specific technique) and is the standard way to get uncertainty out of
a Random Forest without retraining anything special.

CRITICAL: a confidence interval is only meaningful if it's CALIBRATED --
i.e. a 90% interval should actually contain the true value about 90% of
the time. We verify this empirically using LOOCV, rather than just
trusting the interval by construction. This calibration check is what
makes the uncertainty "calibrated" rather than just "a number that looks
like a range."
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import LeaveOneOut

from baseline_model import build_features, INPUT_FILE

CONFIDENCE_LEVEL = 0.90  # 90% interval -- change to 0.80/0.95 etc if you want


def predict_with_interval(model, X_row, confidence=CONFIDENCE_LEVEL):
    """Get every individual tree's prediction for one input row, then
    build a confidence interval from their spread."""
    tree_predictions = np.array([tree.predict(X_row.reshape(1, -1))[0] for tree in model.estimators_])

    mean_pred = tree_predictions.mean()
    lower_pct = (1 - confidence) / 2 * 100
    upper_pct = (1 + confidence) / 2 * 100
    lower = np.percentile(tree_predictions, lower_pct)
    upper = np.percentile(tree_predictions, upper_pct)

    return mean_pred, lower, upper, tree_predictions.std()


if __name__ == "__main__":
    df = pd.read_csv(INPUT_FILE)
    df["price_was_imputed"] = df["avg_modal_price"].isna()
    df["avg_modal_price"] = df.groupby("Crop")["avg_modal_price"].transform(lambda s: s.fillna(s.mean()))
    df["price_volatility"] = df.groupby("Crop")["price_volatility"].transform(lambda s: s.fillna(s.mean()))
    df["avg_modal_price"] = df["avg_modal_price"].fillna(df["avg_modal_price"].mean())
    df["price_volatility"] = df["price_volatility"].fillna(df["price_volatility"].mean())

    X_df = build_features(df)
    feature_names = X_df.columns.tolist()
    X = X_df.values.astype(float)
    y = df["Yield"].values

    print(f"Running LOOCV with uncertainty intervals ({int(CONFIDENCE_LEVEL*100)}% confidence) "
          f"on {len(y)} rows...\n")

    loo = LeaveOneOut()
    results = []

    for train_idx, test_idx in loo.split(X):
        model = RandomForestRegressor(n_estimators=200, random_state=42)
        model.fit(X[train_idx], y[train_idx])

        mean_pred, lower, upper, std = predict_with_interval(model, X[test_idx[0]])
        actual = y[test_idx[0]]
        within_interval = lower <= actual <= upper

        results.append({
            "Crop": df.iloc[test_idx[0]]["Crop"],
            "Year": df.iloc[test_idx[0]]["Crop_Year"],
            "Season": df.iloc[test_idx[0]]["Season"],
            "Actual": round(actual, 2),
            "Predicted": round(mean_pred, 2),
            "Lower_Bound": round(lower, 2),
            "Upper_Bound": round(upper, 2),
            "Interval_Width": round(upper - lower, 2),
            "Within_Interval": within_interval,
        })

    results_df = pd.DataFrame(results)

    # --- THE key check: is this actually calibrated? ---
    empirical_coverage = results_df["Within_Interval"].mean() * 100
    avg_width = results_df["Interval_Width"].mean()

    print("=" * 60)
    print(f"CALIBRATION CHECK  (target: {int(CONFIDENCE_LEVEL*100)}% of true values "
          f"should fall inside the interval)")
    print("=" * 60)
    print(f"Empirical coverage: {empirical_coverage:.1f}% "
          f"({results_df['Within_Interval'].sum()} of {len(results_df)} rows)")
    print(f"Average interval width: {avg_width:.2f} tonnes/hectare")

    gap = empirical_coverage - CONFIDENCE_LEVEL * 100
    if abs(gap) <= 10:
        print(f"-> Reasonably well calibrated (within 10 points of target, given only "
              f"{len(y)} rows -- exact calibration needs far more data than this).")
    elif gap < -10:
        print(f"-> Intervals are OVERCONFIDENT (too narrow) -- true values fall "
              f"outside more often than the {int(CONFIDENCE_LEVEL*100)}% claim.")
    else:
        print(f"-> Intervals are CONSERVATIVE (wider than necessary) -- true values "
              f"almost always land inside, could be tightened.")
    print("=" * 60)

    print("\nFull results (every row's prediction with its confidence range):")
    print(results_df.to_string(index=False))

    results_df.to_csv("uncertainty_loocv_results.csv", index=False)
    print("\nSaved -> uncertainty_loocv_results.csv")

    # Rows where the true value fell OUTSIDE the interval -- worth looking at directly
    misses = results_df[~results_df["Within_Interval"]]
    print(f"\nRows where actual yield fell OUTSIDE the predicted range ({len(misses)}):")
    print(misses.to_string(index=False) if len(misses) else "  (none)")