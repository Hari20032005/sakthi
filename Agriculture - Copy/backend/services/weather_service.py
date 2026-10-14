import requests
import pandas as pd
from datetime import datetime
from backend.config import WEATHER_FORECAST_FILE, WEATHER_HISTORICAL_FILE

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

class WeatherService:
    @staticmethod
    def get_forecast(lat: float = 11.137, lon: float = 79.078, days: int = 7):
        """Fetch 7-day live weather forecast from Open-Meteo with local CSV fallback."""
        try:
            params = {
                "latitude": lat,
                "longitude": lon,
                "daily": [
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "precipitation_probability_max",
                    "wind_speed_10m_max",
                    "et0_fao_evapotranspiration"
                ],
                "timezone": "Asia/Kolkata",
                "forecast_days": days
            }
            resp = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("daily", {})
                dates = data.get("time", [])
                forecast = []
                for i in range(len(dates)):
                    forecast.append({
                        "date": dates[i],
                        "temp_max": data.get("temperature_2m_max", [None])[i],
                        "temp_min": data.get("temperature_2m_min", [None])[i],
                        "rainfall_mm": data.get("precipitation_sum", [None])[i],
                        "rain_probability": data.get("precipitation_probability_max", [None])[i],
                        "wind_speed_kmh": data.get("wind_speed_10m_max", [None])[i],
                        "et0_mm": data.get("et0_fao_evapotranspiration", [None])[i],
                        "source": "Open-Meteo Live API"
                    })
                return {
                    "location": {"lat": lat, "lon": lon},
                    "source": "Open-Meteo Live API",
                    "forecast": forecast
                }
        except Exception as e:
            pass

        # Fallback to local forecast data
        return WeatherService._load_local_forecast(days)

    @staticmethod
    def _load_local_forecast(days: int = 7):
        try:
            df = pd.read_csv(WEATHER_FORECAST_FILE)
            records = df.head(days).to_dict(orient="records")
            clean_records = []
            for r in records:
                clean_records.append({
                    "date": str(r.get("date")),
                    "temp_max": float(r.get("temperature_2m_max", 34.0)),
                    "temp_min": float(r.get("temperature_2m_min", 25.0)),
                    "rainfall_mm": float(r.get("precipitation_sum", 0.0)),
                    "rain_probability": int(r.get("precipitation_probability_max", 40)),
                    "wind_speed_kmh": 14.5,
                    "et0_mm": 4.8,
                    "source": "Cached Sensor-Free Public Weather"
                })
            return {
                "location": {"lat": 11.137, "lon": 79.078, "district": "Ariyalur"},
                "source": "Cached NOAA/Open-Meteo",
                "forecast": clean_records
            }
        except Exception:
            today = datetime.now().strftime("%Y-%m-%d")
            return {
                "location": {"lat": 11.137, "lon": 79.078, "district": "Ariyalur"},
                "source": "System Baseline",
                "forecast": [
                    {"date": today, "temp_max": 34.2, "temp_min": 24.8, "rainfall_mm": 2.5, "rain_probability": 35, "source": "Baseline"}
                ]
            }

    @staticmethod
    def get_season_to_date_weather(lat: float, lon: float, sowing_date: str, forecast_days=None):
        """Get farm weather accumulated since sowing, with a transparent fallback.

        The archive API provides observed/reanalysis-like daily values. If it
        cannot be reached, a same-calendar-window climatology is calculated
        from the included Ariyalur historic-weather CSV. Forecast days are
        added separately by the weather-adjustment layer.
        """
        today = datetime.now().date()
        try:
            start = datetime.strptime(sowing_date, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            start = today
        if start > today:
            start = today
        if start == today:
            return {"source": "No elapsed growing days", "days": 0, "rainfall_mm": 0.0, "et0_mm": 0.0, "avg_temp_max": 0.0, "heat_days": 0}

        try:
            response = requests.get(
                OPEN_METEO_ARCHIVE_URL,
                params={
                    "latitude": lat, "longitude": lon,
                    "start_date": start.isoformat(), "end_date": (today - pd.Timedelta(days=1)).date().isoformat(),
                    "daily": ["temperature_2m_max", "precipitation_sum", "et0_fao_evapotranspiration"],
                    "timezone": "Asia/Kolkata",
                }, timeout=12,
            )
            response.raise_for_status()
            daily = response.json().get("daily", {})
            temps = [value for value in daily.get("temperature_2m_max", []) if value is not None]
            rain = [value or 0 for value in daily.get("precipitation_sum", [])]
            et0 = [value or 0 for value in daily.get("et0_fao_evapotranspiration", [])]
            if temps:
                return {
                    "source": "Open-Meteo historical weather API", "days": len(temps),
                    "rainfall_mm": round(float(sum(rain)), 1), "et0_mm": round(float(sum(et0)), 1),
                    "avg_temp_max": round(float(sum(temps) / len(temps)), 1),
                    "heat_days": sum(value >= 35 for value in temps),
                }
        except Exception:
            pass

        # Same-calendar-window climatology fallback from supplied historic data.
        try:
            df = pd.read_csv(WEATHER_HISTORICAL_FILE, parse_dates=["date"])
            dates = pd.date_range(start, today - pd.Timedelta(days=1), freq="D")
            seasonal_means = df.groupby(df["date"].dt.strftime("%m-%d"))[[
                "temperature_2m_max", "precipitation_sum", "et0_fao_evapotranspiration"
            ]].mean()
            values = [seasonal_means.loc[date.strftime("%m-%d")] for date in dates if date.strftime("%m-%d") in seasonal_means.index]
            if values:
                temps = [float(row["temperature_2m_max"]) for row in values]
                return {
                    "source": "Historical Ariyalur climatology fallback", "days": len(values),
                    "rainfall_mm": round(sum(float(row["precipitation_sum"]) for row in values), 1),
                    "et0_mm": round(sum(float(row["et0_fao_evapotranspiration"]) for row in values), 1),
                    "avg_temp_max": round(sum(temps) / len(temps), 1),
                    "heat_days": sum(value >= 35 for value in temps),
                }
        except Exception:
            pass
        return {"source": "Weather accumulation unavailable", "days": 0, "rainfall_mm": 0.0, "et0_mm": 0.0, "avg_temp_max": 0.0, "heat_days": 0}

weather_service = WeatherService()
