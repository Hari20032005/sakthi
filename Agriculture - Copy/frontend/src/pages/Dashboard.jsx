import React, { useEffect, useState } from 'react';
import {
  CloudSun,
  Droplets,
  Thermometer,
  Wind,
  Layers,
  Activity,
  AlertTriangle,
  CheckCircle2,
  TrendingUp,
  MapPin,
  ExternalLink
} from 'lucide-react';
import { api } from '../api/client';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar
} from 'recharts';

export default function Dashboard({ digitalShadow, loading, activeFarm }) {
  const [snapshots, setSnapshots] = useState([]);
  const [completedRecommendationIds, setCompletedRecommendationIds] = useState([]);
  const [recommendationError, setRecommendationError] = useState('');

  useEffect(() => {
    if (!activeFarm?.farm_id) return;
    api.getTwinHistory(activeFarm.farm_id)
      .then((result) => setSnapshots(result.snapshots || []))
      .catch(() => setSnapshots([]));
  }, [activeFarm?.farm_id, digitalShadow?.twin_state?.snapshot_id]);

  if (loading || !digitalShadow) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="flex flex-col items-center space-y-3">
          <div className="w-10 h-10 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin"></div>
          <p className="text-slate-600 font-medium text-sm">Synthesizing Farm Digital Shadow...</p>
        </div>
      </div>
    );
  }

  const { farm_name, location, farm_specs, weather, soil, satellite_vegetation, current_yield_forecast, weather_adjusted_yield_forecast, active_alerts, twin_state } = digitalShadow;
  const weatherList = weather?.forecast || [];
  const ndviData = satellite_vegetation?.time_series || [];
  const recommendations = digitalShadow?.recommendations || [];

  const markRecommendationDone = async (recommendation) => {
    try {
      setRecommendationError('');
      await api.completeRecommendation(activeFarm.farm_id, recommendation);
      setCompletedRecommendationIds((ids) => [...ids, recommendation.id]);
    } catch (error) {
      setRecommendationError(error.message || 'Could not log this action.');
    }
  };

  return (
    <div className="space-y-6">
      
      {/* Top Banner: Digital Shadow Identity */}
      <div className="bg-gradient-to-r from-emerald-800 via-teal-900 to-slate-900 rounded-2xl p-6 text-white shadow-lg relative overflow-hidden">
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2 text-emerald-300 text-xs font-semibold uppercase tracking-wider mb-1">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>Versioned Farm Digital Twin State</span>
            </div>
            <h1 className="text-2xl font-bold text-white tracking-tight">{farm_name}</h1>
            <div className="flex flex-wrap items-center gap-4 text-xs text-emerald-200 mt-2">
              <span className="flex items-center gap-1">
                <MapPin className="w-3.5 h-3.5 text-emerald-400" />
                {location?.district}, {location?.state} ({location?.latitude}°N, {location?.longitude}°E)
              </span>
              <span>•</span>
              <span>Acreage: <strong>{farm_specs?.size_hectares} ha</strong> ({farm_specs?.size_acres} acres)</span>
              <span>•</span>
              <span>Active Crop: <strong>{farm_specs?.active_crop}</strong> ({farm_specs?.active_season})</span>
              <span>•</span>
              <span className="bg-emerald-700/80 px-2 py-0.5 rounded text-white font-medium border border-emerald-500/40">
                0 Physical Sensors
              </span>
            </div>
          </div>

          <div className="bg-white/10 backdrop-blur-md rounded-xl p-4 border border-white/15 text-right shrink-0">
            <div className="text-xs text-emerald-200">Weather-adjusted baseline</div>
            <div className="text-3xl font-extrabold text-white">
              {weather_adjusted_yield_forecast?.weather_adjusted_yield_t_per_ha ?? current_yield_forecast?.predicted_yield_t_per_ha} <span className="text-base font-normal text-emerald-200">t/ha</span>
            </div>
            <div className="text-[11px] text-emerald-300 mt-1">
              Range: {weather_adjusted_yield_forecast?.interval?.lower_bound ?? current_yield_forecast?.conformal_interval?.lower_bound} – {weather_adjusted_yield_forecast?.interval?.upper_bound ?? current_yield_forecast?.conformal_interval?.upper_bound} t/ha
            </div>
          </div>
        </div>
      </div>

      <div className="bg-sky-50 border border-sky-200 rounded-xl p-3.5 text-xs text-sky-900 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div><strong>Twin Snapshot #{twin_state?.snapshot_id}</strong> · State v{twin_state?.state_version} · {twin_state?.generated_at ? new Date(twin_state.generated_at).toLocaleString() : 'loading'} {!twin_state?.snapshot_created && <span className="text-sky-700">· unchanged state reused</span>}</div>
        <div className="text-sky-700">Farm inputs: {twin_state?.farm_inputs_used?.join(', ')}</div>
      </div>

      {weather_adjusted_yield_forecast && (
        <section className="bg-white rounded-2xl border border-sky-200 p-5 shadow-xs">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
            <div>
              <h2 className="font-bold text-slate-800 text-base">Weather-Adjusted Yield Baseline</h2>
              <p className="text-xs text-slate-500 mt-1">Season-to-date weather plus the next 7-day forecast is compared with the historic crop-season pattern.</p>
            </div>
            <span className="text-[11px] font-semibold bg-sky-50 text-sky-700 border border-sky-200 rounded-full px-2.5 py-1">{weather_adjusted_yield_forecast.weather_evidence?.source_status}</span>
          </div>
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div className="rounded-xl bg-slate-50 border border-slate-200 p-3"><span className="text-slate-500">Historic RF baseline</span><div className="mt-1 font-bold text-slate-900 text-lg">{weather_adjusted_yield_forecast.baseline_ml_yield_t_per_ha} <span className="text-xs font-normal">t/ha</span></div></div>
            <div className="rounded-xl bg-sky-50 border border-sky-200 p-3"><span className="text-sky-700">Weather adjustment</span><div className={`mt-1 font-bold text-lg ${weather_adjusted_yield_forecast.adjustment_pct < 0 ? 'text-amber-700' : 'text-emerald-700'}`}>{weather_adjusted_yield_forecast.adjustment_pct > 0 ? '+' : ''}{weather_adjusted_yield_forecast.adjustment_pct}%</div></div>
            <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-3"><span className="text-emerald-700">Adjusted baseline</span><div className="mt-1 font-bold text-emerald-900 text-lg">{weather_adjusted_yield_forecast.weather_adjusted_yield_t_per_ha} <span className="text-xs font-normal">t/ha</span></div></div>
          </div>
          <p className="mt-3 text-[11px] text-slate-500">Rain anomaly {weather_adjusted_yield_forecast.weather_evidence?.anomalies?.rainfall_pct}% · ET0 anomaly {weather_adjusted_yield_forecast.weather_evidence?.anomalies?.et0_pct}% · maximum-temperature anomaly {weather_adjusted_yield_forecast.weather_evidence?.anomalies?.avg_temp_max_c}°C. {weather_adjusted_yield_forecast.interval?.interpretation}</p>
          <p className="mt-2 text-[11px] text-amber-700">This is a weather-adjusted baseline, not a retrained model prediction. Verify crop condition in the field before acting.</p>
        </section>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
          <h2 className="font-bold text-slate-800 text-base">Twin State Timeline</h2>
          <p className="text-xs text-slate-500 mt-1">Persisted states make the virtual farm reproducible and auditable.</p>
          <div className="mt-4 space-y-2">
            {snapshots.slice(0, 4).map((snapshot, index) => (
              <div key={snapshot.snapshot_id} className="flex items-center justify-between text-xs border-l-2 border-emerald-400 pl-3 py-1.5">
                <div>
                  <span className="font-semibold text-slate-800">Snapshot #{snapshot.snapshot_id}</span>
                  <span className="ml-2 text-slate-500">State v{snapshot.state_version}</span>
                </div>
                <span className="text-slate-400">{new Date(snapshot.generated_at).toLocaleString()}</span>
              </div>
            ))}
            {snapshots.length === 0 && <p className="text-xs text-slate-400">Snapshot history will appear after the first synchronization.</p>}
          </div>
        </section>

        <section className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
          <h2 className="font-bold text-slate-800 text-base">Data Provenance & Limitations</h2>
          <p className="text-xs text-slate-500 mt-1">Every layer is labelled so results can be interpreted correctly.</p>
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg bg-emerald-50 border border-emerald-100 p-2.5"><strong className="text-emerald-800">Farm identity</strong><br /><span className="text-emerald-700">Persistent SQLite profile</span></div>
            <div className="rounded-lg bg-sky-50 border border-sky-100 p-2.5"><strong className="text-sky-800">Weather</strong><br /><span className="text-sky-700">Live API or local fallback</span></div>
            <div className="rounded-lg bg-amber-50 border border-amber-100 p-2.5"><strong className="text-amber-800">Soil</strong><br /><span className="text-amber-700">SoilGrids-derived baseline</span></div>
            <div className="rounded-lg bg-violet-50 border border-violet-100 p-2.5">
              <strong className="text-violet-800">Vegetation</strong><br />
              <span className="text-violet-700">
                {satellite_vegetation?.is_live_satellite_observation
                  ? `${satellite_vegetation.sensor_source} · real observation`
                  : 'Deterministic academic proxy'}
              </span>
            </div>
          </div>
        </section>
      </div>

      <section className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h2 className="font-bold text-slate-800 text-base">Recommended Actions</h2>
            <p className="text-xs text-slate-500 mt-1">Rule-based risk checks are ranked with scenario evidence where available. Verify conditions in the field before acting.</p>
          </div>
          <span className="text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full px-2.5 py-1">Twin decision layer</span>
        </div>
        {recommendationError && <p className="mt-3 text-xs text-rose-700">{recommendationError}</p>}
        <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-3">
          {recommendations.map((recommendation) => {
            const completed = completedRecommendationIds.includes(recommendation.id);
            const effect = recommendation.expected_effect;
            return (
              <article key={recommendation.id} className={`rounded-xl border p-4 ${recommendation.priority === 'HIGH' ? 'border-amber-200 bg-amber-50/50' : 'border-slate-200 bg-slate-50/70'}`}>
                <div className="flex items-center justify-between gap-3">
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${recommendation.priority === 'HIGH' ? 'bg-amber-200 text-amber-950' : 'bg-slate-200 text-slate-700'}`}>{recommendation.priority} PRIORITY</span>
                  {completed && <span className="text-[11px] font-semibold text-emerald-700">✓ Logged as done</span>}
                </div>
                <h3 className="mt-2 font-semibold text-sm text-slate-900">{recommendation.action}</h3>
                <p className="mt-1 text-xs text-slate-600 leading-relaxed"><strong>Why:</strong> {recommendation.reason}</p>
                {effect && <p className="mt-2 text-xs text-emerald-800"><strong>Scenario estimate:</strong> {effect.comparison}; {effect.yield_change_t_ha >= 0 ? '+' : ''}{effect.yield_change_t_ha} t/ha, ₹{effect.profit_change_inr.toLocaleString()} net-profit change.</p>}
                <p className="mt-2 text-[11px] text-slate-500"><strong>Confidence:</strong> {recommendation.confidence}</p>
                <button disabled={completed} onClick={() => markRecommendationDone(recommendation)} className="mt-3 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-300 px-3 py-1.5 rounded-lg transition-colors">
                  {completed ? 'Action logged' : 'Mark as done'}
                </button>
              </article>
            );
          })}
        </div>
      </section>

      {/* Active Alerts Banner */}
      {active_alerts && active_alerts.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {active_alerts.map((alert, idx) => (
            <div
              key={idx}
              className={`p-3.5 rounded-xl border flex items-start space-x-3 text-sm ${
                alert.severity === 'WARNING'
                  ? 'bg-amber-50 border-amber-200 text-amber-900'
                  : alert.severity === 'SUCCESS'
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
                  : 'bg-blue-50 border-blue-200 text-blue-900'
              }`}
            >
              {alert.severity === 'WARNING' ? (
                <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              ) : (
                <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
              )}
              <div>
                <div className="font-semibold text-xs uppercase tracking-wide">{alert.title}</div>
                <div className="text-xs mt-0.5 leading-relaxed">{alert.message}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Grid: 1. Live Weather Forecast & 2. Soil Health Card */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Weather Forecast (2 cols) */}
        <div className="lg:col-span-2 bg-white rounded-2xl p-5 border border-slate-200 shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <CloudSun className="w-5 h-5 text-amber-500" />
              <h2 className="font-bold text-slate-800 text-base">7-Day Meteorological Forecast</h2>
            </div>
            <span className="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded">
              Open-Meteo & NOAA GFS
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2">
            {weatherList.map((day, idx) => (
              <div
                key={idx}
                className="bg-slate-50 border border-slate-100 rounded-xl p-3 text-center flex flex-col justify-between hover:border-emerald-300 transition-colors"
              >
                <div className="text-xs font-semibold text-slate-600">
                  {new Date(day.date).toLocaleDateString('en-US', { weekday: 'short' })}
                </div>
                <div className="my-2">
                  <div className="text-base font-bold text-slate-900">{day.temp_max}°</div>
                  <div className="text-[11px] text-slate-400">{day.temp_min}°</div>
                </div>
                <div className="pt-2 border-t border-slate-200/60 flex items-center justify-center space-x-1 text-[11px] text-blue-600 font-medium">
                  <Droplets className="w-3 h-3" />
                  <span>{day.rainfall_mm}mm</span>
                </div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-3 gap-4 pt-2 border-t border-slate-100 text-xs text-slate-600">
            <div className="flex items-center space-x-2">
              <Thermometer className="w-4 h-4 text-rose-500" />
              <span>Day Max Average: <strong>{weatherList[0]?.temp_max}°C</strong></span>
            </div>
            <div className="flex items-center space-x-2">
              <Droplets className="w-4 h-4 text-blue-500" />
              <span>Expected Rain (7d): <strong>{weatherList.reduce((acc, d) => acc + (d.rainfall_mm || 0), 0).toFixed(1)} mm</strong></span>
            </div>
            <div className="flex items-center space-x-2">
              <Wind className="w-4 h-4 text-teal-500" />
              <span>Evapotranspiration ET0: <strong>~4.8 mm/day</strong></span>
            </div>
          </div>
        </div>

        {/* Soil Health Profile (1 col) */}
        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Layers className="w-5 h-5 text-amber-700" />
              <h2 className="font-bold text-slate-800 text-base">ISRIC Soil Profile</h2>
            </div>
            <span className="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded">250m Map</span>
          </div>

          <div className="bg-amber-50/60 border border-amber-200/50 rounded-xl p-3.5 text-xs text-amber-900">
            <div className="font-semibold text-sm text-amber-950">{soil?.texture_class} Soil</div>
            <p className="mt-1 text-[11px] text-amber-800 leading-relaxed">
              {soil?.water_retention_capacity}
            </p>
          </div>

          <div className="space-y-2.5 text-xs">
            <div className="flex justify-between items-center py-1 border-b border-slate-100">
              <span className="text-slate-500">Soil pH (H₂O)</span>
              <span className="font-semibold text-slate-800">{soil?.ph?.value} ({soil?.ph?.classification})</span>
            </div>
            <div className="flex justify-between items-center py-1 border-b border-slate-100">
              <span className="text-slate-500">Clay Fraction</span>
              <span className="font-semibold text-slate-800">{soil?.texture?.clay_pct}%</span>
            </div>
            <div className="flex justify-between items-center py-1 border-b border-slate-100">
              <span className="text-slate-500">Sand / Silt</span>
              <span className="font-semibold text-slate-800">{soil?.texture?.sand_pct}% / {soil?.texture?.silt_pct}%</span>
            </div>
            <div className="flex justify-between items-center py-1 border-b border-slate-100">
              <span className="text-slate-500">Organic Carbon (SOC)</span>
              <span className="font-semibold text-slate-800">{soil?.organic_carbon_g_kg} g/kg</span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-slate-500">Cation Exchange (CEC)</span>
              <span className="font-semibold text-slate-800">{soil?.cation_exchange_capacity} cmol/kg</span>
            </div>
          </div>
        </div>

      </div>

      {/* Satellite Vegetation Index (NDVI) & Phenology Progression */}
      <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <div className="flex items-center space-x-2">
              <Activity className="w-5 h-5 text-emerald-600" />
              <h2 className="font-bold text-slate-800 text-base">Vegetation State (NDVI)</h2>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              {satellite_vegetation?.is_live_satellite_observation
                ? 'Real Sentinel-2 L2A NDVI statistics for the farm point buffer. Cloud/no-data pixels are excluded.'
                : 'Deterministic academic phenology proxy derived from the registered crop and sowing date; not a live satellite observation.'}
            </p>
          </div>
          <div className="flex items-center space-x-2">
            <span className="text-xs font-semibold bg-emerald-100 text-emerald-800 px-2.5 py-1 rounded-full border border-emerald-300">
              Current NDVI: {satellite_vegetation?.current_ndvi} ({satellite_vegetation?.canopy_vigor})
            </span>
          </div>
        </div>

        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={ndviData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="ndviGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="phenology_stage" tick={{ fontSize: 11, fill: '#64748b' }} />
              <YAxis domain={[0, 1]} tick={{ fontSize: 11, fill: '#64748b' }} />
              <Tooltip
                content={({ active, payload }) => {
                  if (active && payload && payload.length) {
                    const d = payload[0].payload;
                    return (
                      <div className="bg-slate-900 text-white p-2.5 rounded-lg text-xs shadow-lg space-y-1">
                        <div className="font-bold text-emerald-400">{d.phenology_stage}</div>
                        <div>Date: {d.date}</div>
                        <div>NDVI Index: <strong>{d.ndvi}</strong></div>
                        {d.evi !== null && <div>Enhanced Veg Index (EVI): <strong>{d.evi}</strong></div>}
                        {d.valid_pixel_pct !== undefined && <div>Valid pixels: <strong>{d.valid_pixel_pct}%</strong></div>}
                        <div className="text-emerald-300 font-medium">Status: {d.health_status}</div>
                      </div>
                    );
                  }
                  return null;
                }}
              />
              <Area type="monotone" dataKey="ndvi" stroke="#059669" strokeWidth={2.5} fillOpacity={1} fill="url(#ndviGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

    </div>
  );
}
