import React, { useState, useEffect } from 'react';
import { api } from './api/client';
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import YieldForecast from './pages/YieldForecast';
import PriceForecast from './pages/PriceForecast';
import ScenarioSim from './pages/ScenarioSim';
import Explainability from './pages/Explainability';
import Chatbot from './pages/Chatbot';
import CooperativeView from './pages/CooperativeView';
import FarmManagement from './pages/FarmManagement';

export default function App() {
  const getInitialTab = () => {
    const hash = window.location.hash ? window.location.hash.replace('#', '') : '';
    if (['dashboard', 'forecast', 'prices', 'scenarios', 'explain', 'chatbot', 'cooperative', 'farms'].includes(hash)) {
      return hash;
    }
    return 'dashboard';
  };
  const initTab = getInitialTab();
  const [currentRole, setCurrentRole] = useState(initTab === 'cooperative' ? 'cooperative_admin' : 'farmer');
  const [activeTab, setActiveTab] = useState(initTab);

  useEffect(() => {
    const handleHashChange = () => {
      const tab = getInitialTab();
      setActiveTab(tab);
      if (tab === 'cooperative') {
        setCurrentRole('cooperative_admin');
      } else {
        setCurrentRole('farmer');
      }
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);
  const [farms, setFarms] = useState([]);
  const [activeFarm, setActiveFarm] = useState(null);
  const [digitalShadow, setDigitalShadow] = useState(null);
  const [loading, setLoading] = useState(true);

  // Fetch initial farms & active farm digital shadow
  const loadInitialData = async () => {
    setLoading(true);
    try {
      const farmsRes = await api.getFarms();
      if (farmsRes.success && farmsRes.farms?.length > 0) {
        setFarms(farmsRes.farms);
        const initialFarm = farmsRes.farms[0];
        setActiveFarm(initialFarm);

        const shadowRes = await api.getDigitalShadow(initialFarm.farm_id);
        if (shadowRes.success) {
          setDigitalShadow(shadowRes.digital_shadow);
        }
      }
    } catch (err) {
      console.error("Failed to load initial farm digital shadow:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  // When active farm changes, reload its digital shadow
  useEffect(() => {
    if (activeFarm) {
      const reloadShadow = async () => {
        try {
          const res = await api.getDigitalShadow(activeFarm.farm_id);
          if (res.success) {
            setDigitalShadow(res.digital_shadow);
          }
        } catch (e) {
          console.error(e);
        }
      };
      reloadShadow();
    }
  }, [activeFarm]);

  // Adjust active tab when role changes
  useEffect(() => {
    if (currentRole === 'cooperative_admin') {
      setActiveTab('cooperative');
    } else {
      setActiveTab('dashboard');
    }
  }, [currentRole]);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      <Navbar
        currentRole={currentRole}
        setCurrentRole={setCurrentRole}
        activeFarm={activeFarm}
        setActiveFarm={setActiveFarm}
        farms={farms}
        onRefresh={loadInitialData}
      />

      <div className="flex flex-1">
        <Sidebar
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          currentRole={currentRole}
        />

        <main className="flex-1 p-6 max-w-7xl mx-auto w-full overflow-y-auto">
          {activeTab === 'dashboard' && (
            <Dashboard digitalShadow={digitalShadow} loading={loading} activeFarm={activeFarm} />
          )}

          {activeTab === 'forecast' && (
            <YieldForecast activeFarm={activeFarm} />
          )}

          {activeTab === 'prices' && (
            <PriceForecast />
          )}

          {activeTab === 'scenarios' && (
            <ScenarioSim activeFarm={activeFarm} />
          )}

          {activeTab === 'explain' && (
            <Explainability />
          )}

          {activeTab === 'chatbot' && (
            <Chatbot activeFarm={activeFarm} />
          )}

          {activeTab === 'cooperative' && (
            <CooperativeView />
          )}

          {activeTab === 'farms' && (
            <FarmManagement
              farms={farms}
              setFarms={setFarms}
              activeFarm={activeFarm}
              setActiveFarm={setActiveFarm}
            />
          )}
        </main>
      </div>
    </div>
  );
}
