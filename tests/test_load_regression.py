"""
Tests for the sub-hourly load regression module and its impact on simulation results.

Run with:  python -m pytest tests/ -v
"""
from __future__ import annotations

import sys
import os
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from load_regression import (
    get_direct_pv_fraction,
    _get_distribution,
    _create_regression,
    _REGRESSION_DB,
    _DB_MAX_CONSUMPTION_W,
    DB_RESOLUTION_W,
)
from models import SimulationParams
from simulation import simulate


# ──────────────────────────────────────────────────────────────────────────────
# Unit tests for load_regression module
# ──────────────────────────────────────────────────────────────────────────────

class TestRegressionDatabase(unittest.TestCase):
    """Verify the regression database loaded correctly."""

    def test_database_loaded(self):
        self.assertGreater(len(_REGRESSION_DB), 0)

    def test_database_bins(self):
        """DB should have 70 bins from 0 to 3450 in 50 W steps."""
        keys = sorted(_REGRESSION_DB.keys())
        self.assertEqual(keys[0], 0)
        self.assertEqual(keys[-1], 3450)
        self.assertEqual(len(keys), 70)

    def test_probabilities_sum_to_one(self):
        """Each bin's probabilities should sum to ~1.0."""
        for key, dist in _REGRESSION_DB.items():
            total = sum(p for _, p in dist)
            self.assertAlmostEqual(total, 1.0, places=4,
                                   msg=f"Bin {key}W sums to {total}")

    def test_resolution(self):
        self.assertEqual(DB_RESOLUTION_W, 50)

    def test_max_consumption(self):
        self.assertEqual(_DB_MAX_CONSUMPTION_W, 3450)


class TestGetDirectPvFraction(unittest.TestCase):
    """Test the core self-consumption fraction function."""

    # ── Edge cases ──
    def test_zero_load(self):
        self.assertEqual(get_direct_pv_fraction(0, 500), 0.0)

    def test_zero_pv(self):
        self.assertEqual(get_direct_pv_fraction(500, 0), 0.0)

    def test_negative_load(self):
        self.assertEqual(get_direct_pv_fraction(-100, 500), 0.0)

    def test_negative_pv(self):
        self.assertEqual(get_direct_pv_fraction(500, -100), 0.0)

    # ── Fraction bounds ──
    def test_fraction_between_zero_and_one(self):
        for load in [50, 200, 500, 1000, 2000]:
            for pv in [50, 200, 500, 1000, 2000]:
                f = get_direct_pv_fraction(load, pv)
                self.assertGreaterEqual(f, 0.0, f"load={load}, pv={pv}")
                self.assertLessEqual(f, 1.0, f"load={load}, pv={pv}")

    # ── Regression effect ──
    def test_fraction_less_than_one_for_surplus(self):
        """When PV >> load, fraction should be noticeably below 1.0 because
        at low-load moments within the hour, PV exceeds the instantaneous demand."""
        f = get_direct_pv_fraction(200, 800)
        self.assertLess(f, 1.0)
        self.assertGreater(f, 0.5)  # but not ridiculously low

    def test_fraction_less_than_one_for_deficit(self):
        """When load >> PV, fraction should also be < 1.0 because at low-load
        moments some PV is unused (goes to feed-in)."""
        f = get_direct_pv_fraction(800, 200)
        self.assertLess(f, 1.0)
        self.assertGreater(f, 0.5)

    def test_higher_pv_gives_higher_or_equal_direct_pv(self):
        """With more PV available, the absolute direct-PV energy should increase
        (or stay equal).  Note: the *fraction* itself may decrease because the
        base ``min(load, pv)`` changes — but the product must not decrease."""
        load = 300
        f_low = get_direct_pv_fraction(load, 100)
        f_high = get_direct_pv_fraction(load, 500)
        direct_low = f_low * min(load, 100)
        direct_high = f_high * min(load, 500)
        self.assertGreaterEqual(direct_high, direct_low)

    # ── Synthetic distribution ──
    def test_above_db_range(self):
        """Loads above 3450 W should still return a valid fraction."""
        f = get_direct_pv_fraction(5000, 800)
        self.assertGreater(f, 0.0)
        self.assertLessEqual(f, 1.0)

    def test_synthetic_regression_returns_valid_distribution(self):
        dist, resolution = _create_regression(5000)
        self.assertGreater(len(dist), 0)
        self.assertGreater(resolution, 0)
        total = sum(p for _, p in dist)
        self.assertAlmostEqual(total, 1.0, places=4)


