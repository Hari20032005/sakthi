import sys
from pathlib import Path
import werkzeug

# Fix for Flask 2.2.5 compatibility with Werkzeug 3.x
if not hasattr(werkzeug, "__version__"):
    try:
        import importlib.metadata
        werkzeug.__version__ = importlib.metadata.version("werkzeug")
    except Exception:
        werkzeug.__version__ = "3.1.3"

# Ensure root workspace is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, jsonify
from flask_cors import CORS
from backend.config import API_PORT, API_HOST
from backend.routes.auth_routes import auth_bp
from backend.routes.farm_routes import farm_bp
from backend.routes.forecast_routes import forecast_bp
from backend.routes.scenario_routes import scenario_bp
from backend.routes.explain_routes import explain_bp
from backend.routes.chat_routes import chat_bp
from backend.routes.cooperative_routes import cooperative_bp
from backend.routes.recommendation_routes import recommendation_bp
from backend.routes.integrity_routes import integrity_bp

def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(farm_bp)
    app.register_blueprint(forecast_bp)
    app.register_blueprint(scenario_bp)
    app.register_blueprint(explain_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(cooperative_bp)
    app.register_blueprint(recommendation_bp)
    app.register_blueprint(integrity_bp)

    @app.route("/api/health", methods=["GET"])
    def health_check():
        return jsonify({
            "status": "healthy",
            "service": "Sensor-Free Agriculture Digital Twin API",
            "version": "1.0.0",
            "region": "Ariyalur, Tamil Nadu",
            "public_data_sources": [
                "Open-Meteo & NOAA Weather",
                "ISRIC SoilGrids 250m",
                "Sentinel-2 / MODIS NDVI",
                "APY Yield Records",
                "Agmarknet Mandi Prices"
            ]
        })

    return app

app = create_app()

if __name__ == "__main__":
    print(f"Starting Agriculture Digital Twin API on http://localhost:{API_PORT} ...")
    app.run(host=API_HOST, port=API_PORT, debug=True)
