-- Agriculture Farm Digital Twin -- PostGIS schema
-- Mirrors the class diagram: User -> Farmer/CooperativeAdmin, Farm,
-- WeatherRecord, SatelliteIndex, YieldForecast, PriceForecast,
-- ScenarioSimulation, Explanation, ChatSession.

CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------- Users ----------
CREATE TABLE users (
    user_id      SERIAL PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    role         VARCHAR(20) NOT NULL CHECK (role IN ('farmer', 'cooperative_admin')),
    contact_number     VARCHAR(20),          -- used when role = 'farmer'
    organization_name  VARCHAR(150)          -- used when role = 'cooperative_admin'
);

-- ---------- Farms ----------
-- Farm location is a real PostGIS geometry -- this is what makes the
-- "digital shadow" spatial rather than just a plain database.
CREATE TABLE farms (
    farm_id        SERIAL PRIMARY KEY,
    owner_id       INTEGER NOT NULL REFERENCES users(user_id),
    farm_name      VARCHAR(100),
    location       GEOMETRY(Point, 4326) NOT NULL,   -- 4326 = standard lat/lon (WGS84)
    size_hectares  NUMERIC(10,2),
    soil_type      VARCHAR(50)
);
CREATE INDEX idx_farms_location ON farms USING GIST (location);

-- ---------- Weather records ----------
CREATE TABLE weather_records (
    record_id       SERIAL PRIMARY KEY,
    farm_id         INTEGER NOT NULL REFERENCES farms(farm_id),
    record_date     DATE NOT NULL,
    rainfall_mm     NUMERIC(8,2),
    temp_max_c      NUMERIC(5,2),
    temp_min_c      NUMERIC(5,2),
    temp_mean_c     NUMERIC(5,2),
    et0_mm          NUMERIC(8,2),
    wind_speed_kmh  NUMERIC(6,2),
    UNIQUE (farm_id, record_date)
);
CREATE INDEX idx_weather_farm_date ON weather_records (farm_id, record_date);

-- ---------- Satellite vegetation index ----------
CREATE TABLE satellite_index (
    index_id     SERIAL PRIMARY KEY,
    farm_id      INTEGER NOT NULL REFERENCES farms(farm_id),
    record_date  DATE NOT NULL,
    ndvi         NUMERIC(5,3),
    evi          NUMERIC(5,3),
    UNIQUE (farm_id, record_date)
);

-- ---------- Soil properties (static per farm, per the design decision
-- to treat soil as constant at this prototype scale) ----------
CREATE TABLE soil_properties (
    soil_id     SERIAL PRIMARY KEY,
    farm_id     INTEGER NOT NULL REFERENCES farms(farm_id),
    property    VARCHAR(30) NOT NULL,   -- e.g. 'clay', 'phh2o', 'soc'
    depth_cm    VARCHAR(20) NOT NULL,   -- e.g. '0-5cm'
    value       NUMERIC(10,3),
    unit        VARCHAR(20),
    UNIQUE (farm_id, property, depth_cm)
);

-- ---------- Price records ----------
CREATE TABLE price_records (
    price_id       SERIAL PRIMARY KEY,
    farm_id        INTEGER REFERENCES farms(farm_id),   -- nullable: some price data is market-level, not farm-specific
    market_name    VARCHAR(100),
    commodity      VARCHAR(50) NOT NULL,
    arrival_date   DATE NOT NULL,
    min_price      NUMERIC(10,2),
    max_price      NUMERIC(10,2),
    modal_price    NUMERIC(10,2)
);
CREATE INDEX idx_price_commodity_date ON price_records (commodity, arrival_date);

-- ---------- Yield forecasts (model output) ----------
CREATE TABLE yield_forecasts (
    forecast_id       SERIAL PRIMARY KEY,
    farm_id           INTEGER NOT NULL REFERENCES farms(farm_id),
    crop_type         VARCHAR(50) NOT NULL,
    season            VARCHAR(20) NOT NULL,
    crop_year         INTEGER NOT NULL,
    predicted_yield   NUMERIC(6,2) NOT NULL,
    confidence_low    NUMERIC(6,2),
    confidence_high   NUMERIC(6,2),
    generated_at      TIMESTAMP DEFAULT NOW()
);

-- ---------- Explanations (SHAP output, linked 1:1 to a forecast) ----------
CREATE TABLE explanations (
    explanation_id  SERIAL PRIMARY KEY,
    forecast_id     INTEGER NOT NULL UNIQUE REFERENCES yield_forecasts(forecast_id),
    top_factors     JSONB NOT NULL   -- e.g. [{"feature": "avg_modal_price", "impact": 0.24}, ...]
);

-- ---------- Scenario simulations (what-if results, linked to a forecast) ----------
CREATE TABLE scenario_simulations (
    scenario_id        SERIAL PRIMARY KEY,
    forecast_id        INTEGER NOT NULL REFERENCES yield_forecasts(forecast_id),
    scenario_label      VARCHAR(150) NOT NULL,   -- e.g. "Drought (-40% rainfall)"
    parameters          JSONB,                   -- the overrides used for this scenario
    predicted_outcome   NUMERIC(6,2) NOT NULL,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ---------- Chat sessions (chatbot conversation log) ----------
CREATE TABLE chat_sessions (
    session_id    SERIAL PRIMARY KEY,
    farmer_id     INTEGER NOT NULL REFERENCES users(user_id),
    farm_id       INTEGER REFERENCES farms(farm_id),
    started_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE chat_messages (
    message_id    SERIAL PRIMARY KEY,
    session_id    INTEGER NOT NULL REFERENCES chat_sessions(session_id),
    sender        VARCHAR(10) NOT NULL CHECK (sender IN ('farmer', 'bot')),
    message_text  TEXT NOT NULL,
    sent_at       TIMESTAMP DEFAULT NOW()
);