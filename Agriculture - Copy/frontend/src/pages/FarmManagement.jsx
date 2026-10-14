import React, { useState } from 'react';
import { Settings, MapPin, Plus, CheckCircle, Sprout, Layers } from 'lucide-react';
import { api } from '../api/client';

export default function FarmManagement({ farms, setFarms, activeFarm, setActiveFarm }) {
  const [showAddModal, setShowAddModal] = useState(false);
  const [formData, setFormData] = useState({
    farm_name: '',
    latitude: '11.137',
    longitude: '79.078',
    district: 'Ariyalur',
    size_hectares: '3.5',
    soil_type: 'Clay loam',
    primary_crop: 'Rice',
    current_season: 'Kharif',
  });
  const [savedSuccess, setSavedSuccess] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const res = await api.createFarm(formData);
      const newFarm = res.farm;
      setFarms([...farms, newFarm]);
      setActiveFarm(newFarm);
      setSavedSuccess(true);
      setTimeout(() => {
        setSavedSuccess(false);
        setShowAddModal(false);
      }, 1500);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="space-y-6">
      
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <Settings className="w-6 h-6 text-emerald-600" />
            Farm Plots & Spatial Profile Management
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Register and manage your farm holdings to instantiate location-specific <strong>Digital Shadows</strong>.
          </p>
        </div>

        <button
          onClick={() => setShowAddModal(true)}
          className="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs px-4 py-2 rounded-xl transition-all shadow-sm flex items-center space-x-1.5"
        >
          <Plus className="w-4 h-4" />
          <span>Register New Farm Plot</span>
        </button>
      </div>

      {/* Farms List */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {farms.map((f) => {
          const isActive = f.farm_id === activeFarm?.farm_id;
          return (
            <div
              key={f.farm_id}
              className={`rounded-2xl p-5 border flex flex-col justify-between transition-all ${
                isActive
                  ? 'bg-emerald-50/40 border-emerald-300 ring-2 ring-emerald-500/20'
                  : 'bg-white border-slate-200 shadow-xs'
              }`}
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-emerald-700 bg-emerald-100/60 px-2.5 py-0.5 rounded-full">
                    Farm ID #{f.farm_id}
                  </span>
                  {isActive && (
                    <span className="text-[10px] bg-emerald-600 text-white font-bold px-2 py-0.5 rounded-full">
                      Active Digital Twin
                    </span>
                  )}
                </div>

                <h3 className="font-bold text-slate-900 text-base mt-2.5">{f.farm_name}</h3>
                
                <div className="flex items-center space-x-1 text-xs text-slate-500 mt-1">
                  <MapPin className="w-3.5 h-3.5 text-slate-400" />
                  <span>{f.district}, {f.state || 'Tamil Nadu'} ({f.latitude}°N, {f.longitude}°E)</span>
                </div>

                <div className="mt-4 space-y-1.5 text-xs text-slate-600 border-t border-slate-100 pt-3">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Total Size:</span>
                    <span className="font-semibold text-slate-800">{f.size_hectares} ha ({(f.size_hectares * 2.471).toFixed(1)} acres)</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Soil Classification:</span>
                    <span className="font-semibold text-slate-800">{f.soil_type}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Active Crop:</span>
                    <span className="font-semibold text-slate-800">{f.primary_crop}</span>
                  </div>
                </div>
              </div>

              <div className="mt-5 pt-3 border-t border-slate-100">
                {!isActive ? (
                  <button
                    onClick={() => setActiveFarm(f)}
                    className="w-full bg-slate-100 hover:bg-emerald-50 hover:text-emerald-700 text-slate-700 text-xs font-semibold py-2 rounded-xl transition-colors"
                  >
                    Set as Active Digital Twin
                  </button>
                ) : (
                  <div className="text-center text-xs text-emerald-700 font-semibold py-1">
                    ✓ Currently Connected & Syncing
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Add Farm Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4 border border-slate-200">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="font-bold text-slate-900 text-base">Register New Farm Plot</h3>
              <button onClick={() => setShowAddModal(false)} className="text-slate-400 hover:text-slate-600 text-sm">✕</button>
            </div>

            {savedSuccess ? (
              <div className="text-center py-6 space-y-2">
                <CheckCircle className="w-10 h-10 text-emerald-500 mx-auto" />
                <div className="font-bold text-slate-800 text-sm">Farm Plot Registered Successfully!</div>
                <div className="text-xs text-slate-400">Synthesizing location digital shadow...</div>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-3 text-xs">
                <div>
                  <label className="block text-slate-600 font-medium mb-1">Farm Plot Name</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Ariyalur North Paddy Field"
                    value={formData.farm_name}
                    onChange={(e) => setFormData({ ...formData, farm_name: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-slate-800 focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-600 font-medium mb-1">Latitude (°N)</label>
                    <input
                      type="number"
                      step="0.001"
                      value={formData.latitude}
                      onChange={(e) => setFormData({ ...formData, latitude: e.target.value })}
                      className="w-full px-3 py-2 border border-slate-200 rounded-lg text-slate-800 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-600 font-medium mb-1">Longitude (°E)</label>
                    <input
                      type="number"
                      step="0.001"
                      value={formData.longitude}
                      onChange={(e) => setFormData({ ...formData, longitude: e.target.value })}
                      className="w-full px-3 py-2 border border-slate-200 rounded-lg text-slate-800 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-600 font-medium mb-1">Area (Hectares)</label>
                    <input
                      type="number"
                      step="0.1"
                      value={formData.size_hectares}
                      onChange={(e) => setFormData({ ...formData, size_hectares: e.target.value })}
                      className="w-full px-3 py-2 border border-slate-200 rounded-lg text-slate-800 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-600 font-medium mb-1">Primary Crop</label>
                    <select
                      value={formData.primary_crop}
                      onChange={(e) => setFormData({ ...formData, primary_crop: e.target.value })}
                      className="w-full px-3 py-2 border border-slate-200 rounded-lg text-slate-800 focus:outline-none"
                    >
                      <option value="Rice">Rice (Paddy)</option>
                      <option value="Cotton(lint)">Cotton</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-slate-600 font-medium mb-1">Soil Type</label>
                  <select
                    value={formData.soil_type}
                    onChange={(e) => setFormData({ ...formData, soil_type: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg text-slate-800 focus:outline-none"
                  >
                    <option value="Clay loam">Clay loam (Optimal water holding)</option>
                    <option value="Black Cotton Soil">Black Cotton Soil (Deep clay)</option>
                    <option value="Sandy Loam">Sandy Loam</option>
                  </select>
                </div>

                <div className="pt-3 flex items-center justify-end space-x-2">
                  <button
                    type="button"
                    onClick={() => setShowAddModal(false)}
                    className="px-4 py-2 rounded-lg text-slate-500 hover:bg-slate-100"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold"
                  >
                    Create Farm Plot
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
