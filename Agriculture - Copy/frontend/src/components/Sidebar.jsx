import React from 'react';
import {
  LayoutDashboard,
  TrendingUp,
  BarChart3,
  Sliders,
  HelpCircle,
  MessageSquare,
  Building2,
  Settings,
  Sparkles,
  Info
} from 'lucide-react';

export default function Sidebar({ activeTab, setActiveTab, currentRole }) {
  const farmerNavItems = [
    { id: 'dashboard', label: 'Farm Digital Shadow', icon: LayoutDashboard },
    { id: 'forecast', label: 'Yield Forecasting & Uncertainty', icon: TrendingUp },
    { id: 'prices', label: 'Mandi Price Forecast', icon: BarChart3 },
    { id: 'scenarios', label: 'What-If Scenario Simulator', icon: Sliders },
    { id: 'explain', label: 'SHAP Explainability (XAI)', icon: HelpCircle },
    { id: 'chatbot', label: 'AI Advisory Chatbot (RAG)', icon: MessageSquare, badge: 'AI' },
    { id: 'farms', label: 'Farm Plots & Soil Profile', icon: Settings },
  ];

  const coopNavItems = [
    { id: 'cooperative', label: 'Cooperative Overview', icon: Building2 },
    { id: 'dashboard', label: 'Farm Digital Shadow', icon: LayoutDashboard },
    { id: 'forecast', label: 'Yield Forecasting', icon: TrendingUp },
    { id: 'scenarios', label: 'Scenario Testing', icon: Sliders },
    { id: 'prices', label: 'Market Trends', icon: BarChart3 },
    { id: 'chatbot', label: 'AI Advisory Chatbot', icon: MessageSquare },
  ];

  const items = currentRole === 'cooperative_admin' ? coopNavItems : farmerNavItems;

  return (
    <aside className="w-64 bg-white border-r border-slate-200 flex flex-col justify-between shrink-0 min-h-[calc(100vh-4rem)]">
      <div className="p-4 space-y-1">
        <div className="px-3 py-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">
          {currentRole === 'cooperative_admin' ? 'Cooperative Portal' : 'Farmer Decision Support'}
        </div>

        {items.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl font-medium text-sm transition-all ${
                isActive
                  ? 'bg-emerald-50 text-emerald-700 shadow-sm border border-emerald-200 font-semibold'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
              }`}
            >
              <div className="flex items-center space-x-3">
                <Icon className={`w-4 h-4 ${isActive ? 'text-emerald-600' : 'text-slate-400'}`} />
                <span>{item.label}</span>
              </div>
              {item.badge && (
                <span className="text-[10px] bg-gradient-to-r from-emerald-500 to-teal-500 text-white font-bold px-1.5 py-0.5 rounded-full shadow-xs">
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Public Data Info Widget */}
      <div className="p-4 m-3 bg-emerald-900/5 rounded-2xl border border-emerald-900/10 text-xs text-slate-600 space-y-2">
        <div className="flex items-center space-x-2 text-emerald-800 font-semibold">
          <Sparkles className="w-4 h-4 text-emerald-600" />
          <span>Zero-Sensor Pipeline</span>
        </div>
        <p className="text-[11px] text-slate-500 leading-relaxed">
          Powered entirely by public Open-Meteo, ISRIC SoilGrids, Sentinel-2 NDVI, and Agmarknet mandi feeds.
        </p>
      </div>
    </aside>
  );
}
