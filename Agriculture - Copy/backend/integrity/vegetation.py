"""Vegetation observation quality from spatial-support stability.

No parcel boundary polygon is available for these farms, so a vegetation index
is sampled over a circular buffer around the farm point. The buffer radius is
an arbitrary choice, and area-averaged vegetation index is known to vary
monotonically with spatial resolution within a resolution class. A naive
"stability across radii" metric would therefore largely measure that known
scale trend rather than anything about how well the sample represents the field.

The fix implemented here: fit the systematic scale trend across the radius
ladder first, then measure how far each radius *departs from that trend*. A
ladder that follows the expected scale trend is a spatially homogeneous
neighbourhood. A ladder that departs from it -- where the index changes faster
or slower than resolution alone explains -- is heterogeneous, and the point
sample is a poorer description of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

# Radius ladder in metres. The first entry matches the production hard-coded
# 180 m buffer so results remain comparable with the existing twin state.
DEFAULT_LADDER: Sequence[int] = (90, 180, 360, 720, 1440)

# Stop extending the ladder once the marginal step changes the index by less
# than this many NDVI units (1/300 ~ 0.0033), i.e. below the precision to which
# the index is reported.
CONVERGENCE_TOLERANCE = 1.0 / 300.0


@dataclass
class LadderSample:
    radius_m: int
    ndvi: float
    valid_pixel_pct: float


@dataclass
class SupportStability:
    """Spatial representativeness of a point-sampled vegetation index."""

    radii_m: List[int]
    ndvi_by_radius: List[float]
    convergence_radius_m: Optional[int]
    converged: bool
    trend_slope: float
    trend_r2: float
    residual_rms: float
    normalised_residual: float
    spatial_trust: float
    n_samples: int

    def to_dict(self) -> Dict:
        return {
            "radii_m": self.radii_m,
            "ndvi_by_radius": [round(v, 4) for v in self.ndvi_by_radius],
            "convergence_radius_m": self.convergence_radius_m,
            "converged": self.converged,
            "trend_slope": round(self.trend_slope, 6),
            "trend_r2": round(self.trend_r2, 4),
            "residual_rms": round(self.residual_rms, 5),
            "normalised_residual": round(self.normalised_residual, 4),
            "spatial_trust": round(self.spatial_trust, 4),
            "n_samples": self.n_samples,
        }


def ndvi_quality_band(valid_pixel_pct: Optional[float], stability: Optional[SupportStability]) -> str:
    """Collapse per-observation quality into the band used as a calibration key.

    Bands are deliberately coarse. The calibration store is populated by
    degrading a small number of real seasons, so fine-grained bands would leave
    every partition below the validity floor and collapse the method back to a
    pooled constant.
    """

    if valid_pixel_pct is None:
        return "absent"
    if valid_pixel_pct < 20.0:
        return "degraded"
    if stability is None:
        return "high"
    if stability.normalised_residual > 0.45 or not stability.converged:
        return "degraded"
    return "high"


def support_stability(
    samples: Sequence[LadderSample],
    tolerance: float = CONVERGENCE_TOLERANCE,
    scale_reference: float = 0.10,
) -> SupportStability:
    """De-trended stability of a vegetation index over a radius ladder.

    ``samples`` must be ordered by increasing radius. ``scale_reference`` is the
    magnitude of index change over the ladder considered "fully heterogeneous";
    it sets the scale on which ``spatial_trust`` saturates at zero.
    """

    radii = [int(s.radius_m) for s in samples]
    values = [float(s.ndvi) for s in samples]
    n = len(values)

    if n < 3:
        span = float(max(values) - min(values)) if n > 1 else 0.0
        return SupportStability(
            radii_m=radii,
            ndvi_by_radius=values,
            convergence_radius_m=radii[-1] if radii else None,
            converged=False,
            trend_slope=0.0,
            trend_r2=0.0,
            residual_rms=span,
            normalised_residual=min(1.0, span / max(scale_reference, 1e-9)),
            spatial_trust=max(0.0, 1.0 - min(1.0, span / max(scale_reference, 1e-9))),
            n_samples=n,
        )

    x = np.log(np.asarray(radii, dtype=float))
    y = np.asarray(values, dtype=float)
    design = np.vstack([np.ones_like(x), x]).T
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    fitted = design @ coef
    residuals = y - fitted
    ss_res = float(np.sum(residuals**2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-15 else 0.0
    rms = float(np.sqrt(ss_res / n))

    # Convergence is judged on what an extra radius adds *beyond the fitted
    # scale trend*, not on the raw change between successive radii. A uniform
    # field still shows a sizeable raw change at every step because the scale
    # trend is real, so a raw-delta criterion would report a perfectly uniform
    # neighbourhood as never converging. The test is instead: does adding the
    # next radius move the trend's prediction there by more than the tolerance?
    converged_at = None
    for i in range(3, n):
        partial = np.vstack([np.ones(i), x[:i]]).T
        pcoef, *_ = np.linalg.lstsq(partial, y[:i], rcond=None)
        predicted_next = float(np.array([1.0, x[i]]) @ pcoef)
        if abs(y[i] - predicted_next) <= tolerance:
            converged_at = radii[i]
            break
    converged = converged_at is not None

    normalised = min(1.0, rms / max(scale_reference / 2.0, 1e-9))
    trust = max(0.0, 1.0 - normalised)

    return SupportStability(
        radii_m=radii,
        ndvi_by_radius=values,
        convergence_radius_m=converged_at,
        converged=converged,
        trend_slope=float(coef[1]),
        trend_r2=float(max(0.0, min(1.0, r2))),
        residual_rms=rms,
        normalised_residual=float(normalised),
        spatial_trust=float(trust),
        n_samples=n,
    )


def simulate_ladder(
    mean_ndvi: float,
    valid_pixel_pct: float,
    heterogeneity: float,
    seed: int,
    ladder: Sequence[int] = DEFAULT_LADDER,
    scale_trend: float = -0.0125,
) -> List[LadderSample]:
    """Generate a deterministic synthetic radius ladder for degraded-condition testing.

    The synthetic ladder reproduces the two effects that make the de-trending
    necessary: a systematic monotone index decrease with increasing radius
    (``scale_trend``) plus local departures driven by spatial heterogeneity.
    Heterogeneity is expressed as the standard deviation, in index units, of
    the true sub-pixel field; its expected contribution to the value sampled at
    radius r grows as ``sigma / sqrt(r)``.
    """

    rng = np.random.default_rng(seed)
    samples: List[LadderSample] = []
    for radius in ladder:
        local = rng.normal(0.0, heterogeneity / np.sqrt(radius / 90.0))
        value = mean_ndvi + scale_trend * np.log(radius / 90.0) + local
        coverage = max(0.0, min(100.0, valid_pixel_pct + rng.normal(0.0, 4.0)))
        samples.append(LadderSample(radius_m=int(radius), ndvi=float(value), valid_pixel_pct=float(coverage)))
    return samples
