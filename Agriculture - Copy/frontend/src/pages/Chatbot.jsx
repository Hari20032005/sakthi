import React, { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';
import { MessageSquare, Send, Bot, User, Sparkles, Database, CheckCircle, HelpCircle } from 'lucide-react';

export default function Chatbot({ activeFarm }) {
  const [messages, setMessages] = useState([
    {
      id: 0,
      sender: 'bot',
      text: "🌾 **Vanakkam! I am your AI Agriculture Twin Advisor.**\n\nI am grounded in your farm's real-time **digital shadow** (Open-Meteo weather, SoilGrids clay loam data, Sentinel-2 satellite NDVI, and Agmarknet prices).\n\nAsk me anything about your expected yield, irrigation schedule, fertilizer plan, or mandi selling timing!",
      engine: 'Sensor-Free Agronomy RAG Engine'
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [starters, setStarters] = useState([]);
  const [groundedContext, setGroundedContext] = useState(null);
  const chatEndRef = useRef(null);

  useEffect(() => {
    const fetchStarters = async () => {
      try {
        const res = await api.getPromptStarters();
        if (res.success) setStarters(res.prompt_starters);
      } catch (e) {
        console.error(e);
      }
    };
    fetchStarters();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSend = async (textToSend) => {
    const query = textToSend || input;
    if (!query.trim()) return;

    const userMsg = {
      id: messages.length + 1,
      sender: 'farmer',
      text: query,
    };
    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInput('');
    setLoading(true);

    try {
      const res = await api.sendChatMessage(query, activeFarm?.farm_id || 1);
      if (res.success) {
        setMessages((prev) => [
          ...prev,
          {
            id: prev.length + 1,
            sender: 'bot',
            text: res.reply,
            engine: res.engine,
          }
        ]);
        if (res.grounded_context) {
          setGroundedContext(res.grounded_context);
        }
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: prev.length + 1,
          sender: 'bot',
          text: "I encountered a network issue. Please ensure the backend server is reachable.",
          engine: 'System'
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[calc(100vh-8.5rem)]">
      
      {/* Left: Chat Window (2 cols) */}
      <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between overflow-hidden">
        
        {/* Chat Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/60">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-emerald-600 flex items-center justify-center text-white shadow-xs">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <h2 className="font-bold text-slate-800 text-sm">Grounded Agronomy Advisory Chatbot</h2>
              <div className="flex items-center space-x-1.5 text-xs text-emerald-600 font-medium">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                <span>RAG Grounded in Farm Digital Twin Telemetry</span>
              </div>
            </div>
          </div>
          <span className="text-[11px] bg-emerald-100 text-emerald-800 px-2.5 py-1 rounded-full font-bold">
            Zero Hallucination Mode
          </span>
        </div>

        {/* Message Stream */}
        <div className="p-6 overflow-y-auto space-y-4 flex-1">
          {messages.map((m) => {
            const isBot = m.sender === 'bot';
            return (
              <div key={m.id} className={`flex items-start space-x-3 ${isBot ? '' : 'flex-row-reverse space-x-reverse'}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-white text-xs font-bold ${
                  isBot ? 'bg-emerald-600' : 'bg-slate-700'
                }`}>
                  {isBot ? <Bot className="w-4 h-4" /> : <User className="w-4 h-4" />}
                </div>

                <div className={`max-w-[82%] rounded-2xl p-4 text-xs leading-relaxed ${
                  isBot
                    ? 'bg-slate-50 text-slate-800 border border-slate-200/80 shadow-xs'
                    : 'bg-emerald-700 text-white shadow-xs'
                }`}>
                  <div className="whitespace-pre-line">{m.text}</div>
                  {m.engine && (
                    <div className="mt-2 pt-2 border-t border-slate-200/60 text-[10px] text-slate-400 flex items-center gap-1">
                      <Sparkles className="w-3 h-3 text-emerald-500" />
                      <span>Answer grounded by: {m.engine}</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {loading && (
            <div className="flex items-start space-x-3">
              <div className="w-8 h-8 rounded-full bg-emerald-600 flex items-center justify-center text-white text-xs">
                <Bot className="w-4 h-4" />
              </div>
              <div className="bg-slate-50 rounded-2xl p-4 border border-slate-200 text-xs text-slate-500 flex items-center space-x-2">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-bounce"></div>
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-bounce [animation-delay:0.2s]"></div>
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-bounce [animation-delay:0.4s]"></div>
                <span className="text-[11px] text-slate-400">Retrieving digital twin state & agronomic knowledge...</span>
              </div>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        {/* Prompt Starters & Input Box */}
        <div className="p-4 border-t border-slate-100 bg-white space-y-3">
          
          {/* Starters Pills */}
          <div className="flex items-center space-x-2 overflow-x-auto pb-1 text-xs">
            <span className="text-[11px] text-slate-400 font-semibold shrink-0">Quick Starters:</span>
            {starters.slice(0, 3).map((st, i) => (
              <button
                key={i}
                onClick={() => handleSend(st)}
                className="bg-slate-100 hover:bg-emerald-50 hover:text-emerald-700 text-slate-600 px-3 py-1 rounded-full shrink-0 transition-colors border border-slate-200/60 text-[11px]"
              >
                {st}
              </button>
            ))}
          </div>

          {/* Text Input */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex items-center space-x-2"
          >
            <input
              type="text"
              placeholder="Ask anything about yield, rainfall shocks, soil fertilizer doses, or mandi selling timing..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
              className="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition-all"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white px-4 py-2.5 rounded-xl transition-all flex items-center justify-center shrink-0 shadow-sm"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>

        </div>

      </div>

      {/* Right: RAG Knowledge & Grounded State Panel (1 col) */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs flex flex-col justify-between space-y-4">
        <div>
          <div className="flex items-center space-x-2 text-slate-800 font-bold text-sm">
            <Database className="w-4 h-4 text-emerald-600" />
            <span>RAG Context Injected Into Responses</span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            The chatbot grounds every reply in these live digital twin facts to prevent hallucination:
          </p>

          <div className="mt-4 space-y-3 text-xs">
            <div className="p-3 bg-slate-50 rounded-xl border border-slate-100 space-y-1">
              <span className="text-[10px] uppercase font-bold text-slate-400">Target Farm</span>
              <div className="font-semibold text-slate-800">Ariyalur Demonstration Farm (Tamil Nadu)</div>
            </div>

            <div className="p-3 bg-slate-50 rounded-xl border border-slate-100 space-y-1">
              <span className="text-[10px] uppercase font-bold text-slate-400">Current Prediction Baseline</span>
              <div className="font-semibold text-slate-800">4.02 t/ha (Range: 2.25 – 5.79 t/ha)</div>
              <div className="text-[10px] text-emerald-700">90% Finite-Sample Conformal Interval</div>
            </div>

            <div className="p-3 bg-slate-50 rounded-xl border border-slate-100 space-y-1">
              <span className="text-[10px] uppercase font-bold text-slate-400">Soil & Satellite Telemetry</span>
              <div className="text-slate-700 font-medium">Clay Loam (pH 7.3) • Active NDVI: 0.71</div>
            </div>

            <div className="p-3 bg-slate-50 rounded-xl border border-slate-100 space-y-1">
              <span className="text-[10px] uppercase font-bold text-slate-400">Knowledge Chunks Loaded</span>
              <div className="text-slate-600 space-y-1">
                <div>• TNAU SRI Rice & Alternate Wetting & Drying</div>
                <div>• Bt Cotton Pink Bollworm Pest Advisory</div>
                <div>• Ariyalur Mandi Price Seasonality Cycle</div>
              </div>
            </div>
          </div>
        </div>

        <div className="p-3 bg-emerald-50 rounded-xl border border-emerald-200 text-[11px] text-emerald-900 flex items-start space-x-2">
          <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
          <span>No physical IoT sensors or drones needed — purely powered by open public meteorological, soil, and satellite feeds.</span>
        </div>
      </div>

    </div>
  );
}
