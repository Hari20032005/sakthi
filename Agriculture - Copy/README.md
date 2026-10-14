# 🌾 Software-Based Agriculture Digital Twin (Sensor-Free)

> An end-to-end digital twin system for smallholder farmers and agricultural cooperatives that eliminates hardware and IoT costs by using freely available public datasets — **weather forecasts, SoilGrids soil maps, satellite vegetation indices (Sentinel-2 NDVI), historical yield records, and Agmarknet mandi market prices**.

## Academic Prototype Disclosure

This project implements a **farm-specific, sensor-free academic digital twin**. A twin state is produced from each registered farm's location, crop, season, sowing date and area; it is persisted as a versioned SQLite snapshot so it can be inspected and compared over time.

Data status is intentionally explicit:

- Weather is retrieved from Open-Meteo when available, with a local cached-data fallback.
- Soil values are a local SoilGrids-derived baseline used for this Ariyalur demonstration.
- Yield and price outputs are model-driven estimates based on the included historical datasets.
- The headline yield can include a clearly-labelled **weather-adjusted baseline**: season-to-date rainfall, ET0, maximum temperature and heat days are compared with the historic crop-season pattern, then a conservative bounded overlay is applied to the historic Random Forest estimate. It is not a retrained live-weather ML prediction, and its displayed range is widened accordingly.
- The vegetation chart is a deterministic **phenology/NDVI proxy** until a live Sentinel-2 data connector is configured. It must not be interpreted as a live satellite observation.

### Real Sentinel-2 NDVI

The preferred academic workflow is Google Earth Engine. Install dependencies with `pip install -r requirements.txt`, authenticate locally using `earthengine authenticate`, and set `GOOGLE_EARTH_ENGINE_PROJECT` to your registered noncommercial Google Cloud project. The application then uses cloud-masked Sentinel-2 SR Harmonized imagery to calculate and persist a median NDVI observation for each farm coordinate buffer.

If Google Earth Engine is not configured, the project falls back to anonymous Microsoft Planetary Computer access to obtain a low-cloud Sentinel-2 L2A scene. This requires no account, though anonymous service access can be throttled. Until a farm boundary is captured, both providers use a small buffer around the registered farm coordinate.

An optional Copernicus Data Space connector remains available for a later upgrade: set `COPERNICUS_CLIENT_ID` and `COPERNICUS_CLIENT_SECRET` as environment variables (template: `.env.example`).

This distinction is important for academic integrity: the application demonstrates the digital-twin workflow (farm identity → data fusion → versioned state → prediction and scenarios) without representing synthetic demonstration data as real-time telemetry.

### Recommendation layer

The dashboard includes a transparent recommendation layer: configured academic risk rules inspect the current twin state, and relevant recommendations use the existing scenario engine to estimate an action's yield/profit difference from baseline. Each recommendation exposes its trigger, confidence, data sources, and field-verification requirement. Completing a recommendation logs a management event into the next twin state. The thresholds are academic-prototype defaults and require TNAU/ICAR validation before field deployment.

For a concise evaluator-facing explanation, architecture, limitations, and live demonstration sequence, see [DIGITAL_TWIN_EVIDENCE.md](DIGITAL_TWIN_EVIDENCE.md).

---

## 🎯 Key Capabilities & Architecture

1. **Sensor-Free Farm Digital Shadow**:
   - Synthesizes an updated virtual representation of any farm plot using GPS coordinates.
   - Dynamic 7-day meteorological forecast from Open-Meteo / NOAA GFS.
   - 250m global soil texture, pH, cation exchange capacity (CEC), and organic carbon from ISRIC SoilGrids.
   - 10m Sentinel-2 satellite vegetation index (NDVI & EVI) tracking crop canopy vigor and vegetative stages.
