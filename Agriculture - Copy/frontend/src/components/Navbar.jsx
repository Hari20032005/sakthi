import React from 'react';
import { Sprout, Users, ShieldCheck, RefreshCw, MapPin } from 'lucide-react';

export default function Navbar({ currentRole, setCurrentRole, activeFarm, setActiveFarm, farms, onRefresh }) {
  return (
    <header className="bg-emerald-900 text-white shadow-md border-b border-emerald-800 sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        
        {/* Brand & Project Logo */}
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/20 border border-emerald-400/40 flex items-center justify-center text-emerald-300 shadow-inner">
            <Sprout className="w-6 h-6 text-emerald-400" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-bold text-lg tracking-tight text-white">AgriTwin India</span>
              <span className="bg-emerald-700/60 text-emerald-200 text-xs px-2 py-0.5 rounded-full border border-emerald-500/30 font-medium">
                Sensor-Free
              </span>
            </div>
            <p className="text-xs text-emerald-300/80">Public Data Powered Agricultural Digital Twin</p>
          </div>
        </div>

        {/* Center Farm Selector */}
        <div className="hidden md:flex items-center space-x-3 bg-emerald-950/60 px-3 py-1.5 rounded-lg border border-emerald-700/50">
          <MapPin className="w-4 h-4 text-emerald-400" />
          <span className="text-xs text-emerald-300 font-medium">Active Farm:</span>
          <select
            value={activeFarm?.farm_id || 1}
            onChange={(e) => {
              const selected = farms.find(f => f.farm_id === parseInt(e.target.value));
              if (selected) setActiveFarm(selected);
            }}
            className="bg-transparent text-sm text-white font-medium focus:outline-none cursor-pointer"
          >
            {farms.map((f) => (
              <option key={f.farm_id} value={f.farm_id} className="bg-gray-800 text-white">
                {f.farm_name} ({f.district})
              </option>
            ))}
          </select>
        </div>

        {/* Right Actions: Role Toggle & Status */}
        <div className="flex items-center space-x-4">
          <div className="flex items-center bg-emerald-950/80 p-1 rounded-lg border border-emerald-700/60 text-xs">
            <button
              onClick={() => setCurrentRole('farmer')}
              className={`px-3 py-1 rounded-md transition-all font-medium flex items-center space-x-1.5 ${
                currentRole === 'farmer'
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'text-emerald-300 hover:text-white'
              }`}
            >
              <Sprout className="w-3.5 h-3.5" />
              <span>Farmer</span>
            </button>
            <button
              onClick={() => setCurrentRole('cooperative_admin')}
              className={`px-3 py-1 rounded-md transition-all font-medium flex items-center space-x-1.5 ${
                currentRole === 'cooperative_admin'
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'text-emerald-300 hover:text-white'
              }`}
            >
              <Users className="w-3.5 h-3.5" />
              <span>Cooperative Admin</span>
            </button>
          </div>

          <button
            onClick={onRefresh}
            title="Refresh Digital Shadow Data"
            className="p-2 rounded-lg bg-emerald-800/60 hover:bg-emerald-700 text-emerald-200 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

      </div>
    </header>
  );
}