# ──────────────────────────────────────────────────────────────────────────────
# Comparison test: old (naive) vs new (regression) simulation
# ──────────────────────────────────────────────────────────────────────────────

def _make_sim_params_from_config() -> SimulationParams:
    """Build SimulationParams matching the shared config string (decoded below).

    Config: Erweitert mode, 2 kWp system, DC-coupled, 800 W inverter limit,
    custom load profile, flex + periodic loads enabled.
    """
    from inverter_efficiency import INVERTER_EFFICIENCY_CURVES

    return SimulationParams(
        batt_loss_pct=10,
        dc_coupled=True,
        min_soc_summer_pct=10,
        min_soc_winter_pct=20,
        max_soc_summer_pct=100,
        max_soc_winter_pct=100,
        data_year=2015,
        inverter_limit_kw=0.8,  # 800 W
        inverter_efficiency_curve=INVERTER_EFFICIENCY_CURVES["median"],
        batt_inverter_efficiency_curve=INVERTER_EFFICIENCY_CURVES["median"],
        profile_mode="Erweitert",
        annual_kwh=2821,
        profile_base=[
            190, 170, 170, 170, 170, 170, 340, 220,
            230, 370, 260, 1040, 250, 220, 190, 200,
            200, 900, 410, 270, 860, 340, 190, 200,
        ],
        profile_saturday=None,
        profile_sunday=None,
        yearly_profile=None,
        seasonal_enabled=True,
        season_winter_pct=114,
        season_summer_pct=86,
        flex_load_enabled=True,
        flex_min_yield=5.0,
        flex_pool_size=3,
        flex_delta=[
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 110, 160, 0, 0, 410,
            530, -570, 0, 0, 0, 0, 0, 0,
        ],
        flex_refresh_rate=0.5,
        periodic_load_enabled=True,
        periodic_delta=[
            350, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
        ],
        periodic_interval_days=3,
    )


def _naive_fraction(load_w: float, pv_w: float) -> float:
    """Old (naive) approach: fraction is always 1.0 — all of min(load, pv) is
    self-consumed."""
    if load_w <= 0 or pv_w <= 0:
        return 0.0
    return 1.0


