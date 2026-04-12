#!/usr/bin/env python3
"""
Build a base-load-free regression database from the Schlemminger 1-min data.

For each of the 28 accepted households the per-household P1 base load is
subtracted so that the resulting distributions capture **only** the variable
load above the always-on floor.  The output ``regression_db.json`` has the
same format as the original DB but with 25 W bins instead of 50 W.

Usage:
    uv run python scripts/build_regression_db.py

Input:
    data/raw/2019_data_1min.hdf5   (Schlemminger et al. 2022, Zenodo 5642902)

Output:
    src/solarbatteryield/simulation/data/regression_db.json   (overwritten)
"""
from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
HDF5 = PROJECT_ROOT / "data" / "raw" / "2019_data_1min.hdf5"
OUTPUT_PATH = PROJECT_ROOT / "src" / "solarbatteryield" / "simulation" / "data" / "regression_db.json"

# ── Constants ────────────────────────────────────────────────────────────────
DB_RESOLUTION_W = 25  # bin width (was 50 in PVTools DB)
MAX_CONSUMPTION_W = 3450  # highest outer key
BASE_LOAD_PERCENTILE = 1  # P1 = 1st percentile
MIN_COMPLETENESS = 0.95  # ≥95 % non-NaN minutes required
MAX_NEGATIVE_PCT = 0.05  # ≤5 % negative values allowed
MINUTES_PER_YEAR = 365 * 24 * 60  # 525 600 for 2019
MINUTES_PER_HOUR = 60


# ── Step 1: load & filter ───────────────────────────────────────────────────

def load_and_filter(f: h5py.File) -> dict[str, np.ndarray]:
    """Load P_TOT for NO_PV/WITH_PV households passing quality filters."""
    accepted: dict[str, np.ndarray] = {}
    rejected: list[str] = []

    for cat in ["NO_PV", "WITH_PV"]:
        if cat not in f:
            continue
        for sfh in sorted(f[cat].keys()):
            tbl_path = f"{cat}/{sfh}/HOUSEHOLD/table"
            if tbl_path not in f:
                continue
            tbl = f[tbl_path]
            if "P_TOT" not in tbl.dtype.names:
                continue

            values = tbl["P_TOT"][:].astype(np.float64)
            name = f"{sfh} ({cat})"

            # Quality checks
            n_valid = np.count_nonzero(~np.isnan(values))
            completeness = n_valid / MINUTES_PER_YEAR
            if completeness < MIN_COMPLETENESS:
                rejected.append(f"  ✘ {name:<22} completeness {completeness:.1%}")
                continue

            clean = values[~np.isnan(values)]
            pct_neg = np.count_nonzero(clean < 0) / len(clean)
            if pct_neg > MAX_NEGATIVE_PCT:
                rejected.append(f"  ✘ {name:<22} negative {pct_neg:.1%}")
                continue

            accepted[name] = values

    print(f"Accepted: {len(accepted)},  Rejected: {len(rejected)}")
    for r in rejected:
        print(r)
    return accepted


# ── Step 2: compute base load & variable load ────────────────────────────────

def compute_variable_loads(
        households: dict[str, np.ndarray],
) -> dict[str, tuple[float, np.ndarray]]:
    """
    Return {name: (base_load_w, variable_load_array)} for each household.

    variable_load = max(0, clipped_P_TOT − P1)
    """
    result: dict[str, tuple[float, np.ndarray]] = {}

    print(f"\n{'Household':<22} {'Base(P1)':>8} {'VarMean':>8} {'VarMax':>8} {'kWh/a':>8}")
    print("─" * 58)

    for name in sorted(households):
        values = households[name]
        clean = values[~np.isnan(values)]
        # Clip negative measurement artefacts before computing P1
        clipped = np.maximum(0.0, clean)
        base_load = float(np.percentile(clipped, BASE_LOAD_PERCENTILE))
        variable = np.maximum(0.0, clipped - base_load)

        result[name] = (base_load, variable)

        var_mean = float(np.mean(variable))
        var_max = float(np.max(variable))
        kwh = float(np.sum(clipped) / 60 / 1000)
        print(f"  {name:<20} {base_load:>8.0f} {var_mean:>8.0f} {var_max:>8.0f} {kwh:>8.0f}")

    return result


