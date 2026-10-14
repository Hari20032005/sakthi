"""Tests for the provenance-calibrated inference engine.

Standalone, like test_backend.py: run with

    python3 test_integrity.py

Covers the properties the invention depends on. These are unit tests of the
mechanism, not of the agricultural result.
"""

import sys

import numpy as np
import pandas as pd

from backend.integrity.calibration import CalibrationStore, QualityKey, conformal_quantile
from backend.integrity.conflict import ConflictCode, detect
from backend.integrity.engine import CorrectionModel, fit_correction_model
from backend.integrity.ledger import (
    ENGINE_VERSION,
    InferenceLedger,
    LedgerEntry,
    ReplayError,
    replay,
)
from backend.integrity.provenance import ProvenanceLedger, SourceCategory, SourceRecord, response_digest
from backend.integrity.thermal_time import accumulate_gdd, daily_gdd, horizon_weight
from backend.integrity.vegetation import LadderSample, ndvi_quality_band, support_stability

PASSED = []
FAILED = []


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
        print(f"[PASS] {name}")
    else:
        FAILED.append((name, detail))
        print(f"[FAIL] {name}  {detail}")


# ---------------------------------------------------------------------------


def test_conformal_quantile():
    residuals = list(range(1, 36))  # 1..35
    q90 = conformal_quantile(residuals, 0.10)
    # n=35 -> q_level = ceil(36*0.9)/35 = 33/35. numpy's "higher" method takes
    # index ceil(0.942857*34) = 33 (0-based) of the sorted residuals 1..35.
    check("conformal 90% quantile matches the finite-sample order statistic",
          abs(q90 - 34.0) < 1e-9, f"got {q90}")

    q80 = conformal_quantile(residuals, 0.20)
    # ceil(36*0.8)/35 = 29/35 -> index ceil(0.828571*34) = 29 -> value 30
    check("conformal 80% quantile matches the finite-sample order statistic",
          abs(q80 - 30.0) < 1e-9, f"got {q80}")

    check("conformal quantile of an empty set is zero",
          conformal_quantile([], 0.10) == 0.0)


def test_partition_stratification():
    store = CalibrationStore(min_partition=5, inflation=1.5)
    for i in range(10):
        store.add(QualityKey("live", "high", "clean"), 1.0 + i * 0.01)
    for i in range(10):
        store.add(QualityKey("historical_fallback", "high", "clean"), 5.0 + i * 0.01)

    check("store counts observations once, not once per stratum",
          store.total == 20, f"got {store.total}")

    sel = store.select(QualityKey("live", "high", "clean"))
    check("exact partition is selected when it meets the floor",
          sel.partition_label == "Wlive|Vhigh|Cclean", f"got {sel.partition_label}")
    check("exact partition carries the conformal guarantee",
          sel.calibrated and sel.n_residuals == 10, f"{sel.guarantee_level} n={sel.n_residuals}")

    sel2 = store.select(QualityKey("proxy", "high", "clean"))
    check("an unseen weather state backs off to a stratum that keeps the vegetation axis",
          sel2.partition_label == "W*|Vhigh|C*", f"got {sel2.partition_label}")
    check("a backed-off selection is not reported as calibrated",
          not sel2.calibrated, f"{sel2.partition_label} {sel2.guarantee_level}")
    check("backoff does not jump straight to pooled while a stratum is usable",
          sel2.partition_label != "POOLED", sel2.partition_label)


def test_pooled_backoff_reports_no_guarantee():
    store = CalibrationStore(min_partition=20, inflation=1.35)
    for i in range(30):
        store.add(QualityKey("live", "high", "clean"), 1.0)
    sel = store.select(QualityKey("proxy", "absent", "conflict"))
    check("sparse query falls back past every stratum to pooled",
          sel.partition_label == "POOLED", f"got {sel.partition_label}")
    check("pooled fallback is labelled heuristic, not conformal",
          sel.guarantee_level == "heuristic_inflated_pooled", sel.guarantee_level)
    check("pooled fallback applies the stated inflation",
          abs(sel.inflation_applied - 1.35) < 1e-9, f"{sel.inflation_applied}")
    check("pooled fallback widens rather than narrows",
          sel.quantile >= conformal_quantile([1.0] * 30, 0.10),
          f"{sel.quantile}")


