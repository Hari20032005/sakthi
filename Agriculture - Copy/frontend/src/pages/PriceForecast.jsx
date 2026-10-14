import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import { BarChart3, TrendingUp, Calendar, AlertCircle, ShoppingBag, ArrowUpRight } from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  ComposedChart
} from 'recharts';

export default function PriceForecast() {
  const [crop, setCrop] = useState('Rice');
  const [priceData, setPriceData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchPrices = async () => {
      setLoading(true);
      try {
        const res = await api.predictPrice(crop, 6);
        if (res.success) {
          setPriceData(res.price_forecast);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchPrices();
  }, [crop]);

  // Combine historical and future forecast points for seamless visualization
  const historyPoints = (priceData?.historical_trend || []).map((h) => ({
    date: h.date,
    historical_price: h.modal_price,
    type: 'Historical Mandi Arrival'
  }));

  const forecastPoints = (priceData?.forecast || []).map((f) => ({
    date: f.date,
    projected_price: f.projected_price,
    lower_bound: f.lower_bound,
    upper_bound: f.upper_bound,
    type: 'Model Projection (90% Conf)'
  }));

  const combinedData = [...historyPoints, ...forecastPoints];

  return (
    <div className="space-y-6">
      
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <BarChart3 className="w-6 h-6 text-emerald-600" />
            Agricultural Commodity Market Price Forecasting
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Time-series projection trained on <strong>AGMARKNET Mandi arrivals</strong> for Ariyalur & Tamil Nadu markets.
          </p>
        </div>

        {/* Commodity Toggle */}
        <div className="flex items-center space-x-2 bg-white p-1 rounded-xl border border-slate-200 shadow-xs">
          <button
            onClick={() => setCrop('Rice')}
            className={`px-4 py-1.5 text-xs font-semibold rounded-lg transition-all ${
              crop === 'Rice' ? 'bg-emerald-600 text-white' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Paddy / Rice
          </button>
          <button
            onClick={() => setCrop('Cotton')}
            className={`px-4 py-1.5 text-xs font-semibold rounded-lg transition-all ${
              crop === 'Cotton' ? 'bg-emerald-600 text-white' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Cotton
          </button>
        </div>
      </div>

      {/* Top Advisory Banner */}
      <div className="bg-gradient-to-r from-slate-900 to-emerald-950 text-white p-6 rounded-2xl shadow-md flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <span className="text-xs uppercase tracking-wider text-emerald-400 font-bold bg-emerald-900/60 px-2.5 py-1 rounded-full border border-emerald-700/50">
            Market Action Strategy
          </span>
          <h2 className="text-xl font-bold text-white mt-3">
            {priceData?.action === 'HOLD_FOR_PEAK' ? 'Recommendation: Stagger Sales for Peak Mandi Window' : 'Recommendation: Sell on Immediate Harvest'}
          </h2>
          <p className="text-xs text-emerald-200/80 mt-1.5 leading-relaxed max-w-2xl">
            {priceData?.market_recommendation}
          </p>
        </div>

        <div className="bg-white/10 backdrop-blur-md border border-white/15 rounded-xl p-4 text-right shrink-0">
          <div className="text-xs text-emerald-300">Ariyalur Mandi Benchmark</div>
          <div className="text-3xl font-extrabold text-white mt-0.5">
            ₹{priceData?.current_benchmark_price} <span className="text-sm font-normal text-emerald-200">/ quintal</span>
          </div>
          <div className="text-[11px] text-emerald-400 mt-1 flex items-center justify-end gap-1">
            <ArrowUpRight className="w-3.5 h-3.5" />
            <span>3-Month Target: ₹{priceData?.forecast?.[2]?.projected_price || '...'}</span>
          </div>
        </div>
      </div>

      {/* Chart: Historical Prices vs 6-Month Projected Trend */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h3 className="font-bold text-slate-900 text-base">Historical Mandi Rates & 6-Month Projection Envelope</h3>
            <p className="text-xs text-slate-500">
              Grey: Past mandi arrivals. Emerald: Projected price path with 90% confidence expansion.
            </p>
          </div>
          <div className="flex items-center space-x-3 text-xs">
            <div className="flex items-center space-x-1.5">
              <span className="w-3 h-3 rounded-full bg-slate-400"></span>
              <span className="text-slate-600">Historical Price</span>
            </div>
            <div className="flex items-center space-x-1.5">
              <span className="w-3 h-3 rounded-full bg-emerald-500"></span>
              <span className="text-slate-600">Forecast</span>
            </div>
          </div>
        </div>

        <div className="h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={combinedData} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#64748b' }} />
              <YAxis domain={['auto', 'auto']} tick={{ fontSize: 11, fill: '#64748b' }} unit=" ₹" />
              <Tooltip
                content={({ active, payload }) => {
                  if (active && payload && payload.length) {
                    const d = payload[0].payload;
                    return (
                      <div className="bg-slate-900 text-white p-3 rounded-xl text-xs shadow-xl space-y-1">
                        <div className="font-bold text-emerald-400">{d.date}</div>
                        {d.historical_price && (
                          <div>Historical Mandi Price: <strong>₹{d.historical_price} / qtl</strong></div>
                        )}
                        {d.projected_price && (
                          <>
                            <div className="text-emerald-300">Projected Rate: <strong>₹{d.projected_price} / qtl</strong></div>
                            <div className="text-slate-400">90% Range: ₹{d.lower_bound} – ₹{d.upper_bound}</div>
                          </>
                        )}
                      </div>
                    );
                  }
                  return null;
                }}
              />
              <Line type="monotone" dataKey="historical_price" stroke="#64748b" strokeWidth={2} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="projected_price" stroke="#059669" strokeWidth={2.5} dot={{ r: 4, fill: '#10b981' }} strokeDasharray="4 4" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Forecast Table breakdown */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-xs">
        <h3 className="font-bold text-slate-900 text-base mb-3">Projected Monthly Mandi Price Horizon</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
          {(priceData?.forecast || []).map((f, idx) => (
            <div key={idx} className="bg-slate-50 border border-slate-200/70 rounded-xl p-3.5 text-center">
              <div className="text-xs font-semibold text-slate-500 uppercase">{f.date}</div>
              <div className="text-lg font-black text-slate-900 mt-1">₹{f.projected_price}</div>
              <div className="text-[11px] text-slate-400 mt-0.5">₹{f.lower_bound} – ₹{f.upper_bound}</div>
              <div className="mt-2 text-[10px] bg-emerald-100 text-emerald-800 font-bold px-1.5 py-0.5 rounded">
                +{idx * 30 + 30} Days
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
