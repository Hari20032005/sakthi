"""Capture one real ledger entry to illustrate the disclosure.

Section 7.2 of the disclosure quotes a worked example. That example must be a
captured entry, not a hand-written illustration, so that every number in it
can be traced to a run.

    python3 -m backend.validation.worked_example
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from backend.config import TRAINING_DATA_FILE, WEATHER_HISTORICAL_FILE, YIELD_DATA_FILE
from backend.integrity.calibration import CalibrationStore
from backend.integrity.engine import IntegrityEngine, fit_correction_model
from backend.integrity.ledger import ENGINE_VERSION, replay
from backend.integrity.thermal_time import accumulate_gdd, persistence_skill_curve
from backend.validation.degrade import REGIME_CLIMATOLOGY, build_season_records, climatology_lookup, degrade
from backend.validation.experiments import (
    FixedBaseModel,
    _base_row_for,
    _build_deployment_artefact,
    _prepared_context,
    _run_engine,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUT = BASE_DIR / "validation_results" / "worked_example.json"


def main() -> None:
    weather = pd.read_csv(WEATHER_HISTORICAL_FILE)
    weather["date"] = pd.to_datetime(weather["date"])
    yield_df = pd.read_csv(YIELD_DATA_FILE)
    train_df = pd.read_csv(TRAINING_DATA_FILE)

    records = build_season_records(yield_df, weather)
    ordered = sorted(records, key=lambda r: (r.crop_year, r.crop, r.season))
    clim = climatology_lookup(weather)
    skill_curve = persistence_skill_curve(weather, horizons=[1, 3, 5, 7, 10, 14, 16, 21])

    deployment = _build_deployment_artefact(ordered, records, train_df, clim, skill_curve)

    store = CalibrationStore(
        alpha=deployment["alpha"],
        min_partition=deployment["min_partition"],
        inflation=deployment["inflation"],
    )
    from backend.integrity.calibration import QualityKey

    for label, values in deployment["partitions"].items():
        parts = label.split("|")
        key = QualityKey(parts[0][1:], parts[1][1:], parts[2][1:])
        for value in values:
            store.add(key, value)

    correction = fit_correction_model(
        deployment["fit_relative_residuals"],
        deployment["fit_anomalies"],
        ridge=deployment["ridge"],
        alpha=deployment["bound_alpha"],
    )

    # A real rice Kharif season, run under climatology fallback: the state in
    # which the point estimate must be trusted least and the interval most.
    target = next(
        (r for r in ordered if r.crop == "Rice" and r.season == "Kharif" and r.crop_year == 2016),
        next(r for r in ordered if r.crop == "Rice" and r.season == "Kharif"),
    )

    base_model = FixedBaseModel(train_df)
    state = degrade(target, REGIME_CLIMATOLOGY, clim, seed=abs(hash(target.key)) % (2**31))
    base_pred = base_model.predict(_base_row_for(train_df, target))

    engine = IntegrityEngine(correction, store, skill_curve=skill_curve)
    prepared = _prepared_context(records, target.key, target.base_temp_c)
    result = _run_engine(engine, target, state, base_pred, [], prepared)

    entry = result.entry
    replay_outcome = replay(entry, IntegrityEngine.recompute)

    payload = {
        "season": target.key,
        "regime": REGIME_CLIMATOLOGY,
        "base_prediction": round(float(base_pred), 4),
        "actual_yield": target.yield_t_per_ha,
        "result": result.to_dict(),
        "correction_model": correction.to_dict(),
        "ledger_entry": entry.to_dict(),
        "replay": {k: v for k, v in replay_outcome.items() if k != "failures"},
        "skill_curve": {str(k): round(v, 4) for k, v in sorted(skill_curve.items())},
        "store_observations": store.total,
        "engine_version": ENGINE_VERSION,
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=float))
    print(f"wrote {OUT}")
    print(f"  season={target.key} regime={REGIME_CLIMATOLOGY}")
    print(f"  base={base_pred:.4f} corrected={result.corrected_prediction:.4f} "
          f"interval=[{result.interval_lower:.4f}, {result.interval_upper:.4f}]")
    print(f"  partition={result.selection.partition_label} n={result.selection.n_residuals} "
          f"guarantee={result.selection.guarantee_level}")
    print(f"  conflict={result.conflict.code.value}")
    print(f"  replay reproduced={replay_outcome['reproduced']}")


if __name__ == "__main__":
    main()