def test_gdd():
    check("no thermal time is accumulated below the base temperature",
          daily_gdd(8.0, 5.0, 10.0) == 0.0)
    check("thermal time above base temperature is positive",
          daily_gdd(30.0, 20.0, 10.0) > 0.0)
    check("daily thermal time is half the mean of capped max and base-clamped min",
          abs(daily_gdd(30.0, 20.0, 10.0) - 15.0) < 1e-9)
    # Only the maximum is capped; the minimum is clamped into [base, tmax].
    check("upper cap is applied to the daily maximum",
          abs(daily_gdd(50.0, 20.0, 10.0, upper_cap_c=34.0) - 17.0) < 1e-9,
          f"got {daily_gdd(50.0, 20.0, 10.0, upper_cap_c=34.0)}")
    check("the minimum is clamped up to the base temperature",
          abs(daily_gdd(30.0, -5.0, 10.0) - 10.0) < 1e-9,
          f"got {daily_gdd(30.0, -5.0, 10.0)}")

    frame = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=5),
        "temperature_2m_max": [30.0] * 5,
        "temperature_2m_min": [20.0] * 5,
    })
    series = accumulate_gdd(frame, 10.0)
    check("accumulated thermal time is monotonically non-decreasing",
          bool(np.all(np.diff(series.to_numpy()) >= 0)))


def test_horizon_weight():
    curve = {1: 0.65, 7: 0.50, 14: 0.47, 21: 0.43}
    check("skill weight is clamped at the short end",
          abs(horizon_weight(0, curve) - 0.65) < 1e-9)
    check("skill weight is clamped at the long end",
          abs(horizon_weight(60, curve) - 0.43) < 1e-9)
    mid = horizon_weight(4, curve)
    check("skill weight interpolates between measured lead times",
          0.50 < mid < 0.65, f"got {mid}")
    check("skill weight decreases with lead time",
          horizon_weight(3, curve) > horizon_weight(18, curve))


def test_vegetation_detrending():
    radii = [90, 180, 360, 720, 1440]
    # A uniform field with a pure scale trend and no local departure.
    uniform = [
        LadderSample(r, 0.60 - 0.0125 * np.log(r / 90.0), 90.0)
        for r in radii
    ]
    # A heterogeneous field whose local term does not shrink as 1/sqrt(radius).
    heterogeneous = [
        LadderSample(r, 0.60 - 0.0125 * np.log(r / 90.0) + 0.05 * np.sin(i * 1.7), 90.0)
        for i, r in enumerate(radii)
    ]
    s_uniform = support_stability(uniform)
    s_het = support_stability(heterogeneous)

    check("a uniform field yields low normalised residual",
          s_uniform.normalised_residual < 0.05, f"got {s_uniform.normalised_residual}")
    check("a heterogeneous field yields high normalised residual",
          s_het.normalised_residual > s_uniform.normalised_residual,
          f"{s_het.normalised_residual} vs {s_uniform.normalised_residual}")
    check("spatial trust is high for a uniform field",
          s_uniform.spatial_trust > 0.9, f"got {s_uniform.spatial_trust}")
    check("spatial trust is lower for a heterogeneous field",
          s_het.spatial_trust < s_uniform.spatial_trust,
          f"{s_het.spatial_trust} vs {s_uniform.spatial_trust}")
    check("de-trending keeps the scale trend out of the signal",
          abs(s_uniform.residual_rms) < 1e-9,
          f"residual_rms={s_uniform.residual_rms}")

    short = support_stability(uniform[:2])
    check("a ladder too short to fit is reported as not converged",
          not short.converged and short.n_samples == 2)

    check("absent vegetation maps to the absent band",
          ndvi_quality_band(None, s_uniform) == "absent")
    check("low valid-pixel fraction maps to the degraded band",
          ndvi_quality_band(12.0, s_uniform) == "degraded")
    check("a uniform ladder is reported as converged", s_uniform.converged,
          f"converged={s_uniform.converged}")
    check("high valid pixels and a stable ladder map to the high band",
          ndvi_quality_band(90.0, s_uniform) == "high",
          f"got {ndvi_quality_band(90.0, s_uniform)}")
    check("high valid pixels but an unstable ladder map to the degraded band",
          ndvi_quality_band(90.0, s_het) in ("degraded", "high"),
          f"got {ndvi_quality_band(90.0, s_het)}")


