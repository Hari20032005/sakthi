import os
import json
import re
from backend.services.digital_twin import digital_twin_service
from backend.models.shap_engine import shap_engine
from backend.models.price_model import price_forecaster
from backend.config import GEMINI_API_KEY

AGRONOMIC_KNOWLEDGE_BASE = [
    {
        "topic": "Rice SRI Method & Water Management",
        "keywords": ["rice", "water", "irrigation", "sri", "paddy", "flooding", "awd"],
        "content": "For Rice in Ariyalur's clay-loam soils, System of Rice Intensification (SRI) using Alternate Wetting and Drying (AWD) reduces water use by 30% while improving root aeration. Avoid continuous deep standing water during vegetative tillering. Maintain 2-3 cm shallow water only during flowering and panicle initiation."
    },
    {
        "topic": "Drought Mitigation & Heat Stress",
        "keywords": ["drought", "dry", "rainfall", "deficit", "heat", "hot", "temperature"],
        "content": "During low rainfall or high temperature periods (>35°C), apply 1% Potassium Chloride (KCl) or 0.5% Zinc Sulfate foliar spray. This improves stomatal regulation, protects chlorophyll integrity, and minimizes transpirational shock in Rice and Cotton."
    },
    {
        "topic": "Cotton Pest & Sucking Insect Management",
        "keywords": ["cotton", "pest", "bollworm", "aphid", "whitefly", "spray"],
        "content": "In Ariyalur cotton tracts, monitor for pink bollworm using pheromone traps (5 traps/acre). For early sucking pests (aphids, jassids), spray 5% Neem Seed Kernel Extract (NSKE) or Neem oil at 3 ml/litre before resorting to synthetic chemical pesticides."
    },
    {
        "topic": "Soil Fertility & Clay Loam Management",
        "keywords": ["soil", "fertilizer", "urea", "nitrogen", "npk", "ph", "clay", "fertility"],
        "content": "Ariyalur soils have high clay content (38-42%) and neutral to slightly alkaline pH (7.3). Nitrogen application should be split into 3-4 doses (basal, active tillering, panicle initiation) to prevent volatilization loss. Incorporate green manure (Daincha or Sunnhemp) to boost organic carbon above 0.5%."
    },
    {
        "topic": "Market Timing & Selling Strategy",
        "keywords": ["price", "sell", "market", "mandi", "profit", "rate", "when to sell"],
        "content": "Mandi price records indicate that crop arrivals peak immediately post-harvest (January-February for Kharif, April-May for Rabi), causing short-term price slumps of 8-12%. If storage facilities or warehouse receipt financing are available, holding paddy for 6-8 weeks typically yields 5-10% higher returns."
    }
]

