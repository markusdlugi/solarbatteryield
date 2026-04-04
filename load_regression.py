"""
Sub-hourly load regression for improved self-consumption estimation.

Instead of comparing a single average load value against PV generation per hour,
this module distributes the hourly load into a probability density function of
instantaneous power levels (in 50 W bins). This captures the real-world variation
of household electrical load within each hour, which is critical for accurate
self-consumption estimates — especially for small balcony solar systems where
the inverter limit is close to the average load.

Example:
    With an average hourly load of 300 W and PV generation of 400 W, the naive
    approach assumes 100 % of the load is covered by PV. In reality, the load
    fluctuates: some minutes it draws 50 W (surplus goes to feed-in) and other
    minutes it draws 800 W (deficit from grid). The regression captures this
    distribution and computes a more realistic direct-PV fraction.

Data source:
    The pre-computed probability distributions (0–3450 W in 50 W bins) are derived
    from measured single-family house electrical load profiles of 38 households in
    Germany, published in:

        Schlemminger, M., Ohrdes, T., Schneider, E. et al.
        "Dataset on electrical single-family house and heat pump load profiles in Germany."
        Sci Data 9, 56 (2022). https://doi.org/10.1038/s41597-022-01156-1

    The regression database was processed and published by PVTools
    (MIT License, Copyright (c) 2023 nick81nrw):
        https://github.com/nick81nrw/PVTools

    For loads above the database range (>3450 W) a synthetic bimodal Gaussian
    distribution is generated, following the same approach as PVTools.
"""
from __future__ import annotations

import json
import math
from pathlib import Path


# ─── Regression Database ───────────────────────────────────────────────────────
_DB_PATH = Path(__file__).parent / "data" / "regression_db.json"

# Pre-computed bin resolution in the database
DB_RESOLUTION_W: int = 50

# Cache for looked-up distributions (regression_key → distribution)
_distribution_cache: dict[int, list[tuple[int, float]]] = {}


def _load_regression_db() -> dict[int, list[tuple[int, float]]]:
    """
    Load the regression database from JSON and convert to an efficient format.

    Returns:
        Dict mapping average consumption (W, rounded to 50 W bins) to a list of
        (power_level_W, probability) tuples.  Only non-zero entries are stored.
    """
    with open(_DB_PATH, encoding="utf-8") as f:
        raw: dict[str, dict[str, float]] = json.load(f)

    db: dict[int, list[tuple[int, float]]] = {}
    for consumption_key, distribution in raw.items():
        entries: list[tuple[int, float]] = [
            (int(power_str), prob)
            for power_str, prob in distribution.items()
            if prob > 0
        ]
        # Sort by power level for deterministic iteration
        entries.sort(key=lambda x: x[0])
        db[int(consumption_key)] = entries
    return db


# Loaded once at import time
_REGRESSION_DB: dict[int, list[tuple[int, float]]] = _load_regression_db()

# Maximum consumption key present in the pre-computed database
_DB_MAX_CONSUMPTION_W: int = max(_REGRESSION_DB.keys())


# ─── Synthetic Distribution for High Loads ─────────────────────────────────────

def _create_regression(load_w: float) -> tuple[list[tuple[int, float]], int]:
    """
    Create a synthetic regression for loads above the database range.

    Uses a bimodal Gaussian model (matching the PVTools approach):
      • Component 1: lower peak near base-load — µ₁ = load/3 + 50, σ₁ = load × 0.195
      • Component 2: higher peak near the mean — µ₂ = load × 1.1,   σ₂ = load × 0.1

    Returns:
        Tuple of (distribution as list of (power, probability), resolution in W).
    """
    multiplier = 8
    resolution = max(
        int(load_w * multiplier / 100 // 100) * 100,
        100,
    )
    regression_key = int(load_w // resolution) * resolution

    sigma1 = load_w * 0.195
    mu1 = load_w / 3 + 50
    sigma2 = load_w * 0.1
    mu2 = load_w + load_w / 10

    n_bins = max(int(regression_key / resolution) * multiplier, 1)
    powers = [i * resolution for i in range(n_bins)]

    sqrt_2pi = math.sqrt(2 * math.pi)
    inv_sigma1_sqrt2pi = 1.0 / (sigma1 * sqrt_2pi) if sigma1 > 0 else 0.0
    inv_sigma2_sqrt2pi = 1.0 / (sigma2 * sqrt_2pi) if sigma2 > 0 else 0.0

    unnorm: list[float] = []
    for p in powers:
        g1 = inv_sigma1_sqrt2pi * math.exp(-0.5 * ((p - mu1) / sigma1) ** 2) if sigma1 > 0 else 0.0
        g2 = inv_sigma2_sqrt2pi * math.exp(-0.5 * ((p - mu2) / sigma2) ** 2) if sigma2 > 0 else 0.0
        unnorm.append(g1 + g2)

    total = sum(unnorm)
    if total == 0:
        # Degenerate case — uniform fallback
        prob = 1.0 / len(powers) if powers else 1.0
        return [(p, prob) for p in powers], resolution

    distribution: list[tuple[int, float]] = [
        (powers[i], unnorm[i] / total)
        for i in range(len(powers))
        if unnorm[i] > 0
    ]
    return distribution, resolution


# ─── Public API ────────────────────────────────────────────────────────────────

def _get_distribution(load_w: float) -> tuple[list[tuple[int, float]], int]:
    """
    Look up (or create) the load distribution for a given average hourly load.

    Returns:
        Tuple of (distribution, power_delta) where power_delta is the midpoint
        offset to add to each bin's power level (half the bin width).
    """
    regression_key = int(load_w // DB_RESOLUTION_W) * DB_RESOLUTION_W

    if regression_key in _REGRESSION_DB:
        return _REGRESSION_DB[regression_key], DB_RESOLUTION_W // 2  # 25 W

    # Check cache for synthetic distributions
    if regression_key in _distribution_cache:
        # Retrieve resolution from cache tag — store alongside
        pass

    # Outside the pre-computed range: generate a synthetic distribution
    distribution, resolution = _create_regression(load_w)
    _distribution_cache[regression_key] = distribution
    return distribution, resolution // 2


def get_direct_pv_fraction(load_w: float, pv_w: float) -> float:
    """
    Calculate the self-consumption fraction considering sub-hourly load variation.

    Given an average hourly load and available PV power (both in watts), this
    function returns the fraction of ``min(load, pv)`` that is actually directly
    consumed by PV.  Values below 1.0 mean that some PV energy is *not*
    self-consumed even though the hourly average would suggest otherwise — because
    during low-load moments the PV exceeds the instantaneous demand.

    Args:
        load_w: Average hourly household load in watts.
        pv_w:   Available PV power in watts (AC side, after inverter).

    Returns:
        Fraction in [0.0, 1.0].  Multiply by ``min(load, pv)`` to obtain the
        actual direct-PV energy in the same unit as the inputs.
    """
    if load_w <= 0 or pv_w <= 0:
        return 0.0

    multiplicator = min(load_w, pv_w)
    if multiplicator <= 0:
        return 0.0

    distribution, power_delta = _get_distribution(load_w)

    # Weighted sum: for each instantaneous power level, compute the fraction of
    # the multiplicator that PV can cover, weighted by the probability of that
    # power level occurring within the hour.
    fraction = 0.0
    inv_mult = 1.0 / multiplicator
    for power, probability in distribution:
        # Fraction covered at this power level
        covered = min((power + power_delta) * inv_mult, 1.0)
        fraction += covered * probability

    return min(fraction, 1.0)

