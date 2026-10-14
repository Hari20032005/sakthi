"""Real Sentinel-2 L2A NDVI retrieval for the academic digital twin.

Copernicus OAuth is supported when credentials are available.  The default
fallback is Microsoft Planetary Computer's anonymous STAC/SAS access, so this
academic project can retrieve real observations without a user account.
"""
from datetime import datetime, timedelta, timezone

import requests

from backend.config import COPERNICUS_CLIENT_ID, COPERNICUS_CLIENT_SECRET, GOOGLE_EARTH_ENGINE_PROJECT
from backend.services.farm_repository import farm_repository

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
STATS_URL = "https://sh.dataspace.copernicus.eu/statistics/v1"
SOURCE = "Copernicus Sentinel-2 L2A Statistical API"
PC_STAC_SEARCH_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
PC_SIGN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
PC_SOURCE = "Microsoft Planetary Computer Sentinel-2 L2A"
GEE_SOURCE = "Google Earth Engine Sentinel-2 SR Harmonized"

NDVI_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "SCL", "dataMask"] }],
    output: [
      { id: "ndvi", bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}
function evaluatePixel(sample) {
  // Keep vegetation and bare-soil pixels; exclude clouds, cloud shadows,
  // cirrus, water, snow and no-data pixels using Sentinel-2's SCL layer.
  const valid = sample.dataMask && (sample.SCL === 4 || sample.SCL === 5);
  const ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
  return { ndvi: [ndvi], dataMask: [valid ? 1 : 0] };
}
"""


class NDVIService:
    def is_configured(self):
        return bool(COPERNICUS_CLIENT_ID and COPERNICUS_CLIENT_SECRET)

    def is_gee_configured(self):
        return bool(GOOGLE_EARTH_ENGINE_PROJECT)

    def get_or_fetch(self, farm):
        """Return real observations, querying only when cache is stale."""
        cached = farm_repository.get_ndvi_observations(farm["farm_id"])
        if cached:
            try:
                newest = datetime.fromisoformat(cached[-1]["fetched_at"])
                if datetime.now(timezone.utc) - newest < timedelta(hours=24):
                    return cached
            except (KeyError, ValueError, TypeError):
                pass
        try:
            if self.is_gee_configured():
                observations = self._fetch_google_earth_engine(farm)
            elif self.is_configured():
                observations = self._fetch_statistics(farm)
            else:
                observations = self._fetch_planetary_computer(farm)
            if observations:
                farm_repository.save_ndvi_observations(farm["farm_id"], observations)
                return farm_repository.get_ndvi_observations(farm["farm_id"])
        except (requests.RequestException, ImportError, OSError, ValueError, RuntimeError):
            # Existing verified observations remain preferable to a proxy.
            return cached
        return cached

    def _fetch_google_earth_engine(self, farm):
        """Compute median cloud-masked Sentinel-2 NDVI over a farm point buffer."""
        import ee

        try:
            ee.Initialize(project=GOOGLE_EARTH_ENGINE_PROJECT)
        except Exception as exc:
            raise RuntimeError("Google Earth Engine is not authenticated") from exc

        lat, lon = float(farm["latitude"]), float(farm["longitude"])
        geometry = ee.Geometry.Point([lon, lat]).buffer(180)
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=90)
        collection = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(geometry)
            .filterDate(str(start), str(end + timedelta(days=1)))
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 35))
        )
        if collection.size().getInfo() == 0:
            return []
        image = ee.Image(collection.sort("CLOUDY_PIXEL_PERCENTAGE").first())
        scl = image.select("SCL")
        valid_mask = scl.eq(4).Or(scl.eq(5))  # vegetation or bare soil
        ndvi = image.normalizedDifference(["B8", "B4"]).rename("ndvi").updateMask(valid_mask)
        total_pixels = ee.Image.constant(1).reduceRegion(
            reducer=ee.Reducer.count(), geometry=geometry, scale=10, maxPixels=100000
        ).get("constant")
        valid_pixels = ee.Image.constant(1).updateMask(valid_mask).reduceRegion(
            reducer=ee.Reducer.count(), geometry=geometry, scale=10, maxPixels=100000
        ).get("constant")
        median_ndvi = ndvi.reduceRegion(
            reducer=ee.Reducer.median(), geometry=geometry, scale=10, maxPixels=100000
        ).get("ndvi")
        values = ee.Dictionary({
            "total": total_pixels, "valid": valid_pixels, "ndvi": median_ndvi,
            "date": image.date().format("YYYY-MM-dd"),
        }).getInfo()
        if values.get("ndvi") is None or not values.get("total"):
            return []
        valid_pct = round(100 * values["valid"] / values["total"], 1)
        if valid_pct < 5:
            return []
        return [{
            "date": values["date"], "ndvi": round(float(values["ndvi"]), 3),
            "valid_pixel_pct": valid_pct, "source": GEE_SOURCE,
        }]

    def _access_token(self):
        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": COPERNICUS_CLIENT_ID,
                "client_secret": COPERNICUS_CLIENT_SECRET,
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def _fetch_statistics(self, farm):
        # A small bounding box is used until farm-polygon capture is added.
        # It is explicitly surfaced in the UI as a point-buffer observation.
        delta = 0.0015
        lat, lon = float(farm["latitude"]), float(farm["longitude"])
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=90)
        payload = {
            "input": {
                "bounds": {
                    "bbox": [lon - delta, lat - delta, lon + delta, lat + delta],
                    "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
                },
                "data": [{"type": "sentinel-2-l2a", "dataFilter": {"maxCloudCoverage": 40}}],
            },
            "aggregation": {
                "timeRange": {"from": f"{start}T00:00:00Z", "to": f"{end}T23:59:59Z"},
                "aggregationInterval": {"of": "P10D", "lastIntervalBehavior": "SHORTEN"},
                "evalscript": NDVI_EVALSCRIPT,
                "width": 64,
                "height": 64,
            },
        }
        response = requests.post(
            STATS_URL,
            headers={"Authorization": f"Bearer {self._access_token()}", "Content-Type": "application/json"},
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        observations = []
        for interval in response.json().get("data", []):
            band = interval.get("outputs", {}).get("ndvi", {}).get("bands", {}).get("B0", {})
            stats = band.get("stats", {})
            samples = stats.get("sampleCount", 0)
            missing = stats.get("noDataCount", 0)
            if not samples or stats.get("mean") is None:
                continue
            valid_pct = round(100 * samples / max(1, samples + missing), 1)
            if valid_pct < 5:
                continue
            observations.append({
                "date": interval["interval"]["from"][:10],
                "ndvi": round(float(stats["mean"]), 3),
                "valid_pixel_pct": valid_pct,
                "source": SOURCE,
            })
        return observations

    def _fetch_planetary_computer(self, farm):
        """Search public STAC, then read only a small field buffer from COGs."""
        # Rasterio is imported only here: the rest of the application remains
        # usable if its optional geospatial dependency is not installed.
        import numpy as np
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.windows import from_bounds
        from rasterio.warp import transform_bounds

        delta = 0.0015
        lat, lon = float(farm["latitude"]), float(farm["longitude"])
        bbox = [lon - delta, lat - delta, lon + delta, lat + delta]
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=90)
        response = requests.post(
            PC_STAC_SEARCH_URL,
            json={
                "collections": ["sentinel-2-l2a"], "bbox": bbox,
                "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
                "query": {"eo:cloud_cover": {"lt": 30}}, "limit": 8,
            },
            timeout=20,
        )
        response.raise_for_status()
        scenes = response.json().get("features", [])
        scenes.sort(key=lambda scene: (
            scene.get("properties", {}).get("eo:cloud_cover") or 100,
            scene.get("properties", {}).get("datetime") or "",
        ))

        def signed_url(href):
            signed = requests.get(PC_SIGN_URL, params={"href": href}, timeout=15)
            signed.raise_for_status()
            return signed.json()["href"]

        def read_buffer(dataset, output_shape=None):
            projected_bounds = transform_bounds("EPSG:4326", dataset.crs, *bbox, densify_pts=8)
            window = from_bounds(*projected_bounds, transform=dataset.transform).round_offsets().round_lengths()
            if output_shape:
                return dataset.read(1, window=window, out_shape=output_shape, masked=True, resampling=Resampling.nearest)
            return dataset.read(1, window=window, masked=True)

        for scene in scenes:
            assets = scene.get("assets", {})
            if not all(key in assets for key in ("B04", "B08", "SCL")):
                continue
            try:
                with rasterio.open(signed_url(assets["B04"]["href"])) as red_ds, \
                     rasterio.open(signed_url(assets["B08"]["href"])) as nir_ds, \
                     rasterio.open(signed_url(assets["SCL"]["href"])) as scl_ds:
                    red = read_buffer(red_ds)
                    if red.size == 0:
                        continue
                    nir = read_buffer(nir_ds, red.shape)
                    scl = read_buffer(scl_ds, red.shape)
                    valid = (~np.ma.getmaskarray(red) & ~np.ma.getmaskarray(nir) & ~np.ma.getmaskarray(scl)
                             & ((scl.data == 4) | (scl.data == 5)))
                    denominator = red.data.astype(float) + nir.data.astype(float)
                    valid &= denominator != 0
                    if not valid.any():
                        continue
                    ndvi = (nir.data.astype(float) - red.data.astype(float)) / denominator
                    valid_pct = round(100 * valid.sum() / valid.size, 1)
                    if valid_pct < 5:
                        continue
                    observation_date = scene.get("properties", {}).get("datetime", "")[:10]
                    return [{
                        "date": observation_date,
                        "ndvi": round(float(np.median(ndvi[valid])), 3),
                        "valid_pixel_pct": valid_pct,
                        "source": PC_SOURCE,
                    }]
            except (requests.RequestException, rasterio.errors.RasterioError, KeyError, ValueError):
                continue
        return []


ndvi_service = NDVIService()