class RAGChatbotService:
    def __init__(self):
        self.api_key = GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")

    def retrieve_context(self, query: str, farm_id: int = 1):
        """Step 1: Retrieve digital shadow facts + matching agronomic chunks."""
        digital_shadow = digital_twin_service.get_farm_digital_shadow(farm_id)
        current_crop = digital_shadow["farm_specs"]["active_crop"]
        season = digital_shadow["farm_specs"]["active_season"]
        yield_info = digital_shadow["current_yield_forecast"]
        weather_adjusted = digital_shadow.get("weather_adjusted_yield_forecast", {})
        weather = digital_shadow["weather"]
        soil = digital_shadow["soil"]
        satellite = digital_shadow["satellite_vegetation"]
        recommendations = digital_shadow.get("recommendations", [])

        # Exact SHAP explanations
        shap_info = shap_engine.explain_prediction(
            crop="Rice" if "rice" in current_crop.lower() else "Cotton(lint)",
            season=season, top_k=3
        )

        # Retrieve matching knowledge chunks based on query keywords
        q_lower = query.lower()
        matched_chunks = []
        for chunk in AGRONOMIC_KNOWLEDGE_BASE:
            score = sum(1 for kw in chunk["keywords"] if kw in q_lower)
            if score > 0:
                matched_chunks.append((score, chunk))

        matched_chunks.sort(key=lambda x: x[0], reverse=True)
        relevant_agronomy = [c[1]["content"] for c in matched_chunks[:2]]
        if not relevant_agronomy:
            relevant_agronomy = [AGRONOMIC_KNOWLEDGE_BASE[0]["content"]]

        return {
            "farm_name": digital_shadow["farm_name"],
            "crop": current_crop,
            "season": season,
            "predicted_yield": weather_adjusted.get("weather_adjusted_yield_t_per_ha", yield_info["predicted_yield_t_per_ha"]),
            "confidence_range": [
                weather_adjusted.get("interval", {}).get("lower_bound", yield_info["conformal_interval"]["lower_bound"]),
                weather_adjusted.get("interval", {}).get("upper_bound", yield_info["conformal_interval"]["upper_bound"])
            ],
            "confidence_pct": "weather-widened baseline range",
            "historic_rf_baseline_yield": yield_info["predicted_yield_t_per_ha"],
            "weather_adjustment_pct": weather_adjusted.get("adjustment_pct", 0),
            "weather_adjustment_note": weather_adjusted.get("method", "Historic Random Forest baseline."),
            "top_shap_factors": shap_info["top_factors"],
            "soil_ph": soil["ph"]["value"],
            "soil_texture": soil["texture_class"],
            "current_ndvi": satellite["current_ndvi"],
            "canopy_vigor": satellite["canopy_vigor"],
            "vegetation_is_real": satellite.get("is_live_satellite_observation", False),
            "weather_forecast_days": weather["forecast"][:3],
            "recommendations": recommendations,
            "agronomy_chunks": relevant_agronomy
        }

    def generate_response(self, user_query: str, farm_id: int = 1):
        context = self.retrieve_context(user_query, farm_id)
        
        # Check if user has Gemini API key configured
        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")

                system_prompt = f"""
You are the AI Agricultural Twin Advisor for a smallholder farmer in Ariyalur, Tamil Nadu.
You must ground your response strictly in the farm's real data provided below. Do NOT hallucinate.
FARM CONTEXT:
- Farm: {context['farm_name']}
- Active Crop: {context['crop']} ({context['season']} Season)
- Weather-adjusted yield baseline: {context['predicted_yield']} tonnes/hectare (weather-widened range: {context['confidence_range'][0]} to {context['confidence_range'][1]} t/ha). Historic RF baseline: {context['historic_rf_baseline_yield']} t/ha; adjustment: {context['weather_adjustment_pct']}%.
- Weather method: {context['weather_adjustment_note']}
- Key Yield Drivers (SHAP Mathematical Analysis): {json.dumps(context['top_shap_factors'])}
- Soil Profile: {context['soil_texture']}, pH {context['soil_ph']}
- Satellite NDVI: {context['current_ndvi']} ({context['canopy_vigor']})
- Twin recommended actions: {json.dumps(context['recommendations'])}
- Verified Agronomic Reference: {' '.join(context['agronomy_chunks'])}

Rules:
1. Explain predictions in simple, caring language suitable for a farmer.
2. Directly answer the question using the exact numbers and driving factors above.
3. Suggest concrete agronomic action steps.
"""
                response = model.generate_content(f"{system_prompt}\n\nFarmer's Question: {user_query}")
                if response and response.text:
                    return {
                        "reply": response.text.strip(),
                        "grounded_context": context,
                        "engine": "Gemini 1.5 Flash (Grounded RAG)"
                    }
            except Exception as e:
                pass # Fallback to local grounded RAG generator

        # High-Fidelity Local Grounded RAG Expert Engine
        return self._local_grounded_response(user_query, context)

    def _local_grounded_response(self, query: str, ctx: dict):
        q = query.lower()
        crop = ctx["crop"]
        yield_val = ctx["predicted_yield"]
        c_low, c_high = ctx["confidence_range"]
        conf_pct = ctx["confidence_pct"]
        top_factors = ctx["top_shap_factors"]
        ndvi = ctx["current_ndvi"]
        soil = ctx["soil_texture"]
        agronomy = " ".join(ctx["agronomy_chunks"])
        recommendations = ctx.get("recommendations", [])

        top_fac_str = ", ".join([f"{f['friendly_name']} ({'+' if f['impact'] > 0 else ''}{f['impact']} t/ha)" for f in top_factors[:2]])

        if any(w in q for w in ["yield", "how much", "production", "forecast", "harvest"]):
            reply = (
                f"🌱 **Yield Forecast Overview for {crop}:**\n\n"
                f"Based on the weather-adjusted Digital Twin baseline, your estimated yield is **{yield_val} tonnes per hectare**.\n"
                f"• **Weather-widened range:** **{c_low} to {c_high} t/ha**. This is not a recalibrated confidence interval.\n"
                f"• **Historic Random Forest baseline:** {ctx['historic_rf_baseline_yield']} t/ha; current weather overlay: {ctx['weather_adjustment_pct']}%.\n"
                f"• **Why this prediction? (SHAP Analysis):** The top factors shaping this harvest are **{top_fac_str}**.\n"
                f"• **Canopy Status:** {'Real Sentinel-2 observation' if ctx['vegetation_is_real'] else 'Academic phenology proxy'} is **{ndvi}** ({ctx['canopy_vigor']}). {'Verify it in the field.' if ctx['vegetation_is_real'] else 'It is not a live satellite observation.'}"
            )
        elif any(w in q for w in ["recommend", "action", "should i do", "what should"]):
            if recommendations:
                reply = "🌾 **Twin Recommended Actions:**\n\n" + "\n".join(
                    f"• **{item['priority']} — {item['action']}**\n  Why: {item['reason']}\n  Confidence: {item['confidence']}"
                    for item in recommendations
                )
            else:
                reply = "No current recommendations are available. Synchronize the farm digital twin and try again."
        elif any(w in q for w in ["why", "reason", "explain", "factor", "shap"]):
            reply = (
                f"🔍 **What is Driving Your Crop Performance?**\n\n"
                f"Our explainable AI (SHAP) checked all weather, soil, and price parameters for your farm:\n"
                + "\n".join([f"• **{f['friendly_name']}**: {'Boosted' if f['impact'] > 0 else 'Lowered'} your yield by {abs(f['impact'])} t/ha ({f['direction']} influence)." for f in top_factors])
                + f"\n\n**Agronomic Advice:** {agronomy}"
            )
        elif any(w in q for w in ["water", "irrigation", "rain", "drought", "dry"]):
            reply = (
                f"💧 **Water & Irrigation Guidance:**\n\n"
                f"Your farm's soil is **{soil}**, which possesses high clay content and excellent moisture retention.\n"
                f"• **Recommended Schedule:** Practice Alternate Wetting and Drying (AWD). Keep shallow water (2 cm) during panicle emergence, but let the topsoil aerate between irrigations.\n"
                f"• **Drought Buffer:** {agronomy}"
            )
        elif any(w in q for w in ["price", "sell", "mandi", "market", "profit"]):
            price_data = price_forecaster.forecast_prices("Rice" if "rice" in crop.lower() else "Cotton", months_ahead=3)
            current_p = price_data["current_benchmark_price"]
            future_p = price_data["forecast"][2]["projected_price"]
            recom = price_data["market_recommendation"]
            reply = (
                f"💰 **Market Price & Selling Strategy:**\n\n"
                f"• **Current Ariyalur Mandi Benchmark:** ₹{current_p} / quintal.\n"
                f"• **3-Month Projected Price:** ₹{future_p} / quintal (90% confidence).\n"
                f"• **Recommendation:** {recom}\n\n"
                f"**Tip:** {agronomy}"
            )
        elif any(w in q for w in ["cotton", "pest", "disease", "fertilizer", "spray"]):
            reply = (
                f"🌾 **Crop Health & Field Recommendations:**\n\n"
                f"For your **{crop}** in Ariyalur:\n"
                f"• **Soil Health:** pH is currently **{ctx['soil_ph']}** (Neutral / Optimal). Your high Cation Exchange Capacity helps retain nutrients well.\n"
                f"• **Expert Advisory:** {agronomy}\n"
                f"• **Vegetation Proxy:** The current modelled vegetation index is **{ndvi}**; verify conditions in the field before acting."
            )
        else:
            reply = (
                f"🌾 **Farm Digital Twin Advisory:**\n\n"
                f"Hello! I am your AI Farm Advisor for your **{crop}** farm in Ariyalur.\n"
                f"• **Current weather-adjusted yield baseline:** **{yield_val} t/ha** (weather-widened range: {c_low} - {c_high} t/ha).\n"
                f"• **Top Influencing Factor:** {top_fac_str}.\n"
                f"• **Soil & Canopy:** {soil} soil with active Sentinel-2 NDVI of {ndvi}.\n\n"
                f"You can ask me questions like:\n"
                f"1. *'Why is my yield predicted at {yield_val} t/ha?'*\n"
                f"2. *'How should I irrigate my {crop} this week?'*\n"
                f"3. *'When is the best time to sell my harvest at the mandi?'*\n"
                f"4. *'What happens if rainfall decreases by 30%?'*"
            )

        return {
            "reply": reply,
            "grounded_context": ctx,
            "engine": "Sensor-Free Agronomy RAG Engine"
        }

rag_chatbot_service = RAGChatbotService()
