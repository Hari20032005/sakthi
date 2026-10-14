"""Endpoints for the provenance-calibrated inference integrity engine.

These expose the engine described in the invention disclosure. They sit beside
the existing forecast routes rather than replacing them: the plain yield
endpoint keeps its current contract, and this one reports the calibrated
estimate together with the provenance of every input that produced it.
"""

from __future__ import annotations

import pandas as pd
from flask import Blueprint, jsonify, request

from backend.models.yield_model import yield_forecaster
from backend.services.integrity_service import (
    CALIBRATION_ARTEFACT,
    CalibrationArtefactMissing,
    integrity_service,
)
from backend.services.weather_service import weather_service
from backend.integrity.provenance import SourceCategory
from backend.integrity.vegetation import LadderSample

integrity_bp = Blueprint("integrity", __name__, url_prefix="/api/integrity")

_SEASON_RANGES = {
    "Kharif": lambda y: (f"{y}-06-01", f"{y}-10-31"),
    "Rabi": lambda y: (f"{y}-11-01", f"{y+1}-03-31"),
    "Whole Year": lambda y: (f"{y}-01-01", f"{y}-12-31"),
    "Summer": lambda y: (f"{y}-03-01", f"{y}-06-15"),
    "Autumn": lambda y: (f"{y}-08-01", f"{y}-11-30"),
    "Winter": lambda y: (f"{y}-11-01", f"{y+1}-02-28"),
}


def _archive_window(crop, season, crop_year, fraction=0.55):
    """Season-to-date window from the station archive, for the worked path."""

    archive = integrity_service.archive
    if season not in _SEASON_RANGES:
        raise ValueError(f"unsupported season {season!r}")
    start, end = _SEASON_RANGES[season](int(crop_year))
    window = archive[(archive["date"] >= start) & (archive["date"] <= end)].reset_index(drop=True)
    if window.empty:
        raise ValueError(f"no archive coverage for {crop} {season} {crop_year}")
    cut = max(1, int(round(len(window) * fraction)))
    return window.iloc[:cut].copy(), window.iloc[cut:].head(7).copy()


@integrity_bp.route("/calibrated-yield", methods=["POST"])
def calibrated_yield():
    """Provenance-conditioned prediction for one crop-season.

    Body: {crop, season, crop_year?, radius_ladder?, vegetation_deviation?,
           valid_pixel_pct?, weather_category?}
    """

    data = request.get_json() or {}
    crop = data.get("crop", "Rice")
    season = data.get("season", "Kharif")
    try:
        crop_year = int(data.get("crop_year") or _default_year(season))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "crop_year must be an integer"}), 400

    try:
        observed, forecast = _archive_window(crop, season, crop_year)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    category = SourceCategory.parse(data.get("weather_category", "live"))

    base = yield_forecaster.predict(crop, season)
    ladder_payload = data.get("radius_ladder")
    ladder = None
    if isinstance(ladder_payload, list) and len(ladder_payload) >= 3:
        try:
            ladder = [
                LadderSample(
                    radius_m=int(item["radius_m"]),
                    ndvi=float(item["ndvi"]),
                    valid_pixel_pct=float(item.get("valid_pixel_pct", 0.0)),
                )
                for item in ladder_payload
            ]
        except (KeyError, TypeError, ValueError):
            ladder = None

    try:
        state = integrity_service.build_state(
            crop=crop,
            season=season,
            base_prediction=base["predicted_yield_t_per_ha"],
            base_model_version="rf-100-fixed",
            observed_daily=observed,
            forecast_daily=forecast,
            weather_category=category,
            weather_age_days=float(len(forecast)),
            forecast_horizon_days=len(forecast),
            vegetation_deviation=data.get("vegetation_deviation"),
            ladder_samples=ladder,
            valid_pixel_pct=data.get("valid_pixel_pct"),
            vegetation_age_days=data.get("vegetation_age_days"),
        )
        result = integrity_service.infer(state)
    except CalibrationArtefactMissing as exc:
        return jsonify({
            "success": False,
            "error": "calibration_artifact_missing",
            "detail": str(exc),
            "remedy": "python3 -m backend.validation.experiments",
        }), 503
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "error": type(exc).__name__, "detail": str(exc)}), 500

    return jsonify({
        "success": True,
        "baseline_forecast": {
            "predicted_yield_t_per_ha": base["predicted_yield_t_per_ha"],
            "conformal_interval": base["conformal_interval"],
            "note": "One pooled margin applied to every crop, season and input quality.",
        },
        "provenance_calibrated": result,
        "baseline_metrics": yield_forecaster.loocv_metrics,
    })


@integrity_bp.route("/ledger", methods=["GET"])
def ledger_status():
    return jsonify({
        "success": True,
        "chain": integrity_service.chain_status(),
        "calibration_artifact": str(CALIBRATION_ARTEFACT),
        "calibration_artifact_present": CALIBRATION_ARTEFACT.exists(),
    })


@integrity_bp.route("/sources", methods=["GET"])
def source_classes():
    """The provenance taxonomy, for clients that need to label an input."""

    return jsonify({
        "success": True,
        "categories": [
            {"value": c.label, "severity": int(c), "is_observation": c is SourceCategory.LIVE}
            for c in SourceCategory
        ],
        "conflict_codes": [
            "NONE",
            "WEATHER_STRESS_NDVI_NORMAL",
            "NDVI_DECLINE_WEATHER_NORMAL",
            "LOW_QUALITY_NDVI",
            "FALLBACK_WEATHER_HIGH_VEGETATION_UNCERTAINTY",
            "INSUFFICIENT_MULTI_SOURCE_EVIDENCE",
            "SOURCE_TIMESTAMP_MISMATCH",
        ],
    })


def _default_year(season):
    from datetime import date

    today = date.today()
    if season == "Kharif":
        return today.year if today.month >= 6 else today.year - 1
    if season == "Rabi":
        return today.year if today.month >= 11 else today.year - 1
    return today.year
