"""
Scenario simulation engine -- the "what-if" decision-support tool.

Lets a farmer compare predicted outcomes for different choices (crop,
season, expected rainfall, etc.) BEFORE committing to one in the real
field. This is the core differentiator identified in the literature
survey -- no paper in our 15-paper survey combines prediction with
actual scenario comparison.

Reuses:
  - build_features() from baseline_model.py (same feature engineering)
  - predict_with_interval() from uncertainty_model.py (same confidence
    ranges, so scenario comparisons are honest about their uncertainty,
    not just point estimates)

Design: rather than requiring the user to specify every single feature
by hand, each scenario starts from a REALISTIC BASELINE (the historical
average conditions for that crop/season in the actual data), and the
user only overrides the specific factor(s) they're asking "what if"
about. This is what makes a scenario request like "what if rainfall is
30% lower" meaningful instead of requiring 15 arbitrary numbers.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from baseline_model import build_features, INPUT_FILE
from uncertainty_model import predict_with_interval, CONFIDENCE_LEVEL


def load_and_prepare():
    df = pd.read_csv(INPUT_FILE)
    df["price_was_imputed"] = df["avg_modal_price"].isna()
    df["avg_modal_price"] = df.groupby("Crop")["avg_modal_price"].transform(lambda s: s.fillna(s.mean()))
    df["price_volatility"] = df.groupby("Crop")["price_volatility"].transform(lambda s: s.fillna(s.mean()))
    df["avg_modal_price"] = df["avg_modal_price"].fillna(df["avg_modal_price"].mean())
    df["price_volatility"] = df["price_volatility"].fillna(df["price_volatility"].mean())
    return df


def build_baseline_row(df, crop, season):
    """Historical average conditions for this crop/season combination --
    the realistic starting point a scenario then overrides specific
    factors on top of."""
    subset = df[(df["Crop"] == crop) & (df["Season"] == season)]
    if subset.empty:
        # Fall back to crop-level average if this exact crop/season
        # combination has no history (e.g. asking about a season this
        # crop has never actually been recorded in)
        subset = df[df["Crop"] == crop]
        print(f"  (note: no historical {crop}/{season} data -- using {crop}'s "
              f"overall average as the baseline instead)")

    numeric_cols = ["Crop_Year", "Area", "total_rainfall_mm", "avg_temp_max",
                     "avg_temp_min", "avg_temp_mean", "total_et0", "avg_wind_speed",
                     "avg_modal_price", "price_volatility", "n_price_records"]
    baseline = {col: subset[col].mean() for col in numeric_cols}
    baseline["Crop"] = crop
    baseline["Season"] = season
    return baseline


def build_scenario_features(baseline_row, overrides, feature_names):
    """Turns one scenario (baseline + overrides) into a feature vector
    matching the exact columns the model was trained on."""
    row = {**baseline_row, **overrides}
    row_df = pd.DataFrame([row])
    row_df = pd.get_dummies(row_df, columns=["Crop", "Season"])

    # Reindex to match training feature columns exactly -- any dummy
    # column not present for this scenario (e.g. a Season this row
    # doesn't have) becomes 0, any extra column is dropped
    row_df = row_df.reindex(columns=feature_names, fill_value=0)
    return row_df.values[0].astype(float)


def run_scenario(model, feature_names, baseline_row, overrides, label):
    X_row = build_scenario_features(baseline_row, overrides, feature_names)
    mean_pred, lower, upper, std = predict_with_interval(model, X_row)
    return {
        "Scenario": label,
        "Predicted_Yield": round(mean_pred, 2),
        "Lower_Bound": round(lower, 2),
        "Upper_Bound": round(upper, 2),
        "Confidence": f"{int(CONFIDENCE_LEVEL*100)}%",
    }


if __name__ == "__main__":
    df = load_and_prepare()
    X_df = build_features(df)
    feature_names = X_df.columns.tolist()
    X = X_df.values.astype(float)
    y = df["Yield"].values

    print(f"Training final model on all {len(y)} rows for scenario simulation...\n")
    model = RandomForestRegressor(n_estimators=200, random_state=42)
    model.fit(X, y)

    # ============================================================
    # SCENARIO SET 1: Crop choice -- "what should I plant this Kharif?"
    # ============================================================
    print("=" * 65)
    print("SCENARIO 1: Which crop to plant this Kharif season?")
    print("=" * 65)

    rice_baseline = build_baseline_row(df, "Rice", "Kharif")
    cotton_baseline = build_baseline_row(df, "Cotton(lint)", "Kharif")

    results_1 = [
        run_scenario(model, feature_names, rice_baseline, {}, "Plant Rice (avg conditions)"),
        run_scenario(model, feature_names, cotton_baseline, {}, "Plant Cotton (avg conditions)"),
    ]
    print(pd.DataFrame(results_1).to_string(index=False))

    # ============================================================
    # SCENARIO SET 2: Rainfall risk -- "what if this is a drought year?"
    # ============================================================
    print("\n" + "=" * 65)
    print("SCENARIO 2: Rice under different rainfall conditions (Kharif)")
    print("=" * 65)

    avg_rainfall = rice_baseline["total_rainfall_mm"]
    results_2 = [
        run_scenario(model, feature_names, rice_baseline,
                     {"total_rainfall_mm": avg_rainfall * 0.6},
                     f"Drought (-40% rainfall, ~{avg_rainfall*0.6:.0f}mm)"),
        run_scenario(model, feature_names, rice_baseline, {},
                     f"Normal (avg rainfall, ~{avg_rainfall:.0f}mm)"),
        run_scenario(model, feature_names, rice_baseline,
                     {"total_rainfall_mm": avg_rainfall * 1.3},
                     f"Above-average (+30% rainfall, ~{avg_rainfall*1.3:.0f}mm)"),
    ]
    print(pd.DataFrame(results_2).to_string(index=False))

    # ============================================================
    # SCENARIO SET 3: Season timing -- "Kharif vs Rabi for cotton?"
    # ============================================================
    print("\n" + "=" * 65)
    print("SCENARIO 3: Cotton -- Kharif vs Rabi planting")
    print("=" * 65)

    cotton_rabi_baseline = build_baseline_row(df, "Cotton(lint)", "Rabi")
    results_3 = [
        run_scenario(model, feature_names, cotton_baseline, {}, "Cotton, Kharif season"),
        run_scenario(model, feature_names, cotton_rabi_baseline, {}, "Cotton, Rabi season"),
    ]
    print(pd.DataFrame(results_3).to_string(index=False))

    # Save all scenarios together
    all_results = pd.DataFrame(results_1 + results_2 + results_3)
    all_results.to_csv("scenario_simulation_results.csv", index=False)
    print("\nSaved all scenarios -> scenario_simulation_results.csv")

    print("\n" + "=" * 65)
    print("This is the core 'what-if' capability: a farmer can compare")
    print("predicted outcomes -- WITH confidence ranges -- for different")
    print("crop, timing, and risk scenarios before committing in the field.")
    print("=" * 65)