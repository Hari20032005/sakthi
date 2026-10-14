const BASE_URL = '/api';

export const api = {
  async getHealth() {
    const res = await fetch(`${BASE_URL}/health`);
    return res.json();
  },

  async getFarms() {
    const res = await fetch(`${BASE_URL}/farms`);
    return res.json();
  },

  async getFarm(farmId) {
    const res = await fetch(`${BASE_URL}/farms/${farmId}`);
    return res.json();
  },

  async createFarm(farm) {
    const res = await fetch(`${BASE_URL}/farms`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(farm),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Could not create farm');
    return data;
  },

  async getTwinHistory(farmId) {
    const res = await fetch(`${BASE_URL}/farms/${farmId}/digital-shadow/history`);
    return res.json();
  },

  async getRecommendations(farmId) {
    const res = await fetch(`${BASE_URL}/farms/${farmId}/recommendations`);
    return res.json();
  },

  async completeRecommendation(farmId, recommendation) {
    const res = await fetch(`${BASE_URL}/farms/${farmId}/recommendations/${recommendation.id}/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: recommendation.action }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Could not log action');
    return data;
  },

  async getDigitalShadow(farmId = 1) {
    const res = await fetch(`${BASE_URL}/farms/${farmId}/digital-shadow`);
    return res.json();
  },

  async predictYield(crop = 'Rice', season = 'Kharif', overrides = {}) {
    const res = await fetch(`${BASE_URL}/forecast/yield`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ crop, season, overrides }),
    });
    return res.json();
  },

  async predictPrice(crop = 'Rice', months = 6) {
    const res = await fetch(`${BASE_URL}/forecast/price?crop=${crop}&months=${months}`);
    return res.json();
  },

  async getModelBenchmarks() {
    const res = await fetch(`${BASE_URL}/forecast/benchmark`);
    return res.json();
  },

  async simulateScenarios(crop = 'Rice', season = 'Kharif', area_ha = 2.0, custom_scenario = null) {
    const res = await fetch(`${BASE_URL}/scenarios/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ crop, season, area_ha, custom_scenario }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || `Simulation request failed (${res.status})`);
    }
    return data;
  },

  async simulateCustomScenario(crop = 'Rice', season = 'Kharif', area_ha = 2.0, rainfall_anomaly = 0, temperature_anomaly = 0) {
    const res = await fetch(`${BASE_URL}/scenarios/custom`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ crop, season, area_ha, rainfall_anomaly, temperature_anomaly }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || `Custom simulation failed (${res.status})`);
    }
    return data;
  },

  async getGlobalShap(top_n = 8) {
    const res = await fetch(`${BASE_URL}/explain/global?top_n=${top_n}`);
    return res.json();
  },

  async explainPrediction(crop = 'Rice', season = 'Kharif', overrides = {}) {
    const res = await fetch(`${BASE_URL}/explain/prediction`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ crop, season, overrides }),
    });
    return res.json();
  },

  async sendChatMessage(message, farm_id = 1) {
    const res = await fetch(`${BASE_URL}/chat/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, farm_id }),
    });
    return res.json();
  },

  async getPromptStarters() {
    const res = await fetch(`${BASE_URL}/chat/starters`);
    return res.json();
  },

  async getCooperativeSummary() {
    const res = await fetch(`${BASE_URL}/cooperative/summary`);
    return res.json();
  },

  async login(email, role = 'farmer') {
    const res = await fetch(`${BASE_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, role }),
    });
    return res.json();
  },
};