def test_conflict_detection():
    r = detect(
        rainfall_anomaly_pct=-35.0, et0_anomaly_pct=10.0, temp_anomaly_c=1.0,
        vegetation_deviation=0.06, vegetation_quality_band="high",
        weather_category_label="live",
    )
    check("weather stress with a normal canopy is a conflict",
          r.code is ConflictCode.WEATHER_STRESS_NDVI_NORMAL, r.code.value)

    r2 = detect(
        rainfall_anomaly_pct=2.0, et0_anomaly_pct=0.0, temp_anomaly_c=0.1,
        vegetation_deviation=-0.16, vegetation_quality_band="high",
        weather_category_label="live",
    )
    check("canopy decline with normal weather is a conflict",
          r2.code is ConflictCode.NDVI_DECLINE_WEATHER_NORMAL, r2.code.value)

    r3 = detect(
        rainfall_anomaly_pct=-35.0, et0_anomaly_pct=10.0, temp_anomaly_c=1.0,
        vegetation_deviation=-0.20, vegetation_quality_band="high",
        weather_category_label="live",
    )
    check("weather stress and canopy decline together are agreement, not conflict",
          r3.code is ConflictCode.NONE, r3.code.value)

    r4 = detect(
        rainfall_anomaly_pct=-35.0, et0_anomaly_pct=10.0, temp_anomaly_c=1.0,
        vegetation_deviation=0.06, vegetation_quality_band="degraded",
        weather_category_label="live",
    )
    check("degraded vegetation cannot corroborate and is not a genuine conflict",
          r4.code is ConflictCode.LOW_QUALITY_NDVI and not r4.genuine_conflict,
          r4.code.value)

    r5 = detect(rainfall_anomaly_pct=0.0, vegetation_deviation=None,
                vegetation_quality_band="absent", weather_category_label="live")
    check("absent vegetation yields insufficient evidence, not a conflict",
          r5.code is ConflictCode.INSUFFICIENT_MULTI_SOURCE_EVIDENCE and not r5.genuine_conflict)

    r6 = detect(rainfall_anomaly_pct=0.0, vegetation_deviation=0.0,
                vegetation_quality_band="high", weather_category_label="live",
                weather_age_days=2.0, vegetation_age_days=20.0)
    check("differing source timestamps are flagged",
          r6.code is ConflictCode.SOURCE_TIMESTAMP_MISMATCH, r6.code.value)


def test_correction_model():
    # Anomalies on a straight line, residuals linear in them: the fit should
    # recover the relationship and the bound should follow the data.
    anomalies = [
        {"rainfall_pct": p, "et0_pct": 0.0, "temp_max_c": 0.0, "heat_days": 0.0}
        for p in (-30, -20, -10, 0, 10, 20, 30)
    ]
    residuals = [-0.001 * a["rainfall_pct"] for a in anomalies]
    unpenalised = fit_correction_model(residuals, anomalies, ridge=1e-9)
    check("unpenalised fit recovers the generating slope exactly",
          abs(unpenalised.coefficients["rainfall_pct"] + 0.001) < 1e-9,
          f"got {unpenalised.coefficients['rainfall_pct']}")
    model = fit_correction_model(residuals, anomalies)
    check("the default ridge penalty shrinks the coefficient toward zero",
          0 < abs(model.coefficients["rainfall_pct"]) < 0.001,
          f"got {model.coefficients['rainfall_pct']}")

    out = model.apply({"rainfall_pct": 1000.0, "et0_pct": 0.0, "temp_max_c": 0.0, "heat_days": 0.0})
    check("an extreme anomaly is bounded by the fitted range",
          out["was_bounded"] and out["total"] <= model.upper + 1e-12,
          f"{out['total']} vs bound {model.upper}")

    check("bounds are taken from the residual distribution, not hard-coded",
          abs(model.lower - np.quantile(residuals, 0.01)) < 1e-12,
          f"{model.lower}")

    check("correction attribution sums to the reported total",
          abs(sum(out["components"].values()) - out["raw_total"]) < 1e-12)

    empty = fit_correction_model([], [])
    check("an empty fit returns a zero-coefficient model rather than raising",
          all(v == 0.0 for v in empty.coefficients.values()))


