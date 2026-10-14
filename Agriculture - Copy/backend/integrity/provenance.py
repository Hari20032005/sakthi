"""Machine-readable provenance records for every external input source.

The existing twin state carries only a free-text ``source`` string per layer
(``weather_service.py:42``, ``soil_service.py:38``, ``satellite_service.py:83``).
That string is not machine-comparable, does not carry retrieval time, and
cannot be hashed, so downstream code cannot tell a live observation from a
climatology substitute except by string comparison.

``SourceRecord`` replaces that string with a structured, hashable object, and
``ProvenanceLedger`` collects the records for one inference into a canonical,
deterministically serialisable form.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Dict, List, Optional


class SourceCategory(IntEnum):
    """Ordered by degradation severity.

    The ordinal value is load-bearing: it is used to rank provenance states
    when resolving calibration backoff, so reordering these members changes
    behaviour.
    """

    LIVE = 0
    CACHED = 1
    FORECAST = 2
    HISTORICAL_FALLBACK = 3
    PROXY = 4

    @property
    def label(self) -> str:
        return self.name.lower()

    @classmethod
    def parse(cls, value: Any) -> "SourceCategory":
        if isinstance(value, SourceCategory):
            return value
        if isinstance(value, int):
            return cls(value)
        text = str(value).strip().lower()
        for member in cls:
            if member.label == text:
                return member
        aliases = {
            "open-meteo historical weather api": cls.LIVE,
            "open-meteo live api": cls.LIVE,
            "cached noaa/open-meteo": cls.CACHED,
            "cached sensor-free public weather": cls.CACHED,
            "system baseline": cls.CACHED,
            "historical ariyalur climatology fallback": cls.HISTORICAL_FALLBACK,
            "weather accumulation unavailable": cls.HISTORICAL_FALLBACK,
            "academic phenology proxy (sentinel-2 connector pending)": cls.PROXY,
            "modelled_proxy": cls.PROXY,
        }
        if text in aliases:
            return aliases[text]
        raise ValueError(f"unknown source category: {value!r}")


def response_digest(payload: Any) -> str:
    """SHA-256 over a canonical JSON encoding of a retrieved source response.

    Canonical means sorted keys, no insignificant whitespace, and floats
    rounded to a fixed number of decimals, so that two retrievals of the same
    logical response digest identically even if the serialiser emits different
    key order or trailing zeros.
    """

    def normalise(obj: Any) -> Any:
        if isinstance(obj, float):
            return round(obj, 9)
        if isinstance(obj, dict):
            return {str(k): normalise(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
        if isinstance(obj, (list, tuple)):
            return [normalise(v) for v in obj]
        return obj

    blob = json.dumps(normalise(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class SourceRecord:
    """One retrieval from one external source."""

    source_id: str
    category: SourceCategory
    acquired_at: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    data_age_hours: float = 0.0
    forecast_horizon_days: Optional[int] = None
    missing_treatment: str = "none"
    radius_m: Optional[float] = None
    cloud_pct: Optional[float] = None
    valid_pixel_pct: Optional[float] = None
    version: Optional[str] = None
    response_digest: Optional[str] = None

    def __post_init__(self) -> None:
        if self.response_digest is None:
            self.response_digest = response_digest(self.to_payload())
        self.acquired_at = str(self.acquired_at)

    def to_payload(self) -> Dict[str, Any]:
        """The retrieved content, as opposed to the metadata about it."""

        return {
            "source_id": self.source_id,
            "lat": self.lat,
            "lon": self.lon,
            "radius_m": self.radius_m,
            "cloud_pct": self.cloud_pct,
            "valid_pixel_pct": self.valid_pixel_pct,
        }

    def to_canonical_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "category": int(self.category),
            "category_label": self.category.label,
            "acquired_at": self.acquired_at,
            "lat": self.lat,
            "lon": self.lon,
            "data_age_hours": round(float(self.data_age_hours), 6),
            "forecast_horizon_days": self.forecast_horizon_days,
            "missing_treatment": self.missing_treatment,
            "radius_m": self.radius_m,
            "cloud_pct": self.cloud_pct,
            "valid_pixel_pct": self.valid_pixel_pct,
            "version": self.version,
            "response_digest": self.response_digest,
        }

    @property
    def is_live_observation(self) -> bool:
        return self.category is SourceCategory.LIVE


@dataclass
class ProvenanceLedger:
    """All source records participating in a single inference."""

    records: Dict[str, SourceRecord] = field(default_factory=dict)

    def record(self, record: SourceRecord) -> SourceRecord:
        self.records[record.source_id] = record
        return record

    def get(self, source_id: str) -> Optional[SourceRecord]:
        return self.records.get(source_id)

    def require(self, source_id: str) -> SourceRecord:
        record = self.records.get(source_id)
        if record is None:
            raise KeyError(f"no provenance record for source_id={source_id!r}")
        return record

    @property
    def worst_category(self) -> SourceCategory:
        if not self.records:
            return SourceCategory.PROXY
        return max(self.records.values(), key=lambda r: int(r.category)).category

    def to_canonical_list(self) -> List[Dict[str, Any]]:
        return [self.records[k].to_canonical_dict() for k in sorted(self.records)]

    def digest(self) -> str:
        return response_digest(self.to_canonical_list())

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
