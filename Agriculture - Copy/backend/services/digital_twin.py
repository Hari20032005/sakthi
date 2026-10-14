from backend.services.weather_service import weather_service
from backend.services.soil_service import soil_service
from backend.services.satellite_service import satellite_service
from backend.services.ndvi_service import ndvi_service
from backend.services.recommendation_engine import recommendation_engine
from backend.services.weather_adjustment_service import weather_adjustment_service
from backend.models.yield_model import yield_forecaster
from backend.models.price_model import price_forecaster
from backend.services.farm_repository import farm_repository
from datetime import datetime, timezone

class DigitalTwinService:
    @staticmethod
    def get_farm_digital_shadow(farm_id: int = 1):
        """
        Synthesizes the complete sensor-free Digital Shadow of a farm:
        Spatial Coordinates + Weather Telemetry + Soil Profile + Satellite NDVI + Historical Yields + Mandi Prices.
        """
        farm_info = farm_repository.get_farm(farm_id)
        if not farm_info:
            raise ValueError("Farm not found")

        lat, lon = farm_info["latitude"], farm_info["longitude"]
        crop = farm_info["primary_crop"]
        season = farm_info["current_season"]
        weather_data = weather_service.get_forecast(lat=lat, lon=lon, days=7)
        soil_profile = soil_service.get_soil_profile(lat=lat, lon=lon)
        real_ndvi_observations = ndvi_service.get_or_fetch(farm_info)
        if real_ndvi_observations:
            satellite_data = satellite_service.from_real_observations(farm_id, crop, season, real_ndvi_observations)
        else:
            satellite_data = satellite_service.get_vegetation_indices(farm_id=farm_id, crop=crop, season=season, sowing_date=farm_info.get("sowing_date"))
        yield_pred = yield_forecaster.predict(crop=crop, season=season)
        weather_adjusted_yield = weather_adjustment_service.build(
            farm_info, yield_pred, weather_data.get("forecast", [])
        )
        price_pred = price_forecaster.forecast_prices("Rice" if "rice" in crop.lower() else "Cotton", months_ahead=3)

        # Generate intelligent automated agronomy alerts
        alerts = []
        forecast_list = weather_data.get("forecast", [])
        if forecast_list:
            max_temp = max(f.get("temp_max") or 0 for f in forecast_list)
            total_rain = sum(f.get("rainfall_mm") or 0 for f in forecast_list)
            if max_temp > 37.0:
                alerts.append({
                    "severity": "WARNING",
                    "type": "HEAT_STRESS",
                    "title": "High Heat Alert",
                    "message": f"Expected daytime peak of {max_temp}°C in the next 7 days. Ensure evening irrigation to prevent panicle blasting."
                })
            if total_rain < 5.0:
                alerts.append({
                    "severity": "INFO",
                    "type": "DRY_SPELL",
                    "title": "Dry Spell Anticipated",
                    "message": f"Only {round(total_rain, 1)} mm rain forecast over 7 days. Soil clay profile retains moisture well, but check seedling bed."
                })

        if satellite_data.get("current_ndvi", 0) > 0.6:
            vegetation_label = "Latest Sentinel-2 NDVI observation" if satellite_data.get("is_live_satellite_observation") else "Modelled vegetation proxy"
            evidence_note = "Use this together with field inspection." if satellite_data.get("is_live_satellite_observation") else "This is a demonstration indicator, not a live satellite measurement."
            alerts.append({
                "severity": "SUCCESS",
                "type": "HEALTHY_CANOPY",
                "title": "Optimal Canopy Photosynthesis",
                "message": f"{vegetation_label} is {satellite_data['current_ndvi']} ({satellite_data['canopy_vigor']}). {evidence_note}"
            })

        twin = {
            "farm_id": farm_info["farm_id"],
            "farm_name": farm_info["farm_name"],
            "owner_name": farm_info["owner_name"],
            "location": {
                "latitude": lat,
                "longitude": lon,
                "district": farm_info["district"],
                "state": farm_info["state"],
                "pin_code": "621704"
            },
            "farm_specs": {
                "size_hectares": float(farm_info.get("size_hectares", 5.0)),
                "size_acres": round(float(farm_info.get("size_hectares", 5.0)) * 2.47105, 1),
                "active_crop": crop,
                "active_season": season,
                "sowing_date": farm_info.get("sowing_date")
            },
            "digital_twin_status": {
                "sensors_installed": 0,
                "data_source_mode": "Farm-specific, sensor-free academic digital twin",
                "last_sync": datetime.now(timezone.utc).isoformat(),
                "state_version": "1.0",
                "synchronization_sources": [
                    "Open-Meteo & NOAA GFS Weather API",
                    "Open-Meteo historical weather / local climatology fallback",
                    "ISRIC SoilGrids 250m Global Earth Map",
                satellite_data["sensor_source"],
                    "Ministry of Agriculture APY Historical Database",
                    "AGMARKNET Mandi Price Arrivals"
                ]
            },
            "weather": weather_data,
            "soil": soil_profile,
            "satellite_vegetation": satellite_data,
            "current_yield_forecast": yield_pred,
            "weather_adjusted_yield_forecast": weather_adjusted_yield,
            "market_price_outlook": price_pred,
            "recent_management_events": farm_repository.recent_management_events(farm_id),
            "active_alerts": alerts
        }
        twin["recommendations"] = recommendation_engine.recommend(twin)
        snapshot = farm_repository.save_snapshot(farm_id, twin)
        twin["twin_state"] = {
            "snapshot_id": snapshot["snapshot_id"],
            "generated_at": snapshot["generated_at"],
            "state_version": snapshot["state_version"],
            "snapshot_created": snapshot["created"],
            "farm_inputs_used": ["farm location", "crop", "season", "sowing date", "area"],
            "academic_disclosure": (
                "Weather may be live or cached. Soil is a local SoilGrids-derived baseline. "
                + ("Vegetation is sourced from Sentinel-2 L2A and should be verified in the field."
                   if satellite_data.get("is_live_satellite_observation")
                   else "Vegetation is a deterministic modelled proxy, not live satellite imagery.")
            )
        }
        return twin

digital_twin_service = DigitalTwinService()
