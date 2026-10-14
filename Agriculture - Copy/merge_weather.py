"""
Builds the final training table: joins each yield record (one row per
Crop_Year + Season + Crop) with aggregated weather stats for that
specific season's date range.

Indian agricultural season month-ranges used here (standard definitions):
  Kharif:      Jun 1  -> Oct 31   (same Crop_Year)
  Rabi:        Nov 1  -> Mar 31   (Crop_Year -> Crop_Year + 1)
  Whole Year:  Jan 1  -> Dec 31   (same Crop_Year)
  Summer:      Mar 1  -> Jun 15   (same Crop_Year)
  Autumn:      Aug 1  -> Nov 30   (same Crop_Year)
"""

import pandas as pd

WEATHER_FILE = "data_historical_weather_ariyalur_2008_2019.csv"
YIELD_FILE = "data_yield_ariyalur_rice_cotton_clean.csv"

SEASON_RANGES = {
    "Kharif":     lambda y: (f"{y}-06-01", f"{y}-10-31"),
    "Rabi":       lambda y: (f"{y}-11-01", f"{y+1}-03-31"),
    "Whole Year": lambda y: (f"{y}-01-01", f"{y}-12-31"),
    "Summer":     lambda y: (f"{y}-03-01", f"{y}-06-15"),
    "Autumn":     lambda y: (f"{y}-08-01", f"{y}-11-30"),
}


def aggregate_weather_for_season(weather_df: pd.DataFrame, start: str, end: str) -> dict:
    mask = (weather_df["date"] >= start) & (weather_df["date"] <= end)
    window = weather_df.loc[mask]
    if window.empty:
        return {
            "total_rainfall_mm": None, "avg_temp_max": None,
            "avg_temp_min": None, "avg_temp_mean": None,
            "total_et0": None, "avg_wind_speed": None, "days_covered": 0,
        }
    return {
        "total_rainfall_mm": window["precipitation_sum"].sum(),
        "avg_temp_max": window["temperature_2m_max"].mean(),
        "avg_temp_min": window["temperature_2m_min"].mean(),
        "avg_temp_mean": window["temperature_2m_mean"].mean(),
        "total_et0": window["et0_fao_evapotranspiration"].sum(),
        "avg_wind_speed": window["wind_speed_10m_max"].mean(),
        "days_covered": len(window),
    }


if __name__ == "__main__":
    weather_df = pd.read_csv(WEATHER_FILE, parse_dates=["date"])
    weather_df["date"] = weather_df["date"].dt.strftime("%Y-%m-%d")

    yield_df = pd.read_csv(YIELD_FILE)

    rows = []
    skipped = 0
    for _, row in yield_df.iterrows():
        season = row["Season"]
        year = int(row["Crop_Year"])

        if season not in SEASON_RANGES:
            print(f"Skipping unrecognized season '{season}' (year {year}) -- add it to SEASON_RANGES if needed.")
            skipped += 1
            continue

        start, end = SEASON_RANGES[season](year)
        weather_stats = aggregate_weather_for_season(weather_df, start, end)

        if weather_stats["days_covered"] == 0:
            print(f"No weather data for {season} {year} ({start} to {end}) -- likely outside fetched range.")
            skipped += 1
            continue

        merged_row = {**row.to_dict(), **weather_stats}
        rows.append(merged_row)

    training_df = pd.DataFrame(rows)
    training_df.to_csv("training_data_ariyalur.csv", index=False)

    print(f"\nMerged {len(training_df)} rows successfully ({skipped} skipped).")
    print("\nFinal training table columns:", training_df.columns.tolist())
    print("\nSample:")
    print(training_df.head(10).to_string())