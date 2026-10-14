import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import { Building2, Users, Layers, AlertTriangle, ShieldAlert, ArrowUpRight, CheckCircle2 } from 'lucide-react';

export default function CooperativeView() {
  const [coopData, setCoopData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchCoop = async () => {
      setLoading(true);
      try {
        const res = await api.getCooperativeSummary();
        if (res.success) {
          setCoopData(res);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchCoop();
  }, []);

  const metrics = coopData?.metrics;
  const farms = coopData?.farms || [];
  const alerts = coopData?.regional_risk_alerts || [];

  return (
    <div className="space-y-6">
      
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <Building2 className="w-6 h-6 text-emerald-600" />
            {coopData?.cooperative_name || 'Farmers Cooperative Federation'}
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            District-scale aggregated decision support & harvest planning across <strong>{metrics?.enrolled_farms || '...'} Member Farms</strong>.
          </p>
        </div>

        <span className="text-xs bg-emerald-100 text-emerald-800 font-bold px-3 py-1 rounded-full border border-emerald-300">
          Ariyalur District Federation
        </span>
      </div>

      {/* Aggregate Metric Highlights */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-xs">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Enrolled Land Acreage</span>
          <div className="text-3xl font-extrabold text-slate-900 mt-2">
            {metrics?.total_cultivated_hectares} <span className="text-sm font-normal text-slate-500">ha</span>
          </div>
          <div className="text-xs text-slate-400 mt-1">({metrics?.total_cultivated_acres} Total Acres)</div>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-xs">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Expected Federation Harvest</span>
          <div className="text-3xl font-extrabold text-emerald-600 mt-2">
            {metrics?.aggregate_expected_harvest_tonnes} <span className="text-sm font-normal text-slate-500">tonnes</span>
          </div>
          <div className="text-xs text-slate-400 mt-1">
            90% Range: {metrics?.aggregate_harvest_confidence_range?.[0]} – {metrics?.aggregate_harvest_confidence_range?.[1]} t
          </div>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-xs">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Projected Market Value</span>
          <div className="text-3xl font-extrabold text-slate-900 mt-2">
            ₹{metrics?.total_estimated_market_value_lakhs} <span className="text-sm font-normal text-slate-500">Lakhs</span>
          </div>
          <div className="text-xs text-emerald-600 mt-1">Based on mandi 3-month projected price</div>
        </div>

        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-xs">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Commodity Distribution</span>
          <div className="flex items-center space-x-4 mt-2">
            <div>
              <div className="text-lg font-bold text-slate-900">{coopData?.crops_breakdown?.Rice} ha</div>
              <div className="text-[11px] text-slate-400">Rice (Paddy)</div>
            </div>
            <div>
              <div className="text-lg font-bold text-slate-900">{coopData?.crops_breakdown?.Cotton} ha</div>
              <div className="text-[11px] text-slate-400">Cotton</div>
            </div>
          </div>
        </div>
      </div>

      {/* Regional Risk Alerts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {alerts.map((al, idx) => (
          <div key={idx} className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start space-x-3 text-xs text-amber-900">
            <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <div className="font-bold text-amber-950 uppercase tracking-wide">{al.cluster}</div>
              <div className="mt-1 leading-relaxed">{al.message}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Member Farms Status Table */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="font-bold text-slate-900 text-base">Federation Member Farm Holdings</h3>
            <p className="text-xs text-slate-500 mt-0.5">Live digital shadow status across all registered plots.</p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-400 text-xs uppercase tracking-wider">
                <th className="py-3 px-5">Farm & Location</th>
                <th className="py-3 px-4">Owner</th>
                <th className="py-3 px-4">Crop</th>
                <th className="py-3 px-4">Area (ha)</th>
                <th className="py-3 px-4">Predicted Yield</th>
                <th className="py-3 px-4">90% Range</th>
                <th className="py-3 px-4">Est. Mandi Value</th>
                <th className="py-3 px-5">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {farms.map((f, i) => (
                <tr key={i} className="hover:bg-slate-50 transition-colors">
                  <td className="py-3.5 px-5 font-semibold text-slate-900">
                    {f.farm_name}
                    <div className="text-[11px] text-slate-400 font-normal">{f.district}, {f.state}</div>
                  </td>
                  <td className="py-3.5 px-4 text-xs">{f.owner_name}</td>
                  <td className="py-3.5 px-4 text-xs font-medium">{f.primary_crop}</td>
                  <td className="py-3.5 px-4 text-xs">{f.size_hectares} ha</td>
                  <td className="py-3.5 px-4 font-bold text-emerald-700">{f.predicted_yield_t_ha} t/ha</td>
                  <td className="py-3.5 px-4 text-xs text-slate-500">
                    {f.confidence_range[0]} – {f.confidence_range[1]} t/ha
                  </td>
                  <td className="py-3.5 px-4 text-xs font-semibold text-slate-800">
                    ₹{f.estimated_mandi_value_inr.toLocaleString()}
                  </td>
                  <td className="py-3.5 px-5">
                    <span className="bg-emerald-100 text-emerald-800 text-[10px] font-bold px-2 py-0.5 rounded-full">
                      {f.health_status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
}
