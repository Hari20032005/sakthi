"""
Final merge: combines all four confirmed data sources into one training
table for the yield forecasting model.

  - Yield (target variable)      -> data_yield_ariyalur_rice_cotton_clean.csv
  - Weather (seasonal aggregate)  -> data_historical_weather_ariyalur_2008_2019.csv
  - Soil (static, same for every row) -> data_soil_ariyalur.csv
  - Price (seasonal aggregate)    -> data_prices_ariyalur_tamilnadu_2001_2026.csv

Run this AFTER all four individual collector/filter scripts have produced
their CSVs in the same folder.
"""

import pandas as pd

YIELD_FILE = "data_yield_ariyalur_rice_cotton_clean.csv"
WEATHER_FILE = "data_historical_weather_ariyalur_2008_2019.csv"
SOIL_FILE = "data_soil_ariyalur.csv"
PRICE_FILE = "data_prices_ariyalur_tamilnadu_2001_2026.csv"

SEASON_RANGES = {
    "Kharif":     lambda y: (f"{y}-06-01", f"{y}-10-31"),
    "Rabi":       lambda y: (f"{y}-11-01", f"{y+1}-03-31"),
    "Whole Year": lambda y: (f"{y}-01-01", f"{y}-12-31"),
    "Summer":     lambda y: (f"{y}-03-01", f"{y}-06-15"),
    "Autumn":     lambda y: (f"{y}-08-01", f"{y}-11-30"),
    "Winter":     lambda y: (f"{y}-11-01", f"{y+1}-02-28"),  # same window as Rabi
}


def aggregate_weather(weather_df, start, end):
    mask = (weather_df["date"] >= start) & (weather_df["date"] <= end)
    window = weather_df.loc[mask]
    if window.empty:
        return None
    return {
        "total_rainfall_mm": window["precipitation_sum"].sum(),
        "avg_temp_max": window["temperature_2m_max"].mean(),
        "avg_temp_min": window["temperature_2m_min"].mean(),
        "avg_temp_mean": window["temperature_2m_mean"].mean(),
        "total_et0": window["et0_fao_evapotranspiration"].sum(),
        "avg_wind_speed": window["wind_speed_10m_max"].mean(),
    }


def aggregate_price(price_df, crop_keyword, start, end):
    mask = (
        (price_df["Arrival_Date"] >= start)
        & (price_df["Arrival_Date"] <= end)
        & (price_df["Commodity"].str.contains(crop_keyword, case=False, na=False))
    )
    window = price_df.loc[mask]
    if window.empty:
        return None
    return {
        "avg_modal_price": window["Modal_Price"].mean(),
        "price_volatility": window["Modal_Price"].std(),
        "n_price_records": len(window),
    }


def build_soil_features(soil_df):
    """Pivot the long soil table (property/depth/value) into one flat row
    of features, e.g. soil_clay_0_5cm=38.1, soil_phh2o_0_5cm=7.3, etc.
    Soil doesn't change year to year, so this same row applies to every
    yield record."""
    features = {}
    for _, row in soil_df.iterrows():
        depth_clean = row["depth"].replace("-", "_")
        col_name = f"soil_{row['property']}_{depth_clean}"
        features[col_name] = row["value"]
    return features


if __name__ == "__main__":
    yield_df = pd.read_csv(YIELD_FILE)
    weather_df = pd.read_csv(WEATHER_FILE, parse_dates=["date"])
    weather_df["date"] = weather_df["date"].dt.strftime("%Y-%m-%d")
    soil_df = pd.read_csv(SOIL_FILE)
    price_df = pd.read_csv(PRICE_FILE)

    soil_features = build_soil_features(soil_df)
    print(f"Soil features (static, applied to every row): {list(soil_features.keys())}")

    # Map yield's crop names to price data's commodity naming
    CROP_TO_PRICE_KEYWORD = {
        "Rice": "Paddy",
        "Cotton(lint)": "Cotton",
    }

    rows = []
    skipped = 0
    for _, row in yield_df.iterrows():
        season = row["Season"]
        year = int(row["Crop_Year"])
        crop = row["Crop"]

        if season not in SEASON_RANGES:
            print(f"Skipping unrecognized season '{season}' ({crop}, {year})")
            skipped += 1
            continue

        start, end = SEASON_RANGES[season](year)

        weather_feats = aggregate_weather(weather_df, start, end)
        if weather_feats is None:
            print(f"No weather data for {crop} {season} {year} -- skipping")
            skipped += 1
            continue

        price_keyword = CROP_TO_PRICE_KEYWORD.get(crop, crop)
        price_feats = aggregate_price(price_df, price_keyword, start, end)
        if price_feats is None:
            # Price data may not cover every season -- fill with NaN rather
            # than dropping the row entirely, since yield/weather are still valid
            price_feats = {"avg_modal_price": None, "price_volatility": None, "n_price_records": 0}
            print(f"No price data for {crop} {season} {year} -- filled as missing")

        merged_row = {**row.to_dict(), **weather_feats, **price_feats, **soil_features}
        rows.append(merged_row)

    training_df = pd.DataFrame(rows)
    training_df.to_csv("training_data_ariyalur_full.csv", index=False)

    print(f"\nFinal training table: {len(training_df)} rows, {len(training_df.columns)} columns "
          f"({skipped} rows skipped)")
    print("\nColumns:", training_df.columns.tolist())
    print("\nSample:")
    print(training_df.head(5).to_string())

    missing_price = training_df["avg_modal_price"].isna().sum()
    print(f"\nRows with missing price data: {missing_price} / {len(training_df)}")