2. **Machine Learning Yield Forecasting with Calibrated Uncertainty**:
   - Random Forest & Gradient Boosting models evaluated via Leave-One-Out Cross-Validation (LOOCV).
   - **Conformal Prediction**: Guarantees finite-sample coverage (90% target coverage) rather than relying on uncalibrated point estimates.
   - **Live-weather consistency layer**: uses Open-Meteo season-to-date history plus the seven-day forecast where available; a transparent -12% to +5% bounded overlay keeps the twin's yield baseline aligned with the weather state without overstating the small training dataset.
   - Deep Learning (PyTorch MLP/LSTM + Monte Carlo Dropout) comparative benchmarks.
3. **Commodity Market Price Forecaster**:
   - Time-series forecasting trained on historical Agmarknet mandi arrivals for Ariyalur / Tamil Nadu (Rice/Paddy and Cotton).
   - Projects 1-to-6-month price trends with 90% confidence bands to guide harvesting and selling timing.
4. **"What-If" Scenario Simulation Engine**:
   - Allows farmers to simulate decisions *before* risking money in the field:
     - Monsoon drought shock (-35% rainfall deficit)
     - Supplemental micro-irrigation (+25% water supply)
     - Sowing date delays (+3 weeks heat exposure)
     - Crop switching (Rice vs Cotton)
     - Custom farmer sliders for rainfall and temperature anomalies
   - Compares expected yield, production tonnage, gross mandi revenue, input costs, and net profit side-by-side.
5. **Explainable AI (SHAP Feature Attribution)**:
   - Uses `shap.TreeExplainer` to identify the exact positive and negative drivers of each forecast.
   - Translates mathematical attributions into plain-language agronomic takeaways.
6. **Retrieval-Augmented Generation (RAG) Advisory Chatbot**:
   - Zero-hallucination conversational advisory grounded directly in the farm's active digital shadow, SHAP outputs, and Tamil Nadu Agricultural University (TNAU) agronomic guidelines.
   - Runs 100% offline out-of-the-box, with optional plug-and-play Google Gemini API support.
7. **Modern Web Dashboard**:
   - Responsive React + Vite + Tailwind CSS interface with interactive charts, maps, comparison sliders, and role-based access for **Farmers** and **Cooperative Admins**.

---

## 🚀 How to Run the Project

### Option 1: Single-Command Launch (Recommended)

In your terminal from the project folder:
```powershell
python run.py
```
*(Or simply double-click `run_all.bat` on Windows)*

This command automatically:
1. Starts the **Backend Flask REST API** at `http://localhost:5000`
2. Starts the **Frontend React Dashboard** at `http://localhost:5173`

