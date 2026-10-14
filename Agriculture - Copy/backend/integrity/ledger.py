"""Replay-sufficient, hash-chained inference ledger.

Existing reproducibility tooling records *references* to inputs: which dataset
path, which model run, which experiment. That supports re-running a pipeline.
It does not support reproducing a published result, because the upstream data
has moved on -- the reference now resolves to different bytes.

The property claimed here is **replay sufficiency**: an entry carries the
canonicalised input *values* and a digest of each external source response, so
that ``replay(entry)`` reproduces the stored output bit-identically without
querying any external service. Entries are chained, so a silent edit to entry
*n* invalidates every subsequent chain head.

The chain is tamper-*evident*, not tamper-*proof*: anyone able to rewrite every
record can recompute a self-consistent chain. Binding the chain head to an
external anchor is out of scope and is stated as such.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

GENESIS = "0" * 64

#: Bumped whenever the correction or calibration arithmetic changes. Stored in
#: every entry so a replay can refuse to run against a different code version.
ENGINE_VERSION = "1.0.0"


def canonical_json(payload: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace, fixed float precision."""

    def normalise(obj: Any) -> Any:
        if isinstance(obj, float):
            if obj != obj or obj in (float("inf"), float("-inf")):
                return None
            return format(round(obj, 9), ".9f")
        if isinstance(obj, dict):
            return {str(k): normalise(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
        if isinstance(obj, (list, tuple)):
            return [normalise(v) for v in obj]
        if isinstance(obj, (set, frozenset)):
            return sorted(str(v) for v in obj)
        return obj

    return json.dumps(normalise(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass
class LedgerEntry:
    """One inference, recorded so that it can be reproduced without refetching."""

    inference_id: str
    engine_version: str
    base_model_version: str
    base_prediction: float
    input_values: Dict[str, Any]
    provenance: List[Dict[str, Any]]
    provenance_digest: str
    thermal_time: Dict[str, Any]
    anomaly_vector: Dict[str, Any]
    forecast_weights: Dict[str, Any]
    vegetation: Dict[str, Any]
    conflict: Dict[str, Any]
    correction_components: Dict[str, Any]
    correction_bounds: Dict[str, float]
    total_correction: float
    calibration_selection: Dict[str, Any]
    corrected_prediction: float
    interval_lower: float
    interval_upper: float
    created_at: str
    previous_hash: str = GENESIS
    entry_hash: str = ""

    def _committed_payload(self) -> Dict[str, Any]:
        """Everything bound into the entry hash.

        ``created_at`` is deliberately excluded: a chain that commits a
        timestamp cannot be verified by a third party who did not witness the
        clock, and including it would let an entry be edited to shift apparent
        ordering without changing any computation.
        """

        payload = dict(self.__dict__)
        payload.pop("entry_hash", None)
        payload.pop("created_at", None)
        return payload

    def seal(self) -> "LedgerEntry":
        self.entry_hash = digest(self._committed_payload())
        return self

    def verify_seal(self) -> bool:
        return self.entry_hash == digest(self._committed_payload())

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LedgerEntry":
        allowed = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclass
class InferenceLedger:
    """Append-only chain of :class:`LedgerEntry` objects."""

    entries: List[LedgerEntry] = field(default_factory=list)

    @property
    def head(self) -> str:
        return self.entries[-1].entry_hash if self.entries else GENESIS

    def append(self, entry: LedgerEntry) -> LedgerEntry:
        entry.previous_hash = self.head
        entry.seal()
        self.entries.append(entry)
        return entry

    def verify(self) -> Dict[str, Any]:
        """Recompute the chain end to end."""

        problems: List[str] = []
        previous = GENESIS
        for i, entry in enumerate(self.entries):
            if entry.previous_hash != previous:
                problems.append(f"entry {i}: previous_hash does not chain")
            if not entry.verify_seal():
                problems.append(f"entry {i}: payload does not match entry_hash")
            previous = entry.entry_hash
        return {
            "ok": not problems,
            "n_entries": len(self.entries),
            "head": self.head,
            "problems": problems,
        }


class ReplayError(RuntimeError):
    pass


def replay(entry: LedgerEntry, compute) -> Dict[str, Any]:
    """Re-run a pure computation from an entry and check it reproduces the output.

    ``compute`` receives the entry and must return a mapping containing at least
    ``corrected_prediction``, ``interval_lower`` and ``interval_upper``.

    Raises :class:`ReplayError` if the engine version differs, because a replay
    against changed arithmetic is not a reproduction.
    """

    if entry.engine_version != ENGINE_VERSION:
        raise ReplayError(
            f"entry was produced by engine version {entry.engine_version!r}; "
            f"this replay is {ENGINE_VERSION!r}. Reproduction is not claimed across versions."
        )
    if not entry.verify_seal():
        raise ReplayError("entry hash does not match its payload; the record has been altered")

    result = compute(entry)

    mismatches: List[str] = []
    for field_name in ("corrected_prediction", "interval_lower", "interval_upper"):
        stored = getattr(entry, field_name)
        recomputed = float(result[field_name])
        if round(float(stored), 9) != round(recomputed, 9):
            mismatches.append(f"{field_name}: stored {stored!r} vs replayed {recomputed!r}")

    return {
        "reproduced": not mismatches,
        "stored_output_digest": digest(
            {
                "corrected_prediction": entry.corrected_prediction,
                "interval_lower": entry.interval_lower,
                "interval_upper": entry.interval_upper,
            }
        ),
        "replayed_output_digest": digest(
            {
                "corrected_prediction": float(result["corrected_prediction"]),
                "interval_lower": float(result["interval_lower"]),
                "interval_upper": float(result["interval_upper"]),
            }
        ),
        "mismatches": mismatches,
        "engine_version": entry.engine_version,
    }


def provenance_digest_from_records(records: List[Dict[str, Any]]) -> str:
    return digest(records)


def optional(value: Optional[Any]) -> Any:
    return None if value is None else value
