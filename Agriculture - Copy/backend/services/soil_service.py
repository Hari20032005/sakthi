import pandas as pd
from backend.config import SOIL_DATA_FILE

class SoilService:
    @staticmethod
    def get_soil_profile(lat: float = 11.137, lon: float = 79.078):
        """Returns the static 250m SoilGrids ISRIC profile for the farm."""
        try:
            df = pd.read_csv(SOIL_DATA_FILE)
            properties = {}
            for _, r in df.iterrows():
                prop = r["property"]
                depth = r["depth"]
                val = float(r["value"])
                unit = r["unit"]
                if prop not in properties:
                    properties[prop] = {"unit": unit, "depths": {}}
                properties[prop]["depths"][depth] = val

            # Agronomic diagnostics
            ph = properties.get("phh2o", {}).get("depths", {}).get("0-5cm", 7.3)
            clay = properties.get("clay", {}).get("depths", {}).get("0-5cm", 38.1)
            sand = properties.get("sand", {}).get("depths", {}).get("0-5cm", 33.8)
            silt = properties.get("silt", {}).get("depths", {}).get("0-5cm", 28.1)
            soc = properties.get("soc", {}).get("depths", {}).get("0-5cm", 31.8)
            cec = properties.get("cec", {}).get("depths", {}).get("0-5cm", 27.0)

            soil_texture = "Clay Loam"
            if clay > 40:
                soil_texture = "Clay"
            elif sand > 50:
                soil_texture = "Sandy Loam"

            ph_classification = "Neutral (Optimal)" if 6.5 <= ph <= 7.5 else "Slightly Alkaline" if ph > 7.5 else "Acidic"
            fertility_status = "High CEC & Medium Organic Carbon" if cec > 20 else "Moderate Fertility"

            return {
                "source": "ISRIC SoilGrids v2.0 (250m Global Resolution)",
                "location": {"lat": lat, "lon": lon, "region": "Ariyalur, Tamil Nadu"},
                "texture_class": soil_texture,
                "ph": {"value": ph, "classification": ph_classification},
                "texture": {
                    "clay_pct": clay,
                    "sand_pct": sand,
                    "silt_pct": silt
                },
                "organic_carbon_g_kg": soc,
                "cation_exchange_capacity": cec,
                "bulk_density": properties.get("bdod", {}).get("depths", {}).get("0-5cm", 1.43),
                "fertility_assessment": fertility_status,
                "water_retention_capacity": "High (Clay-rich profile, suitable for lowland rice and black cotton soil)"
            }
        except Exception as e:
            return {
                "source": "Default Agronomic Profile",
                "texture_class": "Clay Loam",
                "ph": {"value": 7.3, "classification": "Neutral (Optimal)"},
                "water_retention_capacity": "High"
            }

soil_service = SoilService()
