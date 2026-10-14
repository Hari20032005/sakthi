# AgriTwin India — Complete Project Handoff

## 1. Project identity and purpose

**Project name:** AgriTwin India / Sensor-Free Agriculture Digital Twin

**Purpose:** An academic web application that builds a persistent, farm-specific virtual representation of agricultural farms in and around Ariyalur, Tamil Nadu. It is designed to demonstrate a **sensor-free agricultural digital twin**: instead of depending on field IoT devices, it fuses farm registration data with external/public data, historical datasets, machine-learning models, and scenario simulation.

**Academic claim that is accurate:**

> The application is an on-demand synchronized, sensor-free, farm-specific academic digital twin. It persists a farm's identity and time-versioned state, combines weather, soil, vegetation, yield, and market layers, and reuses that state for forecasting, explainability, alerts, and what-if simulation.

**Do not claim:** continuous real-time synchronization, IoT sensor telemetry, parcel-polygon precision, or live satellite NDVI when the UI is showing the academic proxy fallback.

## 2. Current user-facing functions

1. **Farm digital-shadow dashboard**
   - Shows selected farm identity, coordinates, area, crop, season, sowing date, weather, soil, vegetation/NDVI, yield forecast, alerts, and data provenance.
   - Shows a versioned twin snapshot and a timeline of stored state snapshots.

2. **Farm profile management**
   - Lists farms and supports registration of a new farm with latitude, longitude, area, crop, soil type, and season.
   - New farms are persisted in SQLite, so they survive frontend refresh/restart.

3. **Yield forecasting**
   - Random Forest and Gradient Boosting models are trained at backend startup from the included historical training CSV.
   - Returns a point forecast and precomputed 90% conformal interval.

4. **Price forecasting**
   - Uses supplied historical mandi-price CSV data for Rice and Cotton categories.
   - The current approach is a heuristic trend/seasonality projection, not a fully fitted production time-series model.

5. **What-if scenario simulation**
   - Evaluates baseline, drought, supplemental irrigation, delayed sowing, crop-switch, and optional custom rainfall/temperature scenarios.
   - Produces yield, confidence interval, production, revenue, cost, and profit comparisons.

6. **Explainability**
   - SHAP-based explanation service returns feature impacts and plain-language text.

7. **Advisory chatbot**
   - Local rule/RAG-style agricultural responses combine twin facts with a small curated agronomy knowledge base.
   - Optional Gemini branch exists when `GEMINI_API_KEY` is set.

8. **Cooperative dashboard**
   - Aggregates currently registered farms and calculates expected production/revenue using the same forecast models.

9. **Recommendation layer**
   - Inspects live/current twin state through transparent academic rules for dry spell, heat, low real NDVI, and wide forecast uncertainty.
   - Runs the existing scenario engine for supplemental-irrigation comparisons when a dry-spell trigger is present.
   - Presents action, trigger evidence, expected scenario effect, confidence, data sources, and field-verification requirement.
   - A dashboard "Mark as done" action records a management event, which is included in the next twin state.

## 3. Digital-twin model

```text
Physical/registered farm
  (coordinates, area, crop, season, sowing date)
                    |
                    v
Farm-specific digital twin service
  ├─ weather forecast / fallback weather CSV
  ├─ SoilGrids-derived soil baseline
  ├─ real Sentinel-2 NDVI when available, otherwise labelled proxy
  ├─ yield-model prediction + uncertainty
  ├─ market-price projection
  └─ risk/health alerts
                    |
                    v
Persistent versioned twin snapshot in SQLite
                    |
                    v
Dashboard • history • scenarios • SHAP • chatbot • cooperative view
```

### The four defensible digital-twin characteristics

| Characteristic | Current implementation |
| --- | --- |
| Physical entity | Persistent farm profile: coordinates, area, crop, season, sowing date |
| Digital representation | Combined weather, soil, vegetation, forecast, market, and alert state |
| Data connection | Weather is fetched on demand; NDVI provider can fetch real Sentinel-2; data/fallback status is exposed |
| State/history/use | Snapshot storage, timeline, forecasting, scenario simulation, explanations, and advice |

