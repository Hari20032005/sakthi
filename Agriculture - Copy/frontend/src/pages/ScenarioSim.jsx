import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import {
  Sliders,
  CheckCircle,
  AlertTriangle,
  ArrowRight,
  DollarSign,
  Sprout,
  BarChart2,
  TrendingUp,
  TrendingDown,
  CloudRain,
  Thermometer,
  Zap
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts';

export default function ScenarioSim() {
  const [crop, setCrop] = useState('Rice');
  const [season, setSeason] = useState('Kharif');
  const [areaHa, setAreaHa] = useState(3.0);

  // Custom slider adjustments
  const [rainPct, setRainPct] = useState(0); // -50% to +50%
  const [tempShift, setTempShift] = useState(0); // -2°C to +5°C

  const [simData, setSimData] = useState(null);
  const [customResult, setCustomResult] = useState(null);
  const [lastCustomParams, setLastCustomParams] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Load baseline + predefined scenarios A/B/C/D on mount or when crop/season/area changes
  const loadBaselineScenarios = async () => {
    try {
      setError(null);
      const res = await api.simulateScenarios(crop, season, areaHa, null);
      if (res.success && res.simulation) {
        setSimData(res.simulation);
        // If an active custom scenario belongs to a different crop, reset it
        if (customResult && customResult.crop !== crop) {
          setCustomResult(null);
          setLastCustomParams(null);
        }
      }
    } catch (err) {
      console.error('Failed to load baseline scenarios:', err);
      setError(err.message || 'Failed to connect to simulation engine.');
    }
  };

  useEffect(() => {
    loadBaselineScenarios();
  }, [crop, season, areaHa]);

  // Execute user-defined custom scenario
  const handleRunCustomSimulation = async () => {
    // Step 11: Input validation
    const parsedArea = parseFloat(areaHa);
    if (isNaN(parsedArea) || parsedArea <= 0) {
      setError('Farm area must be greater than 0 hectares.');
      return;
    }
    if (rainPct < -50 || rainPct > 50) {
      setError('Rainfall anomaly must be between -50% and +50%.');
      return;
    }
    if (tempShift < -2 || tempShift > 5) {
      setError('Temperature anomaly must be between -2°C and +5°C.');
      return;
    }

    setError(null);
    setLoading(true);

    try {
      const customPayload = {
        crop,
        season,
        area_ha: parsedArea,
        rainfall_anomaly: rainPct,
        temperature_anomaly: tempShift
      };

      const res = await api.simulateScenarios(crop, season, parsedArea, customPayload);

      if (res.success && res.simulation) {
        setSimData(res.simulation);
        const customScenario =
          res.simulation.custom_scenario ||
          res.simulation.scenarios.find((s) => s.label.toLowerCase().includes('custom'));

        if (customScenario) {
          setCustomResult(customScenario);
          setLastCustomParams({
            crop,
            season,
            areaHa: parsedArea,
            rainPct,
            tempShift
          });
        }
      } else {
        setError(res.error || 'Custom simulation failed.');
      }
    } catch (err) {
      console.error('Custom simulation error:', err);
      setError(err.message || 'Custom simulation failed. Please check the simulation service.');
    } finally {
      setLoading(false);
    }
  };

  const scenarios = simData?.scenarios || [];

  // Chart data for comparing net profits & yields (Step 8: Baseline, Scenario A, B, C, D, Custom Scenario)
  const chartData = scenarios.map((s) => {
    let name = s.label.split(':')[0].replace('(Normal Historical Conditions)', 'Baseline').trim();
    if (s.label.toLowerCase().includes('custom') || name.toLowerCase().includes('custom')) {
      name = 'Custom Scenario';
    }
    return {
      name,
      yield: s.predicted_yield_t_ha,
      profit: Math.round(s.financial_estimates.net_profit_inr / 1000), // in Thousands
    };
  });

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <Sliders className="w-6 h-6 text-emerald-600" />
            "What-If" Scenario Simulation Engine
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Simulate alternative crop, irrigation, and climate choices{' '}
            <strong>before risking resources in the physical field</strong>.
          </p>
        </div>

        {/* Global Controls */}
        <div className="flex items-center space-x-3 bg-white p-2 rounded-xl border border-slate-200 shadow-xs">
          <select
            value={crop}
            onChange={(e) => setCrop(e.target.value)}
            className="px-3 py-1.5 text-xs font-semibold bg-slate-50 border border-slate-200 rounded-lg text-slate-800 focus:outline-none"
          >
            <option value="Rice">Rice (Paddy)</option>
            <option value="Cotton(lint)">Cotton</option>
          </select>
          <div className="flex items-center space-x-1.5 text-xs font-medium text-slate-600">
            <span>Area:</span>
            <input
              type="number"
              step="0.5"
              min="0.5"
              max="50"
              value={areaHa}
              onChange={(e) => setAreaHa(parseFloat(e.target.value) || 0)}
              className="w-16 px-2 py-1 text-xs border border-slate-200 rounded text-center font-bold"
            />
            <span>ha</span>
          </div>
        </div>
      </div>

      {/* Error Alert Banner */}
      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-700 text-xs px-4 py-3 rounded-xl flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-500 shrink-0" />
            <span className="font-medium">{error}</span>
          </div>
          <button
            onClick={() => setError(null)}
            className="text-rose-500 hover:text-rose-700 text-xs font-bold underline cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Interactive Custom Scenario Tweaker */}
      <div className="bg-slate-900 text-white rounded-2xl p-5 shadow-md space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
          <div>
            <h3 className="font-bold text-sm text-white flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
              Live What-If Stress Testing Controls
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Adjust rainfall or temperature anomalies below to test hypothetical climate shocks.
            </p>
          </div>
          <button
            onClick={handleRunCustomSimulation}
            disabled={loading}
            className={`text-xs font-bold px-4 py-2 rounded-xl transition-all shadow-sm shrink-0 flex items-center gap-2 ${
              loading
                ? 'bg-slate-700 text-slate-400 cursor-not-allowed'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white cursor-pointer active:scale-95'
            }`}
          >
            {loading ? (
              <>
                <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin"></span>
                <span>Running custom simulation...</span>
              </>
            ) : (
              <span>Run Custom Simulation</span>
            )}
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-1">
          {/* Rainfall Slider */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="text-slate-300 font-medium flex items-center gap-1.5">
                <CloudRain className="w-3.5 h-3.5 text-blue-400" />
                Monsoon Rainfall Anomaly
              </span>
              <span
                className={`font-bold ${
                  rainPct < 0 ? 'text-amber-400' : rainPct > 0 ? 'text-blue-400' : 'text-slate-400'
                }`}
              >
                {rainPct > 0 ? `+${rainPct}%` : `${rainPct}%`}{' '}
                {rainPct < 0 ? '(Drought Deficit)' : rainPct > 0 ? '(Surplus Rain)' : '(Normal)'}
              </span>
            </div>
            <input
              type="range"
              min="-50"
              max="50"
              step="5"
              value={rainPct}
              onChange={(e) => setRainPct(parseInt(e.target.value))}
              className="w-full accent-emerald-500 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-slate-500">
              <span>-50% Extreme Drought</span>
              <span>0% Normal</span>
              <span>+50% High Monsoon</span>
            </div>
          </div>

          {/* Temperature Slider */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="text-slate-300 font-medium flex items-center gap-1.5">
                <Thermometer className="w-3.5 h-3.5 text-rose-400" />
                Temperature Anomaly (°C)
              </span>
              <span
                className={`font-bold ${
                  tempShift > 0 ? 'text-rose-400' : tempShift < 0 ? 'text-cyan-400' : 'text-slate-400'
                }`}
              >
                {tempShift > 0 ? `+${tempShift}°C` : `${tempShift}°C`}{' '}
                {tempShift > 1 ? '(Heat Stress)' : '(Seasonal Baseline)'}
              </span>
            </div>
            <input
              type="range"
              min="-2"
              max="5"
              step="0.5"
              value={tempShift}
              onChange={(e) => setTempShift(parseFloat(e.target.value))}
              className="w-full accent-rose-500 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-slate-500">
              <span>-2°C Cool</span>
              <span>0°C Normal</span>
              <span>+5°C Severe Heatwave</span>
            </div>
          </div>
        </div>
      </div>

      {/* STEP 7: Dedicated CUSTOM FARMER WHAT-IF SCENARIO Result Section */}
      {customResult && lastCustomParams && (
        <div className="bg-gradient-to-br from-slate-900 via-slate-800 to-emerald-950 text-white rounded-2xl p-6 shadow-lg border border-emerald-500/30 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-700/60 pb-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="bg-emerald-500 text-slate-950 text-[10px] font-black tracking-widest uppercase px-2.5 py-0.5 rounded-full">
                  CUSTOM FARMER WHAT-IF SCENARIO
                </span>
                <span className="text-xs text-slate-300 font-semibold">
                  {lastCustomParams.crop} • {lastCustomParams.areaHa} ha
                </span>
              </div>
              <h3 className="font-bold text-base text-white mt-1">
                Hypothetical Anomaly Response Analysis
              </h3>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs bg-slate-800 border border-slate-700 px-3 py-1 rounded-lg text-slate-300 font-medium">
                Rainfall Anomaly:{' '}
                <strong
                  className={
                    lastCustomParams.rainPct < 0
                      ? 'text-amber-400'
                      : lastCustomParams.rainPct > 0
                      ? 'text-blue-400'
                      : 'text-slate-300'
                  }
                >
                  {lastCustomParams.rainPct > 0 ? `+${lastCustomParams.rainPct}%` : `${lastCustomParams.rainPct}%`}
                </strong>
              </span>
              <span className="text-xs bg-slate-800 border border-slate-700 px-3 py-1 rounded-lg text-slate-300 font-medium">
                Temperature Anomaly:{' '}
                <strong
                  className={
                    lastCustomParams.tempShift > 0
                      ? 'text-rose-400'
                      : lastCustomParams.tempShift < 0
                      ? 'text-cyan-400'
                      : 'text-slate-300'
                  }
                >
                  {lastCustomParams.tempShift > 0 ? `+${lastCustomParams.tempShift}°C` : `${lastCustomParams.tempShift}°C`}
                </strong>
              </span>
            </div>
          </div>

          {/* 4 Metric Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* 1. Predicted Yield */}
            <div className="bg-slate-800/80 backdrop-blur-sm p-4 rounded-xl border border-slate-700/60">
              <div className="text-[11px] text-slate-400 font-medium flex items-center justify-between">
                <span>Predicted Yield</span>
                <Sprout className="w-3.5 h-3.5 text-emerald-400" />
              </div>
              <div className="text-2xl font-black text-white mt-1">
                {customResult.predicted_yield_t_ha}{' '}
                <span className="text-xs font-normal text-slate-300">t/ha</span>
              </div>
              <div className="text-[11px] text-slate-400 mt-1">
                Range: {customResult.confidence_interval.lower} – {customResult.confidence_interval.upper} t/ha
              </div>
            </div>

            {/* 2. Total Production */}
            <div className="bg-slate-800/80 backdrop-blur-sm p-4 rounded-xl border border-slate-700/60">
              <div className="text-[11px] text-slate-400 font-medium flex items-center justify-between">
                <span>Total Production</span>
                <BarChart2 className="w-3.5 h-3.5 text-blue-400" />
              </div>
              <div className="text-2xl font-black text-white mt-1">
                {customResult.expected_production_tonnes.expected}{' '}
                <span className="text-xs font-normal text-slate-300">tonnes</span>
              </div>
              <div className="text-[11px] text-slate-400 mt-1">
                Bounds: {customResult.expected_production_tonnes.lower} – {customResult.expected_production_tonnes.upper} t
              </div>
            </div>

            {/* 3. Estimated Economic Outcome */}
            <div className="bg-slate-800/80 backdrop-blur-sm p-4 rounded-xl border border-slate-700/60">
              <div className="text-[11px] text-slate-400 font-medium flex items-center justify-between">
                <span>Estimated Economic Outcome</span>
                <DollarSign className="w-3.5 h-3.5 text-emerald-400" />
              </div>
              <div
                className={`text-2xl font-black mt-1 ${
                  customResult.financial_estimates.net_profit_inr >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                ₹{customResult.financial_estimates.net_profit_inr.toLocaleString()}
              </div>
              <div className="text-[11px] text-slate-400 mt-1">
                Net Profit (Revenue: ₹{Math.round(customResult.financial_estimates.gross_revenue_inr).toLocaleString()})
              </div>
            </div>

            {/* 4. Difference from Baseline */}
            <div className="bg-slate-800/80 backdrop-blur-sm p-4 rounded-xl border border-slate-700/60">
              <div className="text-[11px] text-slate-400 font-medium flex items-center justify-between">
                <span>Difference from Baseline</span>
                {customResult.difference_from_baseline?.yield_diff_t_ha >= 0 ? (
                  <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
                ) : (
                  <TrendingDown className="w-3.5 h-3.5 text-rose-400" />
                )}
              </div>
              <div
                className={`text-2xl font-black mt-1 flex items-baseline gap-1.5 ${
                  (customResult.difference_from_baseline?.yield_change_pct || 0) >= 0
                    ? 'text-emerald-400'
                    : 'text-rose-400'
                }`}
              >
                <span>
                  {customResult.difference_from_baseline?.yield_change_pct > 0 ? '+' : ''}
                  {customResult.difference_from_baseline?.yield_change_pct || 0}%
                </span>
                <span className="text-xs font-normal text-slate-300">
                  ({customResult.difference_from_baseline?.yield_diff_t_ha > 0 ? '+' : ''}
                  {customResult.difference_from_baseline?.yield_diff_t_ha || 0} t/ha)
                </span>
              </div>
              <div className="text-[11px] text-slate-400 mt-1">
                Profit Impact:{' '}
                <strong
                  className={
                    (customResult.difference_from_baseline?.profit_diff_inr || 0) >= 0
                      ? 'text-emerald-400'
                      : 'text-rose-400'
                  }
                >
                  {customResult.difference_from_baseline?.profit_diff_inr > 0 ? '+' : ''}₹
                  {(customResult.difference_from_baseline?.profit_diff_inr || 0).toLocaleString()}
                </strong>
              </div>
            </div>
          </div>

          {/* Explanation Footer */}
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-3 pt-2 text-xs text-slate-300 bg-slate-800/40 p-3 rounded-xl border border-slate-700/40">
            <p className="leading-relaxed flex-1">
              <strong className="text-white">Agronomic Assessment:</strong> {customResult.explanation_text}
            </p>
            <span
              className={`px-3 py-1 rounded-full text-xs font-bold shrink-0 ${
                customResult.risk_assessment.includes('High')
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                  : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
              }`}
            >
              {customResult.risk_assessment}
            </span>
          </div>
        </div>
      )}

      {/* Comparison Chart: Yield & Net Returns */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <h3 className="font-bold text-slate-900 text-base">
            Comparative Yield & Net Farm Income (₹ in Thousands)
          </h3>
          <span className="text-xs text-slate-500">
            Includes Baseline, Scenarios A–D{customResult ? ' + Custom Scenario' : ''}
          </span>
        </div>
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 10, right: 30, left: 10, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis
                dataKey="name"
                tick={{ fontSize: 11, fill: '#64748b' }}
                interval={0}
                angle={-10}
                textAnchor="end"
              />
              <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#64748b' }} unit=" t/ha" />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: '#64748b' }} unit="k ₹" />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 12, paddingTop: 10 }} />
              <Bar yAxisId="left" dataKey="yield" fill="#10b981" name="Yield (t/ha)" radius={[4, 4, 0, 0]} />
              <Bar yAxisId="right" dataKey="profit" fill="#3b82f6" name="Net Profit (₹ '000s)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Comparative Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {scenarios.map((s, idx) => {
          const isBaseline = idx === 0;
          const isCustom = s.label.toLowerCase().includes('custom');
          const isDrought = s.label.includes('Drought');
          const isIrrigation = s.label.includes('Irrigation');
          const netProfit = s.financial_estimates.net_profit_inr;

          return (
            <div
              key={idx}
              className={`rounded-2xl p-5 border flex flex-col justify-between transition-all ${
                isCustom
                  ? 'bg-slate-900 text-white border-emerald-500 shadow-md ring-2 ring-emerald-500/20'
                  : isBaseline
                  ? 'bg-emerald-50/50 border-emerald-300 ring-2 ring-emerald-500/20'
                  : isDrought
                  ? 'bg-amber-50/40 border-amber-200'
                  : 'bg-white border-slate-200 shadow-xs'
              }`}
            >
              <div>
                <div className="flex items-center justify-between">
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${
                      isCustom
                        ? 'bg-emerald-400 text-slate-950 font-black'
                        : isBaseline
                        ? 'bg-emerald-600 text-white'
                        : isDrought
                        ? 'bg-amber-600 text-white'
                        : 'bg-slate-200 text-slate-700'
                    }`}
                  >
                    {isCustom ? 'Custom Scenario' : isBaseline ? 'Current Baseline' : s.label.split(':')[0]}
                  </span>
                  <span
                    className={`text-xs font-semibold ${
                      isCustom
                        ? 'text-emerald-400'
                        : s.risk_assessment.includes('High')
                        ? 'text-amber-600'
                        : 'text-emerald-600'
                    }`}
                  >
                    {s.risk_assessment}
                  </span>
                </div>

                <h4
                  className={`font-bold text-sm mt-2 ${
                    isCustom ? 'text-white' : 'text-slate-900'
                  }`}
                >
                  {s.label}
                </h4>
                <div
                  className={`text-xs mt-0.5 ${
                    isCustom ? 'text-slate-400' : 'text-slate-500'
                  }`}
                >
                  {s.crop} • {s.farm_area_ha} ha
                </div>

                <div
                  className={`mt-4 grid grid-cols-2 gap-2 p-3 rounded-xl border ${
                    isCustom
                      ? 'bg-slate-800/80 border-slate-700'
                      : 'bg-white/80 border-slate-100'
                  }`}
                >
                  <div>
                    <div className="text-[11px] text-slate-400">Predicted Yield</div>
                    <div
                      className={`text-xl font-black ${
                        isCustom ? 'text-white' : 'text-slate-900'
                      }`}
                    >
                      {s.predicted_yield_t_ha} <span className="text-xs font-normal">t/ha</span>
                    </div>
                    <div className="text-[10px] text-slate-400">
                      Range: {s.confidence_interval.lower} – {s.confidence_interval.upper}
                    </div>
                  </div>
                  <div>
                    <div className="text-[11px] text-slate-400">Net Profit (est.)</div>
                    <div
                      className={`text-xl font-black ${
                        netProfit >= 0
                          ? isCustom
                            ? 'text-emerald-400'
                            : 'text-emerald-700'
                          : 'text-rose-600'
                      }`}
                    >
                      ₹{netProfit.toLocaleString()}
                    </div>
                    <div className="text-[10px] text-slate-400">
                      Margin: {s.financial_estimates.profit_margin_pct}%
                    </div>
                  </div>
                </div>

                {/* Explanation text */}
                <p
                  className={`text-xs mt-3 leading-relaxed ${
                    isCustom ? 'text-slate-300' : 'text-slate-600'
                  }`}
                >
                  {s.explanation_text}
                </p>
              </div>

              <div
                className={`mt-4 pt-3 border-t flex items-center justify-between text-xs ${
                  isCustom ? 'border-slate-800 text-slate-400' : 'border-slate-100 text-slate-500'
                }`}
              >
                <span>
                  Production: <strong>{s.expected_production_tonnes.expected} tonnes</strong>
                </span>
                <span>
                  Mandi: <strong>₹{s.financial_estimates.projected_mandi_price_quintal}/qtl</strong>
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
