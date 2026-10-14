"""Provenance-calibrated predictive inference integrity engine.

The package is deliberately free of agriculture-specific vocabulary at its
interface: it operates on a fixed base predictor plus dated daily series and
vegetation observations. ``backend/validation`` supplies the crop-yield domain
as one application.
"""

from backend.integrity.provenance import ProvenanceLedger, SourceCategory, SourceRecord
from backend.integrity.calibration import CalibrationStore, PooledBaselineStore, QualityKey, conformal_quantile
from backend.integrity.conflict import ConflictCode, ConflictResult
from backend.integrity.engine import (
    ANOMALY_FIELDS,
    CorrectionModel,
    InferenceState,
    IntegrityEngine,
    IntegrityResult,
    fit_correction_model,
)
from backend.integrity.ledger import ENGINE_VERSION, InferenceLedger, LedgerEntry, ReplayError, replay
from backend.integrity.thermal_time import ThermalExpectation, horizon_weight, persistence_skill_curve
from backend.integrity.vegetation import LadderSample, SupportStability, ndvi_quality_band, support_stability

__all__ = [
    "ANOMALY_FIELDS",
    "CalibrationStore",
    "ConflictCode",
    "ConflictResult",
    "CorrectionModel",
    "ENGINE_VERSION",
    "InferenceLedger",
    "InferenceState",
    "IntegrityEngine",
    "IntegrityResult",
    "LadderSample",
    "LedgerEntry",
    "PooledBaselineStore",
    "ProvenanceLedger",
    "QualityKey",
    "ReplayError",
    "SourceCategory",
    "SourceRecord",
    "SupportStability",
    "ThermalExpectation",
    "conformal_quantile",
    "fit_correction_model",
    "horizon_weight",
    "ndvi_quality_band",
    "persistence_skill_curve",
    "replay",
    "support_stability",
]