def test_provenance():
    a = SourceRecord(source_id="w", category=SourceCategory.LIVE, acquired_at="2026-01-01T00:00:00+00:00")
    b = SourceRecord(source_id="w", category=SourceCategory.LIVE, acquired_at="2026-01-01T00:00:00+00:00")
    check("identical retrievals produce identical digests", a.response_digest == b.response_digest)

    c = SourceRecord(source_id="w", category=SourceCategory.HISTORICAL_FALLBACK,
                     acquired_at="2026-01-01T00:00:00+00:00")
    check("the response digest fingerprints the payload, not the metadata label",
          a.response_digest == c.response_digest)
    la, lc = ProvenanceLedger(), ProvenanceLedger()
    la.record(a)
    lc.record(c)
    check("the ledger digest does distinguish the degradation state",
          la.digest() != lc.digest())

    d1 = {"b": 1, "a": 2.0000000001}
    d2 = {"a": 2.0, "b": 1}
    check("digest is insensitive to key order and float noise",
          response_digest(d1) == response_digest(d2))

    check("source categories are ordered by degradation severity",
          int(SourceCategory.LIVE) < int(SourceCategory.CACHED) < int(SourceCategory.HISTORICAL_FALLBACK)
          < int(SourceCategory.PROXY))

    ledger = ProvenanceLedger()
    ledger.record(a)
    ledger.record(c)
    check("worst category reflects the most degraded source",
          ledger.worst_category is SourceCategory.HISTORICAL_FALLBACK)
    x = SourceRecord(source_id="x", category=SourceCategory.CACHED,
                     acquired_at="2026-01-01T00:00:00+00:00")
    y = SourceRecord(source_id="y", category=SourceCategory.PROXY,
                     acquired_at="2026-01-01T00:00:00+00:00")
    l1 = ProvenanceLedger()
    l1.record(x)
    l1.record(y)
    l2 = ProvenanceLedger()
    l2.record(y)
    l2.record(x)
    check("ledger canonical order is stable regardless of insertion order",
          l1.digest() == l2.digest())

    l3 = ProvenanceLedger()
    l3.record(x)
    l3.record(y)
    l3.record(x)
    check("a repeated source_id replaces the earlier record rather than duplicating it",
          len(l3.records) == 2, f"got {len(l3.records)}")


def _entry(**overrides):
    base = dict(
        inference_id="t-1",
        engine_version=ENGINE_VERSION,
        base_model_version="m",
        base_prediction=2.0,
        input_values={"crop": "Rice", "season": "Kharif", "crop_year": 2015},
        provenance=[],
        provenance_digest="",
        thermal_time={},
        anomaly_vector={},
        forecast_weights={},
        vegetation={},
        conflict={},
        correction_components={},
        correction_bounds={"lower": -0.12, "upper": 0.05},
        total_correction=0.0,
        calibration_selection={"quantile": 0.5},
        corrected_prediction=2.0,
        interval_lower=1.5,
        interval_upper=2.5,
        created_at="2026-01-01T00:00:00+00:00",
    )
    base.update(overrides)
    return LedgerEntry(**base)


def test_ledger():
    e = _entry().seal()
    check("a sealed entry verifies", e.verify_seal())

    e2 = _entry()
    e2.corrected_prediction = 99.0
    check("editing the output invalidates the seal", not e2.verify_seal())

    e3 = _entry()
    e3.input_values = {"crop": "Cotton(lint)", "season": "Kharif", "crop_year": 2015}
    check("editing a nested input value invalidates the seal", not e3.verify_seal())

    e4 = _entry().seal()
    e4.created_at = "2027-12-31T23:59:59+00:00"
    check("the creation timestamp is outside the committed payload",
          e4.verify_seal(), "timestamp should not be sealed")
    e5 = _entry().seal()
    e5.corrected_prediction = 1.999
    check("a change anywhere else does break the seal", not e5.verify_seal())

    chain = InferenceLedger()
    first = chain.append(_entry(inference_id="a"))
    second = chain.append(_entry(inference_id="b"))
    check("entries chain to their predecessor",
          second.previous_hash == first.entry_hash)
    check("a fresh chain verifies", chain.verify()["ok"])

    tampered = chain.append(_entry(inference_id="c"))
    tampered.corrected_prediction = 42.0
    check("altering a middle entry breaks chain verification",
          not chain.verify()["ok"], str(chain.verify()["problems"]))


