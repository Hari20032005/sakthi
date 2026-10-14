"""
Minimal test -- ONE property, ONE depth, and we print the complete raw JSON
response with no parsing at all. This tells us exactly what key holds
the actual number, instead of guessing.
"""

import requests
import json

LATITUDE = 11.137
LONGITUDE = 79.078

url = "https://rest.isric.org/soilgrids/v2.0/properties/query"
params = {
    "lon": LONGITUDE,
    "lat": LATITUDE,
    "property": "clay",
    "depth": "0-5cm",
    "value": "mean",
}

resp = requests.get(url, params=params, timeout=60)
print("Status code:", resp.status_code)
print("Final URL:", resp.url)
print("\nFull raw JSON response:")
print(json.dumps(resp.json(), indent=2))