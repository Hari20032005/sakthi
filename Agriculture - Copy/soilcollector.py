"""
Step 3 of the data pipeline: Soil properties for Ariyalur.
Uses SoilGrids v2.0 (ISRIC), free, no API key required, global coverage
at 250m resolution.

Docs: https://rest.isric.org/soilgrids/v2.0/docs

Design notes (learned from real failures):
- SoilGrids is slow and prone to timeout when a single request asks for
  many properties x depths at once. So we query ONE property at a time
  (all 3 depths together), not all 8 properties in one call.
- SoilGrids masks out water/urban/quarry pixels -- if the exact point
  falls on one, "mean" comes back null. We nudge outward to nearby
  points until we find valid farmland data.
- Each point+property request gets its own retry-with-backoff, since
  ISRIC's server is known to be intermittently slow, not just down.
"""

import time
import requests
import pandas as pd

LATITUDE = 11.137
LONGITUDE = 79.078
LOCATION_NAME = "Ariyalur"

COORD_OFFSETS = [
    (0, 0),
    (0.01, 0), (-0.01, 0), (0, 0.01), (0, -0.01),                    # ~1.1 km
    (0.02, 0.02), (-0.02, -0.02), (0.02, -0.02), (-0.02, 0.02),      # ~2.2 km
]

BASE_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"

# Properties relevant to crop yield modeling:
# clay/sand/silt -- soil texture, affects water retention
# phh2o -- soil pH (in water)
# soc -- soil organic carbon (fertility indicator)
# nitrogen -- total nitrogen
# cec -- cation exchange capacity (nutrient-holding capacity)
# bdod -- bulk density
PROPERTIES = ["clay", "sand", "silt", "phh2o", "soc", "nitrogen", "cec", "bdod"]

DEPTHS = ["0-5cm", "5-15cm", "15-30cm"]

CONVERSION_FACTORS = {
    "bdod": (100, "kg/dm3"),
    "cec": (10, "cmol(c)/kg"),
    "clay": (10, "%"),
    "sand": (10, "%"),
    "silt": (10, "%"),
    "nitrogen": (100, "g/kg"),
    "phh2o": (10, "pH"),
    "soc": (10, "g/kg"),
}


def _query_one_property(lat, lon, property_name, max_retries=3, base_timeout=90):
    """Query a single property (all depths) at one point, with retry-with-backoff."""
    params = {
        "lon": lon,
        "lat": lat,
        "property": property_name,
        "depth": DEPTHS,
        "value": "mean",
    }
    last_error = None
    for attempt in range(1, max_retries + 1):
        timeout = base_timeout + (attempt - 1) * 30  # grow timeout each retry
        try:
            resp = requests.get(BASE_URL, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            last_error = e
            print(f"    [{property_name}] attempt {attempt}/{max_retries} failed "
                  f"({type(e).__name__}), retrying...")
            time.sleep(3 * attempt)
    print(f"    [{property_name}] gave up after {max_retries} attempts: {last_error}")
    return None


def _has_data(result) -> bool:
    if not result:
        return False
    layers = result.get("properties", {}).get("layers", [])
    return bool(layers) and any(
        d["values"].get("mean") is not None
        for layer in layers for d in layer["depths"]
    )


def fetch_soil_data() -> pd.DataFrame:
    rows = []

    for prop_name in PROPERTIES:
        print(f"Fetching '{prop_name}'...")
        found = False

        for dlat, dlon in COORD_OFFSETS:
            test_lat, test_lon = LATITUDE + dlat, LONGITUDE + dlon
            result = _query_one_property(test_lat, test_lon, prop_name)

            if _has_data(result):
                if (dlat, dlon) != (0, 0):
                    print(f"  Exact point masked -- used nearby point "
                          f"({test_lat:.4f}, {test_lon:.4f}), ~"
                          f"{max(abs(dlat), abs(dlon)) * 111:.1f} km offset.")
                factor, unit = CONVERSION_FACTORS.get(prop_name, (1, "raw"))
                for layer in result["properties"]["layers"]:
                    for depth_info in layer["depths"]:
                        raw_val = depth_info["values"].get("mean")
                        rows.append({
                            "location": LOCATION_NAME,
                            "query_lat": test_lat,
                            "query_lon": test_lon,
                            "property": prop_name,
                            "depth": depth_info["label"],
                            "raw_value": raw_val,
                            "value": raw_val / factor if raw_val is not None else None,
                            "unit": unit,
                        })
                found = True
                break
            else:
                print(f"  No data at ({test_lat:.4f}, {test_lon:.4f}), trying next offset...")

        if not found:
            print(f"  !! Could not get '{prop_name}' at any offset -- skipping it. "
                  f"You can add it manually or widen COORD_OFFSETS.")

    return pd.DataFrame(rows)


if __name__ == "__main__":
    print(f"Fetching soil data for {LOCATION_NAME} ({LATITUDE}, {LONGITUDE})...")
    df = fetch_soil_data()
    df.to_csv("data_soil_ariyalur.csv", index=False)
    print(f"\nSaved {len(df)} soil property/depth rows -> data_soil_ariyalur.csv")
    print(df.to_string())