## 4. Technology stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, Vite 8, Tailwind CSS, Recharts, Lucide icons |
| Backend | Python, Flask, Flask-CORS |
| Persistent demo database | SQLite (`agri_digital_twin.sqlite3`) |
| Future/optional spatial database | PostgreSQL/PostGIS schema in `scema.sql` |
| ML/data | pandas, NumPy, scikit-learn, SHAP, PyTorch benchmark code |
| Weather | Open-Meteo forecast API with local CSV fallback |
| Vegetation | Google Earth Engine preferred; Copernicus optional; Microsoft Planetary Computer anonymous fallback; deterministic proxy final fallback |

## 5. Directory map

```text
Agriculture - Copy/
├─ backend/
│  ├─ app.py                         Flask app and blueprint registration
│  ├─ config.py                      paths, ports, optional API configuration
│  ├─ db.py                          older PostgreSQL/SQLite helper
│  ├─ routes/
│  │  ├─ farm_routes.py              farm CRUD, twin endpoint, history endpoint
│  │  ├─ forecast_routes.py          yield/price/benchmark endpoints
│  │  ├─ scenario_routes.py          scenario endpoints
│  │  ├─ explain_routes.py           SHAP endpoints
│  │  ├─ chat_routes.py              chatbot endpoints
│  │  ├─ auth_routes.py              demo/mock authentication only
│  │  └─ cooperative_routes.py       aggregation endpoint
│  ├─ services/
│  │  ├─ farm_repository.py          SQLite farms, snapshots, NDVI observations
│  │  ├─ digital_twin.py             builds the integrated farm twin state
│  │  ├─ weather_service.py          Open-Meteo then local fallback
│  │  ├─ soil_service.py             local SoilGrids-derived profile
│  │  ├─ satellite_service.py        proxy builder / converter for real NDVI records
│  │  ├─ ndvi_service.py             GEE/Copernicus/Planetary Computer real NDVI
│  │  ├─ recommendation_engine.py    rule-based and scenario-ranked recommendations
│  │  └─ rag_chatbot.py              local grounded advisory logic
│  └─ models/
│     ├─ yield_model.py              RF/GB/conformal model
│     ├─ price_model.py              market price projection
│     ├─ scenario_engine.py          simulation calculations
│     ├─ shap_engine.py              explainability
│     └─ deep_model.py               PyTorch comparison benchmark
├─ frontend/
│  ├─ src/App.jsx                    application shell and active-farm state
│  ├─ src/api/client.js              HTTP client
│  ├─ src/pages/Dashboard.jsx        main twin dashboard
│  ├─ src/pages/FarmManagement.jsx   farm registration/listing
│  └─ src/pages/...                  other views
├─ training_data_ariyalur_full.csv   training table
├─ data_*.csv                        prepared weather/soil/yield/price data
├─ requirements.txt                  Python dependencies
├─ run.py                            starts backend and frontend
├─ README.md                         project documentation
├─ DIGITAL_TWIN_EVIDENCE.md          viva/evaluator evidence and demo script
└─ PROJECT_HANDOFF.md                this document
```

## 6. Persistence and APIs

### SQLite tables created automatically by `FarmRepository`

| Table | Purpose |
| --- | --- |
| `twin_farms` | Farm profile: owner, coordinates, district/state, area, crop, season, sowing date |
| `twin_snapshots` | Serialized integrated twin state, time/version, and meaningful-state hash |
| `ndvi_observations` | NDVI date, value, valid-pixel percentage, provider/source, fetch timestamp |
| `management_events` | Completion events for twin recommendations and their notes |

### Important endpoints

| Endpoint | Method | Current purpose |
| --- | --- | --- |
| `/api/health` | GET | Backend health response |
| `/api/farms` | GET | List persistent farms |
| `/api/farms` | POST | Create persistent farm |
| `/api/farms/<id>` | GET | One farm profile |
| `/api/farms/<id>/digital-shadow` | GET | Build/read current integrated twin state; writes/reuses snapshot |
| `/api/farms/<id>/digital-shadow/history` | GET | Returns de-duplicated snapshot history |
| `/api/farms/<id>/weather-adjusted-yield` | GET | Transparent season-to-date weather overlay on the historic yield baseline |
| `/api/farms/<id>/recommendations` | GET | Generates transparent recommendation list from twin state |
| `/api/farms/<id>/recommendations/<id>/complete` | POST | Logs a completed recommendation as a management event |
| `/api/forecast/yield` | POST | Yield forecast and uncertainty |
| `/api/forecast/price` | GET | Price forecast |
| `/api/scenarios/simulate` | POST | Preset plus optional custom scenario set |
| `/api/scenarios/custom` | POST | One custom rainfall/temperature scenario |
| `/api/explain/prediction` | POST | Local SHAP explanation |
| `/api/chat/message` | POST | Advisory response |
| `/api/cooperative/summary` | GET | Aggregate data across persistent farms |