# ── Step 3 + 4: build per-household distributions ───────────────────────────

def build_per_household_distributions(
        var_loads: dict[str, tuple[float, np.ndarray]],
) -> tuple[
    dict[str, dict[int, dict[int, float]]],  # hh_dist[name][cons_bin][power_bin] = prob
    dict[str, dict[int, int]],  # hh_hours[name][cons_bin] = count
]:
    """
    For each household and each 25 W consumption bin, compute the probability
    distribution of minute-level variable-load power bins.
    """
    hh_dist: dict[str, dict[int, dict[int, float]]] = {}
    hh_hours: dict[str, dict[int, int]] = {}

    consumption_bins = list(range(0, MAX_CONSUMPTION_W + 1, DB_RESOLUTION_W))

    for name, (base_load, variable) in sorted(var_loads.items()):
        # Reshape into hours
        n_hours = len(variable) // MINUTES_PER_HOUR
        hourly_matrix = variable[: n_hours * MINUTES_PER_HOUR].reshape(n_hours, MINUTES_PER_HOUR)
        hourly_means = hourly_matrix.mean(axis=1)

        # Assign each hour to a consumption bin
        hour_bins = np.minimum(
            (hourly_means // DB_RESOLUTION_W).astype(int) * DB_RESOLUTION_W,
            MAX_CONSUMPTION_W,
        )

        dist: dict[int, dict[int, float]] = {}
        hours: dict[int, int] = {}

        for cons_bin in consumption_bins:
            mask = hour_bins == cons_bin
            count = int(mask.sum())
            if count == 0:
                continue

            # Collect all minute values from matching hours
            minute_vals = hourly_matrix[mask].flatten()

            # Bin into 25 W power bins
            power_bins = (minute_vals // DB_RESOLUTION_W).astype(int) * DB_RESOLUTION_W

            # Count and normalize
            unique, counts = np.unique(power_bins, return_counts=True)
            total = counts.sum()
            dist[cons_bin] = {int(u): float(c / total) for u, c in zip(unique, counts)}
            hours[cons_bin] = count

        hh_dist[name] = dist
        hh_hours[name] = hours

    return hh_dist, hh_hours


# ── Step 5: weighted average across households ──────────────────────────────

def weighted_average(
        hh_dist: dict[str, dict[int, dict[int, float]]],
        hh_hours: dict[str, dict[int, int]],
) -> dict[int, dict[int, float]]:
    """
    For each consumption bin, weight-average household distributions by
    their hour counts.
    """
    consumption_bins = list(range(0, MAX_CONSUMPTION_W + 1, DB_RESOLUTION_W))
    merged: dict[int, dict[int, float]] = {}

    for cons_bin in consumption_bins:
        # Collect all contributing households
        contributors: list[tuple[dict[int, float], int]] = []
        for name in hh_dist:
            if cons_bin in hh_dist[name]:
                contributors.append((hh_dist[name][cons_bin], hh_hours[name][cons_bin]))

        if not contributors:
            # No data for this bin — create a delta at the bin midpoint
            mid = cons_bin + DB_RESOLUTION_W // 2
            merged[cons_bin] = {mid: 1.0}
            continue

        # Union of all power bins
        all_power_bins: set[int] = set()
        for dist, _ in contributors:
            all_power_bins.update(dist.keys())

        # Weighted sum
        total_weight = sum(w for _, w in contributors)
        avg: dict[int, float] = {}
        for pb in sorted(all_power_bins):
            weighted_sum = sum(
                dist.get(pb, 0.0) * weight
                for dist, weight in contributors
            )
            avg[pb] = weighted_sum / total_weight

        merged[cons_bin] = avg

    return merged


# ── Step 6: serialize ────────────────────────────────────────────────────────

def serialize(merged: dict[int, dict[int, float]]) -> None:
    """Write the regression DB as JSON (same format as existing DB).

    Only non-zero probabilities are written — ``_load_regression_db()``
    in ``load_regression.py`` already filters ``prob > 0``, so omitting
    zeros is safe and reduces the file from ~1.4 MB to ~150 KB.
    """
    output: dict[str, dict[str, float]] = {}
    total_entries = 0
    for cons_bin in sorted(merged):
        dist = merged[cons_bin]
        sparse: dict[str, float] = {
            str(pb): prob
            for pb, prob in sorted(dist.items())
            if prob > 0
        }
        output[str(cons_bin)] = sparse
        total_entries += len(sparse)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=True)

    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"Written: {OUTPUT_PATH}")
    print(f"Size:    {size_kb:.0f} KB")
    print(f"Outer keys: {len(output)} (0–{MAX_CONSUMPTION_W}, step {DB_RESOLUTION_W})")
    print(f"Non-zero entries: {total_entries:,} (sparse format, zeros omitted)")


