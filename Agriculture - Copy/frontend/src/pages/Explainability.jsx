import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import { HelpCircle, BarChart3, CheckCircle, AlertTriangle, Info, ArrowUp, ArrowDown } from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell
} from 'recharts';

export default function Explainability() {
  const [crop, setCrop] = useState('Rice');
  const [season, setSeason] = useState('Kharif');
  const [globalShap, setGlobalShap] = useState(null);
  const [localExplanation, setLocalExplanation] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const gRes = await api.getGlobalShap(7);
        if (gRes.success) setGlobalShap(gRes.global_importance);

        const lRes = await api.explainPrediction(crop, season);
        if (lRes.success) setLocalExplanation(lRes.explanation);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [crop, season]);

  const globalData = (globalShap?.top_features || []).map((f) => ({
    name: f.friendly_name,
    score: f.importance_score
  }));

  const localFactors = localExplanation?.top_factors || [];

  return (
    <div className="space-y-6">
      
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <HelpCircle className="w-6 h-6 text-emerald-600" />
            Explainable AI (SHAP Feature Attribution)
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Explains the <strong>exact mathematical factors</strong> behind every yield prediction, avoiding a "black box" model.
          </p>
        </div>

        <div className="flex items-center space-x-2 bg-white p-1.5 rounded-xl border border-slate-200 shadow-xs">
          <select
            value={crop}
            onChange={(e) => setCrop(e.target.value)}
            className="px-3 py-1.5 text-xs font-semibold bg-slate-50 border border-slate-200 rounded-lg text-slate-800 focus:outline-none"
          >
            <option value="Rice">Rice (Paddy)</option>
            <option value="Cotton(lint)">Cotton</option>
          </select>
          <select
            value={season}
            onChange={(e) => setSeason(e.target.value)}
            className="px-3 py-1.5 text-xs font-semibold bg-slate-50 border border-slate-200 rounded-lg text-slate-800 focus:outline-none"
          >
            <option value="Kharif">Kharif</option>
            <option value="Rabi">Rabi</option>
          </select>
        </div>
      </div>

      {/* Local Prediction Explanation Breakdown */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-xs space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-4">
          <div>
            <span className="text-xs font-bold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full uppercase tracking-wider">
              Local Attribution for {crop} ({season})
            </span>
            <h2 className="text-lg font-bold text-slate-900 mt-2">
              Why was your harvest predicted at {localExplanation?.predicted_yield} t/ha?
            </h2>
          </div>
          <div className="text-right">
            <div className="text-xs text-slate-400">Regional Dataset Baseline</div>
            <div className="text-xl font-bold text-slate-700">{localExplanation?.baseline_yield} t/ha</div>
          </div>
        </div>

        {/* Plain-Language Farmer Summary */}
        <div className="bg-emerald-50/70 border border-emerald-200/70 rounded-xl p-4 text-xs text-emerald-950 leading-relaxed space-y-2">
          <div className="font-bold flex items-center gap-1.5 text-emerald-900 text-sm">
            <Info className="w-4 h-4 text-emerald-600" />
            Plain-Language Takeaway for the Farmer:
          </div>
          <p>{localExplanation?.plain_language_explanation}</p>
        </div>

        {/* Feature Impact Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 pt-2">
          {localFactors.map((f, idx) => {
            const isPos = f.impact > 0;
            return (
              <div
                key={idx}
                className={`p-4 rounded-xl border flex flex-col justify-between ${
                  isPos
                    ? 'bg-emerald-50/40 border-emerald-200 text-emerald-950'
                    : 'bg-rose-50/40 border-rose-200 text-rose-950'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-700">{f.friendly_name}</span>
                    <span className={`flex items-center text-xs font-bold ${isPos ? 'text-emerald-700' : 'text-rose-600'}`}>
                      {isPos ? <ArrowUp className="w-3.5 h-3.5" /> : <ArrowDown className="w-3.5 h-3.5" />}
                      {isPos ? `+${f.impact}` : f.impact} t/ha
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1">
                    {isPos ? 'Contributed positively to higher yield.' : 'Created environmental / agronomic drag on yield.'}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Global SHAP Feature Importance */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-xs space-y-4">
        <div>
          <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-emerald-600" />
            Global Feature Importance (Across Entire District Dataset)
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Mean absolute SHAP value (|SHAP|) ranking which factors possess the highest predictive leverage over crop productivity.
          </p>
        </div>

        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={globalData}
              layout="vertical"
              margin={{ top: 10, right: 30, left: 140, bottom: 10 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis type="number" tick={{ fontSize: 11, fill: '#64748b' }} unit=" |SHAP|" />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fontSize: 11, fill: '#334155', fontWeight: 500 }}
              />
              <Tooltip />
              <Bar dataKey="score" fill="#059669" radius={[0, 4, 4, 0]}>
                {globalData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={index === 0 ? '#059669' : index < 3 ? '#10b981' : '#34d399'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

    </div>
  );
}
