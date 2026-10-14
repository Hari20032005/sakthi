"""
Extends weather history back to 2008 so it overlaps with the yield data
(which only covers 2008-2019). Same Open-Meteo API as before, just a
different date range.

Note: fetches from 2007-06-01, not 2008-01-01, because Rabi season for
Crop_Year 2008 runs Nov 2008 - Mar 2009, but Kharif season needs data
starting mid-2007 for edge cases -- the extra buffer is cheap and safe.
"""

import requests
import pandas as pd

LATITUDE = 11.137
LONGITUDE = 79.078
LOCATION_NAME = "Ariyalur"


def fetch_historical_weather(start_date: str, end_date: str) -> pd.DataFrame:
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": start_date,
        "end_date": end_date,
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "temperature_2m_mean",
            "precipitation_sum",
            "rain_sum",
            "et0_fao_evapotranspiration",
            "wind_speed_10m_max",
        ],
        "timezone": "Asia/Kolkata",
    }
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()["daily"]
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["time"])
    df.drop(columns=["time"], inplace=True)
    df["location"] = LOCATION_NAME
    return df


if __name__ == "__main__":
    print(f"Fetching historical weather for {LOCATION_NAME}, 2007-06-01 to 2020-03-31...")
    df = fetch_historical_weather("2007-06-01", "2020-03-31")
    df.to_csv("data_historical_weather_ariyalur_2008_2019.csv", index=False)
    print(f"Saved {len(df)} days -> data_historical_weather_ariyalur_2008_2019.csv")
    print(df.head())