## 7. Data behavior and freshness

### Farm data

- Entered through the UI or seeded when SQLite has no farms.
- Persistent until database file is deleted.

### Weather

- `WeatherService.get_forecast()` calls Open-Meteo every time the twin endpoint is requested.
- It requests the selected farm's coordinates and seven forecast days.
- If that network call fails, it reads `data_forecast_weather_ariyalur.csv`.
- There is **no unattended daily scheduler** yet. The accurate term is **on-demand synchronized**.
- The yield card also reads season-to-date weather from the Open-Meteo historical API and combines it with the seven-day forecast. If history cannot be obtained, it uses the supplied Ariyalur climatology fallback.
- It does **not** retrain the Random Forest. It compares accumulated rainfall, ET0, temperature, and heat days with the historic crop-season pattern, applies a deliberately bounded adjustment (-12% to +5%), and widens the displayed interval. The dashboard calls this a **Weather-adjusted baseline**, never a new ML prediction.

### Soil

- `soil_service.py` reads `data_soil_ariyalur.csv`.
- This is a prepared SoilGrids-derived Ariyalur baseline; it is not an individual field soil test and is not refreshed daily.

### Vegetation / NDVI

Provider preference is:

1. **Google Earth Engine**, only when `GOOGLE_EARTH_ENGINE_PROJECT` is set and local Earth Engine authentication has completed.
   - Collection: `COPERNICUS/S2_SR_HARMONIZED`.
   - Searches last 90 days, filters scenes below 35% scene cloud cover, selects the least-cloudy scene.
   - Uses B8 (NIR), B4 (Red), and SCL.
   - NDVI formula: `(B8 - B4) / (B8 + B4)`.
   - Keeps SCL class 4 (vegetation) and 5 (bare soil); excludes cloud/shadow/water/snow/no-data.
   - Uses median NDVI over a 180 m buffer around the farm coordinate.

2. **Copernicus Data Space Statistical API**, only when both `COPERNICUS_CLIENT_ID` and `COPERNICUS_CLIENT_SECRET` are set.

3. **Microsoft Planetary Computer**, an anonymous STAC/SAS fallback. It finds a low-cloud Sentinel-2 L2A scene and reads B04, B08, and SCL data in a small coordinate buffer. It may be throttled.

4. **Deterministic academic phenology proxy** when no real provider gives a usable observation. It is clearly labelled `MODELLED_DEMO`; do not describe it as satellite NDVI.

- Real observations are cached in SQLite for 24 hours.
- In the dashboard, real mode is indicated by wording such as `Real Sentinel-2 ... NDVI statistics`, valid-pixel percentage, and a real provider name. Proxy mode is indicated by `Deterministic academic proxy`.

### Snapshot behavior

- A snapshot is not written repeatedly for identical meaningful state on the same date.
- A SHA-256 state hash excludes volatile fields such as `last_sync`.
- The history response also collapses legacy same-day duplicates without deleting database records.
- A new snapshot can be created on a new day even if the otherwise meaningful state is unchanged.

## 8. Local setup and run instructions

### Prerequisites

- Python available as `python` in PowerShell.
- Node.js/npm available.

### Install backend dependencies

```powershell
cd "D:\Agriculture - Copy"
python -m pip install -r requirements.txt
```

### Install frontend dependencies

```powershell
cd "D:\Agriculture - Copy\frontend"
npm install
```

### Start in two terminals

Terminal 1:

```powershell
cd "D:\Agriculture - Copy"
python backend/app.py
```

Terminal 2:

```powershell
cd "D:\Agriculture - Copy\frontend"
npm run dev
```

Open `http://localhost:5173` after Flask reports that it is running on port 5000.

### Single command option

```powershell
cd "D:\Agriculture - Copy"
python run.py
```

### Google Earth Engine setup for real NDVI

The user must create/register an eligible Google Earth Engine / Google Cloud project and authenticate their own account. Do not store or share credentials in source code.

```powershell
cd "D:\Agriculture - Copy"
python -m pip install earthengine-api
earthengine authenticate
$env:GOOGLE_EARTH_ENGINE_PROJECT="your_google_cloud_project_id"
python backend/app.py
```

