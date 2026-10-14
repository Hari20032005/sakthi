"""
Loads the CSV outputs from the data pipeline (weather, yield, soil,
price) into the PostGIS database, for the Ariyalur farm specifically.
This is what turns the "digital shadow" from a folder of CSVs into an
actual queryable, spatial database, matching the system architecture.

Run schema.sql first to create the tables, then run this to populate them.
"""

import psycopg2
from psycopg2.extras import execute_values
import pandas as pd

DB_CONFIG = {
    "dbname": "agri_digital_twin",
    "user": "agri_user",
    "password": "agri_pass",
    "host": "localhost",
    "port": 5432,
}

ARIYALUR_LAT = 11.137
ARIYALUR_LON = 79.078


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def setup_demo_user_and_farm(conn):
    """Creates one demo farmer + their Ariyalur farm, if not already present."""
    with conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users WHERE name = %s", ("Demo Farmer",))
        row = cur.fetchone()
        if row:
            user_id = row[0]
        else:
            cur.execute(
                "INSERT INTO users (name, role, contact_number) VALUES (%s, %s, %s) RETURNING user_id",
                ("Demo Farmer", "farmer", "9840000000"),
            )
            user_id = cur.fetchone()[0]

        cur.execute("SELECT farm_id FROM farms WHERE owner_id = %s", (user_id,))
        row = cur.fetchone()
        if row:
            farm_id = row[0]
        else:
            cur.execute(
                """INSERT INTO farms (owner_id, farm_name, location, size_hectares, soil_type)
                   VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s)
                   RETURNING farm_id""",
                (user_id, "Ariyalur Demo Farm", ARIYALUR_LON, ARIYALUR_LAT, 5.0, "Clay loam"),
            )
            farm_id = cur.fetchone()[0]

        conn.commit()
        return user_id, farm_id


def load_weather(conn, farm_id, csv_path):
    df = pd.read_csv(csv_path, parse_dates=["date"])
    rows = [
        (farm_id, r["date"].date(), r.get("precipitation_sum"), r.get("temperature_2m_max"),
         r.get("temperature_2m_min"), r.get("temperature_2m_mean"),
         r.get("et0_fao_evapotranspiration"), r.get("wind_speed_10m_max"))
        for _, r in df.iterrows()
    ]
    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO weather_records
              (farm_id, record_date, rainfall_mm, temp_max_c, temp_min_c, temp_mean_c, et0_mm, wind_speed_kmh)
            VALUES %s
            ON CONFLICT (farm_id, record_date) DO NOTHING
        """, rows)
    conn.commit()
    print(f"  Loaded {len(rows)} weather records")


def load_soil(conn, farm_id, csv_path):
    df = pd.read_csv(csv_path)
    rows = [(farm_id, r["property"], r["depth"], r["value"], r["unit"]) for _, r in df.iterrows()]
    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO soil_properties (farm_id, property, depth_cm, value, unit)
            VALUES %s
            ON CONFLICT (farm_id, property, depth_cm) DO NOTHING
        """, rows)
    conn.commit()
    print(f"  Loaded {len(rows)} soil property records")


def load_prices(conn, farm_id, csv_path):
    df = pd.read_csv(csv_path, parse_dates=["Arrival_Date"])
    rows = [
        (farm_id, r.get("Market"), r["Commodity"], r["Arrival_Date"].date(),
         r.get("Min_Price"), r.get("Max_Price"), r.get("Modal_Price"))
        for _, r in df.iterrows()
    ]
    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO price_records (farm_id, market_name, commodity, arrival_date, min_price, max_price, modal_price)
            VALUES %s
        """, rows)
    conn.commit()
    print(f"  Loaded {len(rows)} price records")


def load_yield_forecasts(conn, farm_id, csv_path):
    """Loads the HISTORICAL yield records as 'forecasts' with no confidence
    interval (they're ground truth, not predictions) -- real model
    predictions would be inserted here going forward by the forecasting
    service instead."""
    df = pd.read_csv(csv_path)
    rows = [
        (farm_id, r["Crop"], r["Season"], int(r["Crop_Year"]), r["Yield"])
        for _, r in df.iterrows()
    ]
    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO yield_forecasts (farm_id, crop_type, season, crop_year, predicted_yield)
            VALUES %s
        """, rows)
    conn.commit()
    print(f"  Loaded {len(rows)} historical yield records")


if __name__ == "__main__":
    conn = get_connection()
    print("Connected to database.")

    user_id, farm_id = setup_demo_user_and_farm(conn)
    print(f"Using farm_id={farm_id} for Ariyalur demo farm (owner user_id={user_id})")

    print("\nLoading weather...")
    load_weather(conn, farm_id, "data_historical_weather_ariyalur_2008_2019.csv")

    print("Loading soil...")
    load_soil(conn, farm_id, "data_soil_ariyalur.csv")

    print("Loading prices...")
    load_prices(conn, farm_id, "data_prices_ariyalur_tamilnadu_2001_2026.csv")

    print("Loading yield history...")
    load_yield_forecasts(conn, farm_id, "data_yield_ariyalur_rice_cotton_clean.csv")

    # Quick sanity check: a real spatial query
    with conn.cursor() as cur:
        cur.execute("""
            SELECT farm_name, ST_X(location) AS lon, ST_Y(location) AS lat, soil_type
            FROM farms WHERE farm_id = %s
        """, (farm_id,))
        print("\nFarm record (via spatial query):", cur.fetchone())

    conn.close()
    print("\nDone. Database now holds the full digital shadow for this farm.")