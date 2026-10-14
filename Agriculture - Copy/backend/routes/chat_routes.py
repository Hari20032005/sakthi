from flask import Blueprint, request, jsonify
from backend.services.rag_chatbot import rag_chatbot_service
from backend.db import execute_query

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")

CHAT_HISTORY = []

PROMPT_STARTERS = [
    "Why is my rice yield forecasted at this number?",
    "How should I irrigate my farm under the current dry spell?",
    "When is the best time to sell my crop at the Ariyalur mandi?",
    "What will happen if rainfall decreases by 30% this season?",
    "How does my soil pH and clay profile affect my fertilizer doses?",
    "Should I switch from Rice to Cotton for next season?"
]

@chat_bp.route("/message", methods=["POST"])
def send_message():
    data = request.get_json() or {}
    message = data.get("message", "").strip()
    farm_id = int(data.get("farm_id", 1))

    if not message:
        return jsonify({"success": False, "error": "Message cannot be empty"}), 400

    # Generate grounded RAG response
    response_data = rag_chatbot_service.generate_response(user_query=message, farm_id=farm_id)

    chat_entry = {
        "id": len(CHAT_HISTORY) + 1,
        "sender": "farmer",
        "message": message,
        "bot_reply": response_data["reply"],
        "engine": response_data["engine"],
        "grounded_context": response_data["grounded_context"]
    }
    CHAT_HISTORY.append(chat_entry)

    # Attempt to log to Postgres chat_messages if available
    try:
        execute_query(
            "INSERT INTO chat_messages (session_id, sender, message_text) VALUES (%s, %s, %s)",
            (1, "farmer", message), commit=True
        )
        execute_query(
            "INSERT INTO chat_messages (session_id, sender, message_text) VALUES (%s, %s, %s)",
            (1, "bot", response_data["reply"]), commit=True
        )
    except Exception:
        pass

    return jsonify({
        "success": True,
        "reply": response_data["reply"],
        "engine": response_data["engine"],
        "grounded_context": response_data["grounded_context"]
    })

@chat_bp.route("/history", methods=["GET"])
def get_history():
    return jsonify({
        "success": True,
        "history": CHAT_HISTORY
    })

@chat_bp.route("/starters", methods=["GET"])
def get_starters():
    return jsonify({
        "success": True,
        "prompt_starters": PROMPT_STARTERS
    })
