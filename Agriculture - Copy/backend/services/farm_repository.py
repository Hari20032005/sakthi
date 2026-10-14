"""Persistent farm and digital-twin snapshot storage for the academic demo.

This deliberately uses SQLite so the project runs without requiring a managed
database.  The interface is small enough to replace with PostGIS later.
"""
import json
import sqlite3
import hashlib
from datetime import datetime, timezone

from backend.config import SQLITE_DB_PATH


INITIAL_FARMS = [
    {
        "farm_id": 1, "owner_id": 1, "owner_name": "Demo Farmer",
        "farm_name": "Ariyalur Main Rice Farm", "latitude": 11.137,
        "longitude": 79.078, "district": "Ariyalur", "state": "Tamil Nadu",
        "size_hectares": 5.0, "soil_type": "Clay loam", "primary_crop": "Rice",
        "current_season": "Kharif", "sowing_date": "2026-06-15",
    },
    {
        "farm_id": 2, "owner_id": 1, "owner_name": "Demo Farmer",
        "farm_name": "Ariyalur South Cotton Block", "latitude": 11.112,
        "longitude": 79.055, "district": "Ariyalur", "state": "Tamil Nadu",
        "size_hectares": 3.2, "soil_type": "Black Cotton Soil", "primary_crop": "Cotton(lint)",
        "current_season": "Rabi", "sowing_date": "2026-09-01",
    },
    {
        "farm_id": 3, "owner_id": 2, "owner_name": "Sendurai Farmers Collective",
        "farm_name": "Sendurai Cooperative Cluster", "latitude": 11.233,
        "longitude": 79.182, "district": "Ariyalur", "state": "Tamil Nadu",
        "size_hectares": 12.5, "soil_type": "Clay loam", "primary_crop": "Rice",
        "current_season": "Kharif", "sowing_date": "2026-06-20",
    },
]


