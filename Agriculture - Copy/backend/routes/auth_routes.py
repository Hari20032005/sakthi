from flask import Blueprint, request, jsonify
from backend.db import execute_query

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# In-memory session store for demo simplicity (alongside database user table)
DEMO_USERS = {
    "farmer@example.com": {
        "id": 1,
        "name": "Demo Farmer",
        "email": "farmer@example.com",
        "role": "farmer",
        "contact_number": "9840000000",
        "farm_id": 1
    },
    "coop@example.com": {
        "id": 2,
        "name": "Ariyalur Farmer Producer Org",
        "email": "coop@example.com",
        "role": "cooperative_admin",
        "organization_name": "Ariyalur Agri Cooperative Society",
        "farm_id": None
    }
}

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    role = data.get("role", "farmer")

    # Match existing demo user or auto-authenticate
    if email in DEMO_USERS:
        user = DEMO_USERS[email]
    else:
        name = data.get("name", "Farmer User")
        user = {
            "id": len(DEMO_USERS) + 1,
            "name": name,
            "email": email or "farmer@example.com",
            "role": role,
            "farm_id": 1
        }

    return jsonify({
        "success": True,
        "token": f"agri-jwt-mock-{user['id']}-{user['role']}",
        "user": user
    })

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    name = data.get("name", "New Farmer")
    email = data.get("email", "").strip().lower()
    role = data.get("role", "farmer")
    contact = data.get("contact_number", "")
    org = data.get("organization_name", "")

    new_id = len(DEMO_USERS) + 1
    user = {
        "id": new_id,
        "name": name,
        "email": email or f"user{new_id}@agritwin.in",
        "role": role,
        "contact_number": contact,
        "organization_name": org,
        "farm_id": 1
    }
    DEMO_USERS[user["email"]] = user

    try:
        execute_query(
            "INSERT INTO users (name, role, contact_number, organization_name) VALUES (%s, %s, %s, %s)",
            (name, role, contact, org), commit=True
        )
    except Exception:
        pass

    return jsonify({
        "success": True,
        "token": f"agri-jwt-mock-{new_id}-{role}",
        "user": user
    })

@auth_bp.route("/me", methods=["GET"])
def me():
    # Return default demo farmer
    return jsonify({
        "success": True,
        "user": DEMO_USERS["farmer@example.com"]
    })
