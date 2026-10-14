"""
Baseline yield forecasting model -- Random Forest, evaluated with
Leave-One-Out Cross-Validation (LOOCV).

Why LOOCV instead of a normal train/test split: with ~36 rows, a single
80/20 split leaves only ~7 test rows -- results would swing wildly
depending on which 7 happened to be picked. LOOCV trains on all-but-one
row, predicts the held-out row, repeats for every row, then averages
the error. This uses every row as a test case exactly once, which is
the standard, defensible approach for small agricultural datasets.

Why Random Forest, not LSTM/transformer: with this few rows, a deep
model has far more parameters than data points and will just memorize
noise. Random Forest (and Gradient Boosting) are the right tool at this
scale -- this matches what your literature survey papers (e.g. Haji
Seyed Asadollah et al., 2024) also found for smaller agricultural
datasets.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import LeaveOneOut
from sklearn.metrics import mean_absolute_error, r2_score

INPUT_FILE = "training_data_ariyalur_full.csv"

# Columns that are identifiers/targets, not model input features
NON_FEATURE_COLS = ["State", "District", "Production", "Yield", "price_was_imputed"]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = pd.get_dummies(df, columns=["Crop", "Season"], drop_first=False)

    feature_cols = [c for c in df.columns if c not in NON_FEATURE_COLS]
    X = df[feature_cols]

    # Explicitly exclude ALL soil_* columns for this single-farm prototype.
    # They SHOULD be constant across every row (one static soil profile,
    # one farm location) -- and mostly are -- but relying only on measured
    # zero-variance to catch this is fragile (e.g. tiny floating-point
    # differences after a CSV round-trip, or duplicate rows in the source
    # soil file, can make an intended-constant column register nonzero
    # variance and slip through). An explicit exclusion is guaranteed
    # correct regardless of the cause. Soil becomes genuinely useful once
    # the system scales to multiple farm locations with real soil variation.
    soil_cols = [c for c in X.columns if c.startswith("soil_")]
    if soil_cols:
        print(f"Excluding {len(soil_cols)} soil_* columns -- static/single-farm, "
              f"not usable as a discriminating feature at this scale.")
        X = X.drop(columns=soil_cols)

    # Also still catch any OTHER accidental constant column (e.g. if a
    # weather stat happened to be identical across all rows this run)
    variances = X.var(numeric_only=True)
    constant_cols = variances[variances == 0].index.tolist()
    if constant_cols:
        print(f"Dropping {len(constant_cols)} other zero-variance features: {constant_cols}")
        X = X.drop(columns=constant_cols)

    return X


if __name__ == "__main__":
    df = pd.read_csv(INPUT_FILE)

    # 23 of 33 rows have missing price data (the price dataset simply
    # doesn't have a record for every season/year combination). Dropping
    # those rows would leave only ~10 rows -- nowhere near enough to train
    # or evaluate on. Instead, impute missing price with the CROP-SPECIFIC
    # average price (price varies much more by crop than by exact season),
    # and flag which rows were imputed so this is transparent, not hidden.
    df["price_was_imputed"] = df["avg_modal_price"].isna()
    df["avg_modal_price"] = df.groupby("Crop")["avg_modal_price"].transform(
        lambda s: s.fillna(s.mean())
    )
    df["price_volatility"] = df.groupby("Crop")["price_volatility"].transform(
        lambda s: s.fillna(s.mean())
    )
    # If a crop has NO price records at all, group-mean is also NaN --
    # fall back to the overall dataset mean as a last resort
    df["avg_modal_price"] = df["avg_modal_price"].fillna(df["avg_modal_price"].mean())
    df["price_volatility"] = df["price_volatility"].fillna(df["price_volatility"].mean())

    n_imputed = df["price_was_imputed"].sum()
    print(f"Using all {len(df)} rows -- imputed price for {n_imputed} rows "
          f"using crop-specific average price (see 'price_was_imputed' column "
          f"in the saved results for exactly which ones).")

    X = build_features(df)
    y = df["Yield"].values
    feature_names = X.columns.tolist()
    X = X.values.astype(float)

    print(f"\nFeatures used ({len(feature_names)}): {feature_names}")

    # --- LOOCV ---
    loo = LeaveOneOut()
    predictions = np.zeros(len(y))

    for train_idx, test_idx in loo.split(X):
        model = RandomForestRegressor(n_estimators=200, random_state=42)
        model.fit(X[train_idx], y[train_idx])
        predictions[test_idx] = model.predict(X[test_idx])

    mae = mean_absolute_error(y, predictions)
    r2 = r2_score(y, predictions)

    # MAPE is undefined when actual yield is 0 (division by zero) -- this
    # isn't a data error here, it reflects genuine crop failures (e.g. the
    # 2016-17 Tamil Nadu drought, one of the worst in over a century,
    # plausibly explains a real zero-yield cotton season). Exclude zero-
    # actual rows from MAPE specifically, but keep them in every other
    # metric and in the results table -- they're real, valid data points.
    nonzero_mask = y != 0
    n_excluded = (~nonzero_mask).sum()
    if n_excluded > 0:
        print(f"\nNote: {n_excluded} row(s) have Actual_Yield = 0 (likely genuine crop "
              f"failure, e.g. drought) -- excluded from MAPE only, since percent error "
              f"is undefined at zero. They remain in MAE, R2, and the results table.")
    mape = np.mean(np.abs((y[nonzero_mask] - predictions[nonzero_mask]) / y[nonzero_mask])) * 100

    print(f"\n{'='*50}")
    print("LOOCV RESULTS (baseline Random Forest)")
    print(f"{'='*50}")
    print(f"MAE (Mean Absolute Error):  {mae:.3f} tonnes/hectare")
    print(f"MAPE (Mean Abs % Error):    {mape:.1f}%")
    print(f"R² (variance explained):    {r2:.3f}")
    print(f"{'='*50}")

    print("\nActual vs Predicted (every row, held out once each):")
    comparison = pd.DataFrame({
        "Crop": df["Crop"].values,
        "Year": df["Crop_Year"].values,
        "Season": df["Season"].values,
        "Actual_Yield": y,
        "Predicted_Yield": predictions.round(2),
        "Abs_Error": np.abs(y - predictions).round(2),
        "Price_Was_Imputed": df["price_was_imputed"].values,
    })
    print(comparison.to_string())

    # --- Feature importance (train once on everything for this view) ---
    final_model = RandomForestRegressor(n_estimators=200, random_state=42)
    final_model.fit(X, y)
    importances = pd.Series(final_model.feature_importances_, index=feature_names)
    importances = importances.sort_values(ascending=False)

    print("\nFeature importance (which factors matter most to the model):")
    print(importances.head(10).to_string())

    comparison.to_csv("baseline_model_loocv_results.csv", index=False)
    print("\nSaved detailed results -> baseline_model_loocv_results.csv")