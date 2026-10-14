import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from backend.config import PRICE_DATA_FILE

class PriceForecaster:
    def __init__(self, data_path=PRICE_DATA_FILE):
        self.data_path = str(data_path)
        self.df = None
        self.monthly_prices = {}
        self.load_data()

    def load_data(self):
        df = pd.read_csv(self.data_path)
        df["Arrival_Date"] = pd.to_datetime(df["Arrival_Date"], errors="coerce")
        df = df.dropna(subset=["Arrival_Date", "Modal_Price"])
        
        # Categorize commodity
        def map_crop(val):
            val_lower = str(val).lower()
            if "paddy" in val_lower or "rice" in val_lower:
                return "Rice"
            elif "cotton" in val_lower:
                return "Cotton"
            return "Other"

        df["Crop_Category"] = df["Commodity"].apply(map_crop)
        self.df = df

        # Aggregate monthly
        for crop in ["Rice", "Cotton"]:
            sub = df[df["Crop_Category"] == crop].copy()
            if not sub.empty:
                sub["YearMonth"] = sub["Arrival_Date"].dt.to_period("M")
                monthly = sub.groupby("YearMonth")["Modal_Price"].agg(["mean", "std", "count"]).reset_index()
                monthly["Timestamp"] = monthly["YearMonth"].dt.to_timestamp()
                monthly["mean"] = monthly["mean"].round(2)
                self.monthly_prices[crop] = monthly

    def get_historical_series(self, crop="Rice", limit=24):
        monthly = self.monthly_prices.get(crop)
        if monthly is None or monthly.empty:
            return []
        recent = monthly.tail(limit)
        return [
            {
                "date": row["Timestamp"].strftime("%Y-%m"),
                "modal_price": float(row["mean"]),
                "record_count": int(row["count"])
            }
            for _, row in recent.iterrows()
        ]

    def forecast_prices(self, crop="Rice", months_ahead=6):
        monthly = self.monthly_prices.get(crop)
        if monthly is None or monthly.empty:
            base_price = 2200 if crop == "Rice" else 5800
            history_mean = base_price
            volatility = 150
            last_date = datetime.now()
        else:
            recent_mean = monthly["mean"].tail(6).mean()
            volatility = monthly["std"].tail(6).mean()
            if pd.isna(volatility) or volatility == 0:
                volatility = recent_mean * 0.06
            history_mean = recent_mean
            last_date = monthly["Timestamp"].max().to_pydatetime()

        forecasts = []
        # Inflation/Seasonal Trend drift factor (modest 0.4% per month with seasonal swing)
        growth_rate = 0.005
        seasonal_patterns = {
            "Rice": [0.02, 0.04, 0.01, -0.03, -0.05, -0.01],  # Peak pre-harvest, dips post-harvest
            "Cotton": [0.03, 0.05, 0.02, -0.02, -0.04, 0.01]
        }
        seasons = seasonal_patterns.get(crop, [0.0] * 6)

        curr_price = history_mean
        for i in range(1, months_ahead + 1):
            future_date = last_date + timedelta(days=30 * i)
            seasonal_effect = seasons[(i - 1) % len(seasons)] * curr_price
            projected = curr_price * (1 + growth_rate * i) + seasonal_effect
            margin = volatility * np.sqrt(i) * 1.645 # 90% confidence expansion
            forecasts.append({
                "date": future_date.strftime("%Y-%m"),
                "month_offset": i,
                "projected_price": round(float(projected), 2),
                "lower_bound": round(float(max(projected - margin, projected * 0.7)), 2),
                "upper_bound": round(float(projected + margin), 2),
                "confidence": "90%"
            })

        # Recommendation logic
        initial_p = forecasts[0]["projected_price"]
        max_f = max(forecasts, key=lambda x: x["projected_price"])
        if max_f["projected_price"] > initial_p * 1.05:
            recommendation = f"Favorable upward trend: holding produce until {max_f['date']} could yield up to ₹{max_f['projected_price']}/quintal (+{round((max_f['projected_price']/initial_p - 1)*100, 1)}%)."
            action = "HOLD_FOR_PEAK"
        else:
            recommendation = "Stable prices expected in near term. Mandi arrivals are steady; selling upon harvest is low-risk."
            action = "SELL_ON_HARVEST"

        return {
            "crop": crop,
            "current_benchmark_price": round(float(history_mean), 2),
            "historical_trend": self.get_historical_series(crop, limit=12),
            "forecast": forecasts,
            "market_recommendation": recommendation,
            "action": action
        }

price_forecaster = PriceForecaster()