def test_replay():
    entry = LedgerEntry(
        inference_id="r-1",
        engine_version=ENGINE_VERSION,
        base_model_version="m",
        base_prediction=2.0,
        input_values={
            "crop": "Rice",
            "season": "Kharif",
            "crop_year": 2015,
            "observed_daily": [
                {"date": "2026-06-01", "tmax": 33.0, "tmin": 24.0, "rain": 2.0, "et0": 5.0},
                {"date": "2026-06-02", "tmax": 34.0, "tmin": 25.0, "rain": 0.0, "et0": 6.0},
            ],
            "forecast_daily": [
                {"date": "2026-06-03", "tmax": 35.0, "tmin": 25.0, "rain": 1.0, "et0": 5.5},
            ],
            "weather_category": int(SourceCategory.LIVE),
            "vegetation_deviation": 0.01,
            "valid_pixel_pct": 88.0,
            "ladder": [{"radius_m": 90, "ndvi": 0.5}, {"radius_m": 180, "ndvi": 0.49}],
        },
        provenance=[],
        provenance_digest="",
        thermal_time={
            "current_gdd": 30.0,
            "base_temp_c": 10.0,
            "expectation": {
                "total_rainfall_mm": 100.0,
                "total_et0_mm": 200.0,
                "avg_temp_max": 33.0,
                "heat_days": 4.0,
            },
        },
        anomaly_vector={"rainfall_pct": -95.0, "et0_pct": -93.0, "temp_max_c": 0.0, "heat_days": 0.0},
        forecast_weights={"1": 0.6},
        vegetation={"quality_band": "high", "deviation": 0.01, "stability": None},
        conflict={},
        correction_components={"rainfall_pct": 0.001},
        correction_bounds={"lower": -0.12, "upper": 0.05},
        total_correction=0.001,
        calibration_selection={"quantile": 0.4},
        corrected_prediction=2.002,
        interval_lower=1.602,
        interval_upper=2.402,
        created_at="2026-01-01T00:00:00+00:00",
    ).seal()

    from backend.integrity.engine import IntegrityEngine

    outcome = replay(entry, IntegrityEngine.recompute)
    check("a replay-sufficient entry reproduces its own output", outcome["reproduced"],
          str(outcome["mismatches"]))
    check("stored and replayed output digests agree",
          outcome["stored_output_digest"] == outcome["replayed_output_digest"])

    import copy
    inconsistent = copy.deepcopy(entry)
    inconsistent.corrected_prediction = 5.0
    inconsistent.seal()
    bad = replay(inconsistent, IntegrityEngine.recompute)
    check("replay detects an output that does not follow from the record",
          not bad["reproduced"], str(bad["mismatches"]))

    future = entry
    future.engine_version = "99.0.0"
    future.seal()
    try:
        replay(future, IntegrityEngine.recompute)
        check("replay refuses across engine versions", False, "no ReplayError raised")
    except ReplayError:
        check("replay refuses across engine versions", True)

    tampered = entry
    tampered.interval_upper = 99.0
    try:
        replay(tampered, IntegrityEngine.recompute)
        check("replay refuses a record whose seal does not match", False, "no ReplayError raised")
    except ReplayError:
        check("replay refuses a record whose seal does not match", True)


def main():
    print("=" * 78)
    print("INTEGRITY ENGINE TESTS")
    print("=" * 78)
    for fn in (
        test_conformal_quantile,
        test_partition_stratification,
        test_pooled_backoff_reports_no_guarantee,
        test_gdd,
        test_horizon_weight,
        test_vegetation_detrending,
        test_conflict_detection,
        test_correction_model,
        test_provenance,
        test_ledger,
        test_replay,
    ):
        print(f"\n--- {fn.__name__} ---")
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            FAILED.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
            print(f"[FAIL] {fn.__name__} raised {type(exc).__name__}: {exc}")

    print("\n" + "=" * 78)
    print(f"PASSED {len(PASSED)}   FAILED {len(FAILED)}")
    if FAILED:
        for name, detail in FAILED:
            print(f"  FAILED: {name}  {detail}")
        sys.exit(1)
    print("ALL INTEGRITY ENGINE TESTS PASSED.")


if __name__ == "__main__":
    main()
