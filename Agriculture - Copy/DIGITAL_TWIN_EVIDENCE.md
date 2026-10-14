# Academic Evidence: Farm Digital Twin

## What this project implements

**AgriTwin India** is a sensor-free, farm-specific academic digital twin. It maintains a persistent virtual state for each registered farm by combining its spatial and crop identity with weather, soil, vegetation/phenology, yield, market, and scenario layers.

It is a **digital twin**, rather than a one-time prediction dashboard, because the system has all four elements below:

| Digital-twin characteristic | Project implementation | Evidence |
| --- | --- | --- |
| Physical entity | Registered farm profile with location, area, crop, season, and sowing date | `twin_farms` SQLite table; `GET /api/farms` |
| Digital representation | Integrated farm state across weather, soil, vegetation, yield, price, and alerts | `GET /api/farms/<id>/digital-shadow` |
| Data connection | Farm-specific input data are assembled whenever the twin is synchronized | `DigitalTwinService.get_farm_digital_shadow()` |
| State history and feedback | Every synchronization persists a versioned state snapshot | `twin_snapshots`; `GET /api/farms/<id>/digital-shadow/history` |

## Architecture

```text
Registered Farm
(coordinates, crop, season, sowing date, area)
                    |
                    v
        Farm-specific Digital Twin Service
          /       |        |         \
         v        v        v          v
     Weather    Soil    Phenology   Yield + Market
     API/cache  baseline  proxy       models
          \       |        |         /
                    v
        Versioned Twin State Snapshot
                    |
                    v
 Dashboard • Scenario Simulation • XAI • Advisory
```

## Data transparency

| Layer | Status in this academic prototype |
| --- | --- |
| Farm identity | Persistent SQLite data entered through the Farm Management screen |
| Weather | Open-Meteo request when available; local CSV fallback |
| Soil | Local SoilGrids-derived Ariyalur baseline |
| Vegetation | Real cloud-masked Sentinel-2 SR Harmonized NDVI through Google Earth Engine when configured; anonymous Planetary Computer is the secondary provider; otherwise a deterministic phenology/NDVI proxy based on farm/crop/season/sowing date |
| Yield forecast | Random Forest prediction using supplied historical training data and conformal interval |
| Price forecast | Historical mandi-price-derived projection |

The project does not claim that modelled proxy data are real satellite observations. This explicit separation demonstrates responsible academic use of AI and public data.

## Live demonstration script

1. Start the backend and frontend, then open `http://localhost:5173`.
2. Select **Ariyalur Main Rice Farm** and note its crop, location, sowing date, forecast, and snapshot ID.
3. Select **Ariyalur South Cotton Block**. The dashboard now represents the second farm's own coordinates, Cotton crop, Rabi season, and sowing date.
4. Return to the first farm and use refresh. The **Twin State Timeline** receives another persisted snapshot.
5. Open **Farm Plots & Soil Profile** and register a small demonstration plot. It remains available after page refresh because it is stored in SQLite.
6. Open **What-If Scenario Simulator** and explain that it evaluates alternate future states against the farm's baseline twin state.
7. Open **SHAP Explainability** to show why a model output changed.

## Suggested viva answer

> “Our system is a sensor-free academic digital twin. It stores a farm's physical and crop identity, fuses multiple data layers into a virtual farm state, versions that state after each synchronization, and uses the state for forecasting, explainability, and what-if simulation. It is not merely a yield-prediction dashboard because farm state is persistent, farm-specific, time-versioned, and reusable across multiple decision modules.”

## Important limitations

- Real NDVI uses a point buffer around the farm coordinate. A future version should collect a farm-boundary polygon so statistics represent only the actual parcel.
- When no provider is configured or no usable scene exists, the vegetation layer remains an explicitly labelled deterministic academic proxy.
- Soil data are a regional baseline and should be supplemented by field soil tests.
- The system is designed for demonstration and research, not autonomous agronomic recommendations.