Once running, open your web browser at:
👉 **[http://localhost:5173](http://localhost:5173)**

---

### Option 2: Running Backend and Frontend in Separate Terminals

#### Terminal 1 — Backend (Flask API):
```powershell
python backend/app.py
```
*(Runs on `http://localhost:5000`)*

#### Terminal 2 — Frontend (React + Vite):
```powershell
cd frontend
npm run dev
```
*(Runs on `http://localhost:5173`)*

---

## 🧪 Testing & Verification

To verify that all machine learning models, database connections, and API endpoints are working properly:
```powershell
python test_backend.py
```
This script runs automated integration tests across all API endpoints:
- `/api/health`
- `/api/farms/1/digital-shadow`
- `/api/forecast/yield`
- `/api/forecast/price`
- `/api/scenarios/simulate`
- `/api/explain/prediction`
- `/api/chat/message`

---

## 📁 Project Directory Structure

```
Agriculture/
├── backend/
│   ├── app.py                      # Flask REST API entrypoint & CORS setup
│   ├── config.py                   # Configuration settings (DB, paths, ports)
│   ├── db.py                       # PostgreSQL/PostGIS connection manager with fallback
│   ├── models/
│   │   ├── yield_model.py          # Yield Forecaster (RF, GB, Conformal Uncertainty)
│   │   ├── price_model.py          # Mandi Price Forecaster with confidence bands
│   │   ├── deep_model.py           # PyTorch LSTM / Transformer model benchmark
│   │   ├── shap_engine.py          # SHAP TreeExplainer feature attribution generator
│   │   └── scenario_engine.py      # Scenario simulation engine (what-if decision simulator)
│   ├── services/
│   │   ├── farm_repository.py      # Persistent SQLite farm profiles and twin snapshots
│   │   ├── digital_twin.py         # Digital shadow synthesizer (weather, soil, satellite, yield)
│   │   ├── weather_service.py      # Open-Meteo live forecast & historical collector
│   │   ├── soil_service.py         # SoilGrids 250m profile provider
│   │   ├── satellite_service.py    # Satellite NDVI/EVI vegetation time series
│   │   └── rag_chatbot.py          # RAG Chatbot grounded in digital twin state & agronomy
│   └── routes/
│       ├── auth_routes.py          # User authentication (Farmer & Cooperative Admin)
│       ├── farm_routes.py          # Farm profile & digital shadow API
│       ├── forecast_routes.py      # Yield & price forecasting endpoints
│       ├── scenario_routes.py      # What-if scenario simulation endpoints
│       ├── explain_routes.py       # SHAP explanation & feature importance endpoints
│       ├── chat_routes.py          # RAG chatbot conversation endpoints
│       └── cooperative_routes.py   # Cooperative multi-farm aggregated analytics
├── frontend/                       # Modern React + Vite + Tailwind CSS dashboard
│   ├── src/
│   │   ├── api/client.js           # API client connecting to Flask backend
│   │   ├── components/             # Reusable UI components (Navbar, Sidebar, etc.)
│   │   └── pages/
│   │       ├── Dashboard.jsx       # Farm Digital Shadow overview & telemetry
│   │       ├── YieldForecast.jsx   # Yield prediction with conformal confidence bounds
│   │       ├── PriceForecast.jsx   # Mandi price projection & optimal selling timing
│   │       ├── ScenarioSim.jsx     # Interactive What-If Scenario Simulator
│   │       ├── Explainability.jsx  # SHAP waterfall & impact factor breakdown
│   │       ├── Chatbot.jsx         # RAG Advisory AI Chatbot with prompt starters
│   │       ├── FarmManagement.jsx  # Farm profile management with map coordinates
│   │       └── CooperativeView.jsx # Cooperative admin multi-farm analytics & risk alerts
├── data/                           # Verified datasets (weather, soil, prices, APY yield)
├── test_backend.py                 # Automated backend test suite
├── run.py                          # Cross-platform single-command runner
├── run_all.bat                     # Windows batch launcher
├── start_backend.bat               # Backend launcher batch file
├── start_frontend.bat              # Frontend launcher batch file
├── requirements.txt                # Python backend dependencies
└── README.md                       # Complete documentation
```

---

## 🌐 API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/health` | GET | System health & public data source verification |
| `/api/farms` | GET, POST | List all farm profiles or register a new plot |
| `/api/farms/<id>/digital-shadow` | GET | Complete multi-modal digital shadow for a farm |
| `/api/farms/<id>/digital-shadow/history` | GET | Versioned snapshot history for a farm's twin state |
| `/api/forecast/yield` | POST | Predicted yield with 90% conformal confidence interval |
| `/api/forecast/price` | GET | Future 1–6 month commodity price projection |
| `/api/forecast/benchmark` | GET | LOOCV metrics (MAE, MAPE, R²) comparing RF, GB, Deep Learning |
| `/api/scenarios/simulate` | POST | Comparative What-If scenario simulations with financial returns |
| `/api/explain/global` | GET | District-wide SHAP feature importance rankings |
| `/api/explain/prediction` | POST | Exact per-prediction SHAP factor attributions |
| `/api/chat/message` | POST | Send question to Grounded Agronomy RAG chatbot |
| `/api/cooperative/summary` | GET | Cooperative federation aggregate acreage & harvest production |