# ── Step 7: validate ────────────────────────────────────────────────────────

def validate(merged: dict[int, dict[int, float]]) -> None:
    """Run validation checks on the built database."""
    print(f"\n{'=' * 70}")
    print("VALIDATION")
    print(f"{'=' * 70}")

    # 7a. Sum check
    max_deviation = 0.0
    for cons_bin, dist in sorted(merged.items()):
        total = sum(dist.values())
        dev = abs(total - 1.0)
        max_deviation = max(max_deviation, dev)
        if dev > 0.001:
            print(f"  ⚠️  Bin {cons_bin}W: sum = {total:.6f} (deviation {dev:.6f})")
    print(f"  Sum check:     max deviation = {max_deviation:.8f} {'✅' if max_deviation < 0.001 else '❌'}")

    # 7b. Low-bin mass check
    # For low consumption bins (< 100W) it is expected that many minutes are
    # at zero variable load, so we only flag bins >= 100W.
    max_zero_mass = 0.0
    worst_bin = 0
    for cons_bin, dist in sorted(merged.items()):
        if cons_bin < 100:
            continue
        zero_mass = dist.get(0, 0.0)
        if zero_mass > max_zero_mass:
            max_zero_mass = zero_mass
            worst_bin = cons_bin
    print(f"  Zero-bin mass:  max P(0W) for cons≥100W = {max_zero_mass:.4f} "
          f"at {worst_bin}W {'✅' if max_zero_mass < 0.05 else '⚠️'}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if not HDF5.exists():
        print(f"ERROR: {HDF5} not found. Run explore_schlemminger.py first.")
        raise SystemExit(1)

    print("=" * 70)
    print("BUILD BASE-LOAD-FREE REGRESSION DATABASE")
    print("=" * 70)
    print(f"  Source:     {HDF5.name}")
    print(f"  Output:     {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"  Resolution: {DB_RESOLUTION_W} W")
    print(f"  Base load:  P{BASE_LOAD_PERCENTILE}")
    print()

    # 1. Load & filter
    with h5py.File(HDF5, "r") as f:
        households = load_and_filter(f)

    # 2. Compute variable loads
    var_loads = compute_variable_loads(households)

    # 3+4. Per-household distributions
    print(f"\nBuilding per-household distributions…")
    hh_dist, hh_hours = build_per_household_distributions(var_loads)

    # Coverage stats
    total_hours = sum(
        sum(hours.values()) for hours in hh_hours.values()
    )
    print(f"  Total household-hours: {total_hours:,}")

    # 5. Weighted average
    print("Averaging across households…")
    merged = weighted_average(hh_dist, hh_hours)

    # 6. Serialize
    print()
    serialize(merged)

    # 7. Validate
    validate(merged)

    print(f"\n{'=' * 70}")
    print("DONE ✅")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
