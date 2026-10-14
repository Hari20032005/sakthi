"""
SHAP explainability layer for the chosen Random Forest yield model.

This is what your chatbot's "explain this prediction" feature is built on:
instead of just outputting a yield number, SHAP breaks down exactly how
much each input factor (rainfall, price, crop type, etc.) pushed the
prediction up or down from the baseline average -- in plain, attributable
terms, not a black box.

Uses shap.TreeExplainer, which computes EXACT SHAP values for tree-based
models like Random Forest (no approximation needed, unlike model-agnostic
SHAP methods) -- and is fast even on small datasets like ours.

Reuses build_features() from baseline_model.py so the exact same feature
set used for training is used for explanation.
"""

import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import RandomForestRegressor

from baseline_model import build_features, INPUT_FILE


def prepare_data():
    df = pd.read_csv(INPUT_FILE)
    df["price_was_imputed"] = df["avg_modal_price"].isna()
    df["avg_modal_price"] = df.groupby("Crop")["avg_modal_price"].transform(lambda s: s.fillna(s.mean()))
    df["price_volatility"] = df.groupby("Crop")["price_volatility"].transform(lambda s: s.fillna(s.mean()))
    df["avg_modal_price"] = df["avg_modal_price"].fillna(df["avg_modal_price"].mean())
    df["price_volatility"] = df["price_volatility"].fillna(df["price_volatility"].mean())
    return df


def explain_row(shap_values_row, feature_names, base_value, actual_prediction, top_n=3):
    """Turns one row's raw SHAP numbers into a chatbot-style plain-English
    explanation -- this is literally the function your RAG chatbot would
    call before generating its farmer-facing response."""
    contributions = list(zip(feature_names, shap_values_row))
    contributions.sort(key=lambda x: abs(x[1]), reverse=True)

    lines = [f"Predicted yield: {actual_prediction:.2f} t/ha "
             f"(baseline average across all data: {base_value:.2f} t/ha)"]
    for name, value in contributions[:top_n]:
        direction = "increased" if value > 0 else "decreased"
        lines.append(f"  - {name} {direction} the prediction by {abs(value):.3f} t/ha")
    return "\n".join(lines)


if __name__ == "__main__":
    df = prepare_data()
    X_df = build_features(df)
    feature_names = X_df.columns.tolist()
    X = X_df.values.astype(float)
    y = df["Yield"].values

    print(f"Training final Random Forest on all {len(y)} rows for explanation...")
    model = RandomForestRegressor(n_estimators=200, random_state=42)
    model.fit(X, y)

    print("Computing SHAP values (TreeExplainer -- exact, not approximated)...")
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)
    base_value = explainer.expected_value
    if isinstance(base_value, (list, np.ndarray)):
        base_value = base_value[0]

    # --- Global importance: which features matter most, on average ---
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    global_importance = pd.Series(mean_abs_shap, index=feature_names).sort_values(ascending=False)

    print("\n" + "=" * 55)
    print("GLOBAL FEATURE IMPORTANCE (mean |SHAP value|)")
    print("=" * 55)
    print(global_importance.head(10).to_string())

    # --- Per-row explanations for a few interesting cases ---
    predictions = model.predict(X)
    print("\n" + "=" * 55)
    print("SAMPLE PER-PREDICTION EXPLANATIONS (chatbot-style)")
    print("=" * 55)

    # Show the explanation for: the best prediction, the worst prediction,
    # and one of the drought (zero-yield) rows -- these are the cases most
    # worth being able to explain clearly
    errors = np.abs(y - predictions)
    interesting_idx = [
        errors.argmin(),                  # best prediction
        errors.argmax(),                  # worst prediction
        np.where(y == 0)[0][0] if (y == 0).any() else 0,  # a drought-year row
    ]

    for idx in sorted(set(interesting_idx)):
        crop, year, season = df.iloc[idx][["Crop", "Crop_Year", "Season"]]
        print(f"\n--- Row {idx}: {crop}, {season} {year} (actual yield: {y[idx]:.2f} t/ha) ---")
        print(explain_row(shap_values[idx], feature_names, base_value, predictions[idx]))

    # Save full per-row SHAP values for every row, for use in the chatbot/report
    shap_df = pd.DataFrame(shap_values, columns=[f"shap_{c}" for c in feature_names])
    shap_df.insert(0, "Crop", df["Crop"].values)
    shap_df.insert(1, "Crop_Year", df["Crop_Year"].values)
    shap_df.insert(2, "Season", df["Season"].values)
    shap_df.insert(3, "Predicted_Yield", predictions.round(3))
    shap_df.to_csv("shap_explanations_all_rows.csv", index=False)
    print("\nSaved full per-row SHAP values -> shap_explanations_all_rows.csv")

    # --- Save a summary bar chart for the report ---
    try:
        import matplotlib
        matplotlib.use("Agg")  # no display needed, just save to file
        import matplotlib.pyplot as plt

        plt.figure(figsize=(8, 5))
        global_importance.head(10).sort_values().plot(kind="barh", color="#2E7D32")
        plt.xlabel("Mean |SHAP value| (impact on predicted yield, t/ha)")
        plt.title("Which factors matter most to the yield model")
        plt.tight_layout()
        plt.savefig("shap_summary_chart.png", dpi=150)
        print("Saved chart -> shap_summary_chart.png (use this in your report)")
    except ImportError:
        print("matplotlib not installed -- skipping chart (pip install matplotlib to get it)")