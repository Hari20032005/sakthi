import subprocess
import sys
import time
import os
import signal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def run():
    print("=" * 65)
    print("  🌾 AGRICULTURE DIGITAL TWIN (SENSOR-FREE) LAUNCHER 🌾")
    print("=" * 65)
    print("Starting Backend API (Flask) on http://localhost:5000 ...")
    backend_proc = subprocess.Popen(
        [sys.executable, "backend/app.py"],
        cwd=str(BASE_DIR)
    )

    time.sleep(2)

    print("Starting Frontend Dashboard (React + Vite) on http://localhost:5173 ...")
    npm_cmd = "npm.cmd" if sys.platform.startswith("win") else "npm"
    frontend_proc = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=str(BASE_DIR / "frontend")
    )

    print("\n" + "=" * 65)
    print("🚀 DIGITAL TWIN IS RUNNING!")
    print("👉 Open Dashboard:  http://localhost:5173")
    print("👉 Backend API Docs: http://localhost:5000/api/health")
    print("Press Ctrl+C in this terminal to stop both servers.")
    print("=" * 65 + "\n")

    try:
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None:
                print("Backend server stopped.")
                break
            if frontend_proc.poll() is not None:
                print("Frontend server stopped.")
                break
    except KeyboardInterrupt:
        print("\nShutting down servers...")
    finally:
        try:
            if backend_proc.poll() is None:
                backend_proc.terminate()
            if frontend_proc.poll() is None:
                frontend_proc.terminate()
        except Exception:
            pass
        print("Done. Goodbye!")

if __name__ == "__main__":
    run()
