"""
Partial Dependence Analysis -- a statistically rigorous way to check
"does the model actually understand this feature's effect on yield?"

Unlike the scenario engine (which fixes all other features at ONE
baseline and sweeps one feature), partial dependence sweeps the target
feature across its full observed range while averaging the prediction
over EVERY OTHER combination actually seen in the training data. This
is the standard technique (Friedman, 2001) for isolating a feature's
marginal effect from a fitted model, and directly investigates the
counter-intuitive drought result found in the scenario engine.

Uses sklearn.inspection.partial_dependence -- not a custom
implementation, since this is a well-established, peer-reviewed method
and reinventing it risks introducing subtle bugs.
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import partial_dependence

from baseline_model import build_features, INPUT_FILE

# Features worth checking -- rainfall (to investigate the scenario engine's
# counter-intuitive result) plus the top two from SHAP, as a sanity check
# on features that DID look sensible
FEATURES_TO_CHECK = ["total_rainfall_mm", "avg_modal_price", "total_et0"]


def load_and_prepare():
    df = pd.read_csv(INPUT_FILE)
    df["price_was_imputed"] = df["avg_modal_price"].isna()
    df["avg_modal_price"] = df.groupby("Crop")["avg_modal_price"].transform(lambda s: s.fillna(s.mean()))
    df["price_volatility"] = df.groupby("Crop")["price_volatility"].transform(lambda s: s.fillna(s.mean()))
    df["avg_modal_price"] = df["avg_modal_price"].fillna(df["avg_modal_price"].mean())
    df["price_volatility"] = df["price_volatility"].fillna(df["price_volatility"].mean())
    return df


def check_monotonic_trend(grid_values, avg_predictions):
    """Simple, honest check: as this feature increases, does the
    prediction mostly go the direction real agronomy would expect,
    or does it wander/reverse -- and how much does it actually move?"""
    diffs = np.diff(avg_predictions)
    frac_increasing = (diffs > 0).mean()
    total_range = avg_predictions.max() - avg_predictions.min()
    return frac_increasing, total_range


if __name__ == "__main__":
    df = load_and_prepare()
    X_df = build_features(df)
    feature_names = X_df.columns.tolist()
    X = X_df.values.astype(float)
    y = df["Yield"].values

    print(f"Training final model on all {len(y)} rows...\n")
    model = RandomForestRegressor(n_estimators=200, random_state=42)
    model.fit(X, y)

    fig, axes = plt.subplots(1, len(FEATURES_TO_CHECK), figsize=(6 * len(FEATURES_TO_CHECK), 5))
    if len(FEATURES_TO_CHECK) == 1:
        axes = [axes]

    print("=" * 65)
    print("PARTIAL DEPENDENCE RESULTS")
    print("(marginal effect of each feature, averaged over all other")
    print(" real historical feature combinations -- not just one baseline)")
    print("=" * 65)

    for ax, feature in zip(axes, FEATURES_TO_CHECK):
        if feature not in feature_names:
            print(f"\n'{feature}' was dropped from the model (zero-variance or excluded) -- skipping.")
            continue

        feat_idx = feature_names.index(feature)
        pd_result = partial_dependence(model, X, features=[feat_idx], kind="average", grid_resolution=20)

        # sklearn's key names changed between versions -- handle both
        grid_values = pd_result.get("grid_values", pd_result.get("values"))[0]
        avg_predictions = pd_result["average"][0]

        frac_increasing, total_range = check_monotonic_trend(grid_values, avg_predictions)

        print(f"\n--- {feature} ---")
        print(f"Range swept: {grid_values.min():.1f} to {grid_values.max():.1f}")
        print(f"Predicted yield range across this sweep: {avg_predictions.min():.2f} to "
              f"{avg_predictions.max():.2f} t/ha (spread: {total_range:.2f})")
        print(f"Trend: {frac_increasing*100:.0f}% of steps show an INCREASE as {feature} rises")

        if total_range < 0.15:
            print(f"-> Model shows almost NO sensitivity to {feature} once averaged "
                  f"over all real data combinations (flat curve). This suggests the "
                  f"earlier scenario-engine result was more about correlation with a "
                  f"specific baseline row than a real learned effect.")
        elif feature == "total_rainfall_mm" and frac_increasing < 0.5:
            print(f"-> CONFIRMED: even averaged properly across all real data, the "
                  f"model's rainfall response is NOT consistently positive. This is a "
                  f"genuine limitation, not an artifact of the scenario engine's "
                  f"single-baseline design -- worth stating plainly in the report.")
        elif feature == "total_rainfall_mm":
            print(f"-> Mostly increasing as expected agronomically, though not perfectly "
                  f"monotonic -- reasonable given the small dataset.")

        ax.plot(grid_values, avg_predictions, marker="o", color="#2E7D32")
        ax.set_xlabel(feature)
        ax.set_ylabel("Predicted yield (t/ha)")
        ax.set_title(f"Partial dependence: {feature}")
        ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig("partial_dependence_plots.png", dpi=150)
    print("\nSaved chart -> partial_dependence_plots.png (use this in your Limitations section)")