If the `earthengine` command is not found after install, use:

```powershell
python -c "import ee; ee.Authenticate()"
```

The Google Cloud project must be registered for Earth Engine access. The app is configured to call `ee.Initialize(project=GOOGLE_EARTH_ENGINE_PROJECT)`.

## 9. Important current limitations and technical debt

1. **No farm boundary polygon:** NDVI uses a 180 m point buffer; it is not exact parcel-level NDVI.
2. **No automated scheduler:** Weather/NDVI synchronization happens when the digital-twin endpoint is called, not in the background daily.
3. **Soil is regional baseline:** It is not a dynamic, laboratory-confirmed field measurement.
4. **Vegetation fallback:** It is a deterministic proxy and must stay visibly labelled when real imagery is unavailable.
5. **Yield model constraints:** Uses small historic tabular data; its precomputed metrics/conformal margin should be treated as an academic prototype result.
6. **Price model constraints:** Has hard-coded seasonal/drift assumptions; it should not be presented as financial advice.
7. **Authentication is mock only:** `auth_routes.py` auto-authenticates demo users and returns mock tokens. It does not authorize endpoint access.
8. **CORS is open:** Suitable only for local academic development.
9. **Weather-adjustment caveat:** The live weather layer is a conservative, rule-based overlay on the historic Random Forest baseline; it is not retrained or statistically recalibrated on live weather. Its widened interval is an uncertainty communication aid, not a new 90% coverage guarantee.
10. **No GIS map:** Farm location is text/coordinates, not rendered as a parcel map.
11. **Build environment issue seen during development:** Vite occasionally failed to load Tailwind’s Windows native oxide module with an `EPERM`/encoding error. Earlier frontend production builds succeeded. This appears environment/dependency related, not application logic.

## 10. Recommended next improvements (in priority order)

### Priority A: strengthen current academic demonstration

1. Verify Google Earth Engine real NDVI on the running app and capture a screenshot showing provider, date, NDVI, and valid-pixel percentage.
2. Add an explicit `Last synchronized` / source-health display for weather and NDVI.
3. Add a small farm health/risk score combining latest NDVI, heat/rain risk, ET0, and yield uncertainty.
4. Create screenshots for dashboard, forecast, scenarios, explainability, chatbot, and cooperative view.
5. Keep `DIGITAL_TWIN_EVIDENCE.md` and report language aligned with actual data status.

### Priority B: improve digital-twin fidelity

1. Add daily synchronization while backend is running (APScheduler/background job) and retain one meaningful state per day.
2. When substantially more labelled harvest data is available, retrain and validate a model with farm-specific weather features rather than relying on the current bounded weather overlay.
3. Add farm polygon capture or GeoJSON upload and calculate NDVI only inside that polygon.
4. Store management events: irrigation, fertilizer, planting, pest observation, harvest outcome.
5. Validate forecasts against actual harvest outcomes.

### Priority C: production-grade work (not necessary for academic submission)

1. Real authentication/authorization and organization-level permissions.
2. Postgres/PostGIS migrations, queue workers, scheduled ingestion, monitoring, backups.
3. Model registry, reproducible training pipeline, richer test suite, audit trail.

## 11. Suggested viva/demo statement

> “This project is a sensor-free agricultural digital twin. Each registered farm has a persistent digital identity with coordinates, crop, season, sowing date, and area. The application fuses that identity with weather forecasts, soil baseline data, satellite-derived NDVI when available, historical yield and market data. It saves versioned twin states and uses the state for yield prediction with uncertainty, explainable AI, health alerts, and what-if scenario simulation. In the absence of a valid real satellite observation, the application transparently labels its vegetation indicator as an academic phenology proxy.”

## 12. Prompt for another AI assistant

Copy the following prompt together with this file:

```text
You are working on AgriTwin India, a local academic sensor-free agricultural digital-twin project. Read PROJECT_HANDOFF.md completely before proposing changes. Preserve the distinction between real observations and modelled/demo data. Do not make claims of real-time, parcel-level, or satellite-derived measurements unless the application provides evidence for them. Make changes carefully in the existing React/Vite frontend and Flask/Python backend, retain the SQLite persistence and fallback behavior, and test in proportion to the local environment. Focus on the highest-priority requested feature without replacing unrelated user work.
```
