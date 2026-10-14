import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Database Configuration
DB_CONFIG = {
    "dbname": os.environ.get("DB_NAME", "agri_digital_twin"),
    "user": os.environ.get("DB_USER", "agri_user"),
    "password": os.environ.get("DB_PASSWORD", "agri_pass"),
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
}

# Fallback SQLite DB path if PostgreSQL is unavailable
SQLITE_DB_PATH = BASE_DIR / "agri_digital_twin.sqlite3"

# Data Files Paths
DATA_DIR = BASE_DIR
TRAINING_DATA_FILE = BASE_DIR / "training_data_ariyalur_full.csv"
SOIL_DATA_FILE = BASE_DIR / "data_soil_ariyalur.csv"
WEATHER_HISTORICAL_FILE = BASE_DIR / "data_historical_weather_ariyalur_2008_2019.csv"
WEATHER_FORECAST_FILE = BASE_DIR / "data_forecast_weather_ariyalur.csv"
PRICE_DATA_FILE = BASE_DIR / "data_prices_ariyalur_tamilnadu_2001_2026.csv"
YIELD_DATA_FILE = BASE_DIR / "data_yield_ariyalur_rice_cotton_clean.csv"

# Security
SECRET_KEY = os.environ.get("SECRET_KEY", "agri-digital-twin-secret-key-2026")
JWT_ALGORITHM = "HS256"

# Server Ports
API_PORT = int(os.environ.get("PORT", 5000))
API_HOST = os.environ.get("HOST", "0.0.0.0")

# Optional Gemini API Key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Optional Copernicus Data Space Ecosystem OAuth client. When configured, the
# twin upgrades its vegetation layer from the academic proxy to Sentinel-2 L2A
# NDVI statistics.
COPERNICUS_CLIENT_ID = os.environ.get("COPERNICUS_CLIENT_ID", "")
COPERNICUS_CLIENT_SECRET = os.environ.get("COPERNICUS_CLIENT_SECRET", "")

# Optional Google Earth Engine project. With a locally authenticated Earth
# Engine profile this is the preferred real-NDVI provider for the prototype.
GOOGLE_EARTH_ENGINE_PROJECT = os.environ.get("GOOGLE_EARTH_ENGINE_PROJECT", "")