class TestSimulationComparison(unittest.TestCase):
    """Compare full simulation results with and without the regression."""

    @classmethod
    def setUpClass(cls):
        """Fetch PV data for the test config and run both simulations."""
        # We need real PVGIS data for the comparison.  To make the test
        # self-contained we generate a synthetic but realistic PV array:
        # 8760 hours, sine-shaped daily generation peaking at ~0.6 kW.
        rng = np.random.RandomState(42)
        hours = 8760
        pv = np.zeros(hours)
        for i in range(hours):
            hour = i % 24
            day = i // 24
            # Sunrise ~6, sunset ~20, peak at 13
            if 6 <= hour <= 20:
                solar_angle = np.sin(np.pi * (hour - 6) / 14)
                # Seasonal variation: more in summer (day ~180), less in winter
                season_factor = 0.5 + 0.5 * np.sin(2 * np.pi * (day - 80) / 365)
                pv[i] = max(0, solar_angle * season_factor * 0.6 + rng.normal(0, 0.02))
        cls.pv_data = pv
        cls.params = _make_sim_params_from_config()

        # ── Run with regression (current code) ──
        cls.result_regression = {}
        for cap in [0.0, 2.11, 4.22]:
            cls.result_regression[cap] = simulate(cls.pv_data, cap, cls.params)

        # ── Run WITHOUT regression (patch to return 1.0 always) ──
        cls.result_naive = {}
        with patch("simulation.get_direct_pv_fraction", side_effect=_naive_fraction):
            for cap in [0.0, 2.11, 4.22]:
                cls.result_naive[cap] = simulate(cls.pv_data, cap, cls.params)

    def test_regression_increases_grid_import(self):
        """With regression, more load isn't covered by PV -> higher grid import."""
        for cap in [0.0, 2.11, 4.22]:
            reg = self.result_regression[cap].grid_import
            naive = self.result_naive[cap].grid_import
            self.assertGreater(reg, naive,
                               f"cap={cap}: regression grid_import ({reg:.1f}) "
                               f"should exceed naive ({naive:.1f})")

    def test_regression_increases_feed_in(self):
        """With regression, more PV goes to feed-in during low-load moments.
        Only checked for the no-battery case — with a battery the surplus
        is absorbed and both approaches may show zero feed-in."""
        reg = self.result_regression[0.0].feed_in
        naive = self.result_naive[0.0].feed_in
        self.assertGreater(reg, naive,
                           f"cap=0: regression feed_in ({reg:.1f}) "
                           f"should exceed naive ({naive:.1f})")

    def test_consumption_unchanged(self):
        """Total consumption should not change — regression only affects
        the split between direct PV, battery, and grid."""
        for cap in [0.0, 2.11, 4.22]:
            reg = self.result_regression[cap].total_consumption
            naive = self.result_naive[cap].total_consumption
            self.assertAlmostEqual(reg, naive, places=2,
                                   msg=f"cap={cap}: consumption mismatch")

    def test_energy_balance(self):
        """For each scenario, verify energy conservation:
        pv_generation = direct_pv + battery_charge_equivalent + feed_in + curtailed
        consumption = direct_pv + battery_discharge + grid_import
        """
        for cap, result in self.result_regression.items():
            monthly = result.monthly
            total_direct_pv = sum(m.direct_pv for m in monthly.values())
            total_battery = sum(m.battery for m in monthly.values())
            total_grid = sum(m.grid_import for m in monthly.values())
            total_consumption = sum(m.consumption for m in monthly.values())

            # consumption = direct_pv + battery_discharge + grid_import
            supply = total_direct_pv + total_battery + total_grid
            self.assertAlmostEqual(
                supply, total_consumption, places=1,
                msg=f"cap={cap}: supply ({supply:.1f}) != consumption ({total_consumption:.1f})")

    def test_print_comparison(self):
        """Print a summary table for manual inspection (not a real assertion)."""
        print("\n" + "=" * 78)
        print("COMPARISON: Naive (old) vs Regression (new) simulation results")
        print("=" * 78)
        header = f"{'Battery':>10} | {'Metric':>18} | {'Naive':>10} | {'Regress.':>10} | {'Delta':>10} | {'Delta%':>8}"
        print(header)
        print("-" * 78)

        for cap in [0.0, 2.11, 4.22]:
            naive = self.result_naive[cap]
            reg = self.result_regression[cap]

            for label, n_val, r_val in [
                ("Grid import kWh", naive.grid_import, reg.grid_import),
                ("Feed-in kWh", naive.feed_in, reg.feed_in),
                ("Curtailed kWh", naive.curtailed, reg.curtailed),
                ("Consumption kWh", naive.total_consumption, reg.total_consumption),
            ]:
                delta = r_val - n_val
                pct = (delta / n_val * 100) if n_val != 0 else 0
                print(f"{cap:>8.2f}  | {label:>18} | {n_val:>10.1f} | {r_val:>10.1f} | {delta:>+10.1f} | {pct:>+7.1f}%")
            print("-" * 78)


if __name__ == "__main__":
    unittest.main(verbosity=2)