class FarmRepository:
    def _connection(self):
        conn = sqlite3.connect(str(SQLITE_DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self):
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS twin_farms (
                    farm_id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL,
                    owner_name TEXT NOT NULL, farm_name TEXT NOT NULL,
                    latitude REAL NOT NULL, longitude REAL NOT NULL, district TEXT NOT NULL,
                    state TEXT NOT NULL, size_hectares REAL NOT NULL, soil_type TEXT NOT NULL,
                    primary_crop TEXT NOT NULL, current_season TEXT NOT NULL, sowing_date TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS twin_snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT, farm_id INTEGER NOT NULL,
                    generated_at TEXT NOT NULL, state_version TEXT NOT NULL, payload_json TEXT NOT NULL,
                    state_hash TEXT,
                    FOREIGN KEY(farm_id) REFERENCES twin_farms(farm_id)
                )
            """)
            snapshot_columns = {row[1] for row in conn.execute("PRAGMA table_info(twin_snapshots)")}
            if "state_hash" not in snapshot_columns:
                conn.execute("ALTER TABLE twin_snapshots ADD COLUMN state_hash TEXT")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ndvi_observations (
                    observation_id INTEGER PRIMARY KEY AUTOINCREMENT, farm_id INTEGER NOT NULL,
                    observation_date TEXT NOT NULL, ndvi REAL NOT NULL,
                    valid_pixel_pct REAL NOT NULL, source TEXT NOT NULL,
                    fetched_at TEXT NOT NULL, UNIQUE(farm_id, observation_date, source),
                    FOREIGN KEY(farm_id) REFERENCES twin_farms(farm_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS management_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT, farm_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL, label TEXT NOT NULL, details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(farm_id) REFERENCES twin_farms(farm_id)
                )
            """)
            if conn.execute("SELECT COUNT(*) FROM twin_farms").fetchone()[0] == 0:
                columns = ", ".join(INITIAL_FARMS[0].keys())
                placeholders = ", ".join("?" for _ in INITIAL_FARMS[0])
                conn.executemany(
                    f"INSERT INTO twin_farms ({columns}) VALUES ({placeholders})",
                    [tuple(f.values()) for f in INITIAL_FARMS],
                )

    def list_farms(self):
        self.initialize()
        with self._connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM twin_farms ORDER BY farm_id")]

    def get_farm(self, farm_id):
        self.initialize()
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM twin_farms WHERE farm_id = ?", (farm_id,)).fetchone()
            return dict(row) if row else None

    def create_farm(self, farm):
        self.initialize()
        fields = [key for key in INITIAL_FARMS[0] if key != "farm_id"]
        with self._connection() as conn:
            cursor = conn.execute(
                f"INSERT INTO twin_farms ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
                tuple(farm.get(key) for key in fields),
            )
        return self.get_farm(cursor.lastrowid)

    @staticmethod
    def _state_hash(payload):
        """Hash only meaningful state; refresh timestamps must not create history."""
        comparable = json.loads(json.dumps(payload))
        comparable.get("digital_twin_status", {}).pop("last_sync", None)
        comparable.pop("twin_state", None)
        encoded = json.dumps(comparable, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def save_snapshot(self, farm_id, payload, state_version="1.0"):
        self.initialize()
        generated_at = datetime.now(timezone.utc).isoformat()
        state_hash = self._state_hash(payload)
        with self._connection() as conn:
            latest = conn.execute(
                "SELECT snapshot_id, generated_at, state_version, state_hash, payload_json FROM twin_snapshots WHERE farm_id = ? ORDER BY snapshot_id DESC LIMIT 1",
                (farm_id,),
            ).fetchone()
            if latest:
                latest_hash = latest["state_hash"] or self._state_hash(json.loads(latest["payload_json"]))
                same_day = latest["generated_at"][:10] == generated_at[:10]
                if latest_hash == state_hash and same_day:
                    return {
                        "snapshot_id": latest["snapshot_id"], "generated_at": latest["generated_at"],
                        "state_version": latest["state_version"], "created": False,
                    }
            cursor = conn.execute(
                "INSERT INTO twin_snapshots (farm_id, generated_at, state_version, payload_json, state_hash) VALUES (?, ?, ?, ?, ?)",
                (farm_id, generated_at, state_version, json.dumps(payload), state_hash),
            )
        return {"snapshot_id": cursor.lastrowid, "generated_at": generated_at, "state_version": state_version, "created": True}

    def recent_snapshots(self, farm_id, limit=10):
        self.initialize()
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT snapshot_id, generated_at, state_version, state_hash, payload_json FROM twin_snapshots WHERE farm_id = ? ORDER BY snapshot_id DESC",
                (farm_id,),
            ).fetchall()
        # Hide legacy duplicate refreshes from the academic timeline without
        # deleting historical records created by earlier project versions.
        unique, seen = [], set()
        for row in rows:
            item = dict(row)
            fingerprint = item["state_hash"] or self._state_hash(json.loads(item["payload_json"]))
            day = item["generated_at"][:10]
            key = (day, fingerprint)
            if key not in seen:
                seen.add(key)
                unique.append({key: item[key] for key in ("snapshot_id", "generated_at", "state_version")})
            if len(unique) >= limit:
                break
        return unique

    def get_ndvi_observations(self, farm_id, limit=12):
        self.initialize()
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT observation_date, ndvi, valid_pixel_pct, source, fetched_at FROM ndvi_observations WHERE farm_id = ? ORDER BY observation_date DESC LIMIT ?",
                (farm_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def save_ndvi_observations(self, farm_id, observations):
        if not observations:
            return
        self.initialize()
        fetched_at = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO ndvi_observations (farm_id, observation_date, ndvi, valid_pixel_pct, source, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
                [(farm_id, o["date"], o["ndvi"], o["valid_pixel_pct"], o["source"], fetched_at) for o in observations],
            )

    def log_management_event(self, farm_id, event_type, label, details=None):
        self.initialize()
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            cursor = conn.execute(
                "INSERT INTO management_events (farm_id, event_type, label, details_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (farm_id, event_type, label, json.dumps(details or {}), created_at),
            )
        return {"event_id": cursor.lastrowid, "event_type": event_type, "label": label, "created_at": created_at}

    def recent_management_events(self, farm_id, limit=5):
        self.initialize()
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT event_id, event_type, label, details_json, created_at FROM management_events WHERE farm_id = ? ORDER BY event_id DESC LIMIT ?",
                (farm_id, limit),
            ).fetchall()
        return [{**dict(row), "details": json.loads(row["details_json"])} for row in rows]


farm_repository = FarmRepository()
