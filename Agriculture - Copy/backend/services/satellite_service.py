import hashlib
from datetime import datetime, timedelta

class SatelliteService:
    @staticmethod
    def from_real_observations(farm_id, crop, season, observations):
        records = []
        for observation in observations:
            ndvi = round(float(observation["ndvi"]), 3)
            records.append({
                "date": observation["observation_date"],
                "phenology_stage": "Sentinel-2 L2A observation",
                "ndvi": ndvi,
                "evi": None,
                "health_status": "High-quality observation" if observation["valid_pixel_pct"] >= 50 else "Limited clear pixels",
                "valid_pixel_pct": observation["valid_pixel_pct"],
            })
        latest = records[-1]
        return {
            "farm_id": farm_id, "crop": crop, "season": season,
            "sensor_source": observations[-1]["source"],
            "observation_type": "REAL_SENTINEL_2_L2A",
            "is_live_satellite_observation": True,
            "current_ndvi": latest["ndvi"], "current_evi": None,
            "canopy_vigor": latest["health_status"],
            "moisture_stress_indicator": "Interpret with crop stage and field inspection",
            "time_series": records,
        }

    @staticmethod
    def get_vegetation_indices(farm_id: int = 1, crop: str = "Rice", season: str = "Kharif", sowing_date: str = None):
        """
        Deterministic academic phenology proxy. It is deliberately labelled as a
        modelled observation until a real Sentinel-2 connector is configured.
        """
        # 12-week phenological time-series for Kharif / Rabi
        stages = [
            ("Week 2: Sowing / Emergence", 0.22, 0.15),
            ("Week 4: Early Tillering", 0.38, 0.25),
            ("Week 6: Active Vegetative Growth", 0.58, 0.39),
            ("Week 8: Panicle Initiation / Flowering", 0.76, 0.52),
            ("Week 10: Grain Filling / Boll Maturation", 0.71, 0.48),
            ("Week 12: Physiological Maturity / Pre-Harvest", 0.45, 0.31),
        ]

        today = datetime.now()
        try:
            crop_start = datetime.strptime(sowing_date, "%Y-%m-%d") if sowing_date else today - timedelta(days=70)
        except ValueError:
            crop_start = today - timedelta(days=70)
        growth_day = max(0, min((today - crop_start).days, 118))
        active_index = min(len(stages) - 2, max(0, growth_day // 20))
        seed = int(hashlib.sha256(f"{farm_id}|{crop}|{season}|{today.date()}".encode()).hexdigest()[:8], 16)
        time_series = []

        for i, (stage_name, base_ndvi, base_evi) in enumerate(stages):
            date_stamp = (crop_start + timedelta(days=i * 20)).strftime("%Y-%m-%d")
            # Stable variation enables a repeatable demonstration and testing.
            variation = (((seed + i * 17) % 41) - 20) / 1000
            ndvi_val = round(max(0, min(1, base_ndvi + variation)), 3)
            evi_val = round(max(0, min(1, base_evi + variation * 0.75)), 3)

            health_status = (
                "Excellent Canopy Vigor" if ndvi_val >= 0.7 else
                "Good Vegetative Cover" if ndvi_val >= 0.5 else
                "Moderate / Developing" if ndvi_val >= 0.35 else
                "Emergence / Bare Soil"
            )

            time_series.append({
                "date": date_stamp,
                "phenology_stage": stage_name,
                "ndvi": ndvi_val,
                "evi": evi_val,
                "health_status": health_status
            })

        current_record = time_series[active_index]
        return {
            "farm_id": farm_id,
            "crop": crop,
            "season": season,
            "sensor_source": "Academic phenology proxy (Sentinel-2 connector pending)",
            "observation_type": "MODELLED_DEMO",
            "is_live_satellite_observation": False,
            "growth_day": growth_day,
            "current_ndvi": current_record["ndvi"],
            "current_evi": current_record["evi"],
            "canopy_vigor": current_record["health_status"],
            "moisture_stress_indicator": "Modelled proxy; not a field or satellite measurement",
            "time_series": time_series
        }

satellite_service = SatelliteService()
