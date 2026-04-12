"""
Abstract base class for battery implementations.

Encapsulates SoC state, efficiency curves, and the process_hour() contract.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from solarbatteryield.models import DischargeStrategyConfig, HourlyResult
from solarbatteryield.simulation.inverter_efficiency import (
    get_inverter_efficiency,
    DEFAULT_INVERTER_EFFICIENCY_CURVE,
)


class Battery(ABC):
    """Abstract battery managing SoC, efficiency, and energy flow."""

    def __init__(
            self,
            cap_gross: float,
            batt_eff: float,
            inv_cap: float,
            inv_eff_curve: tuple[tuple[int, float], ...] = DEFAULT_INVERTER_EFFICIENCY_CURVE,
            strategy_config: DischargeStrategyConfig | None = None,
            min_load_w: float = 0.0,
    ) -> None:
        self.cap_gross = cap_gross
        self.batt_eff = batt_eff
        self.inv_cap = inv_cap
        self.inv_eff_curve = inv_eff_curve
        self.strategy_config = strategy_config or DischargeStrategyConfig()
        self.min_load_w = min_load_w

        self._soc: float = 0.0
        self._min_soc: float = 0.0
        self._max_soc: float = 0.0
        self._total_discharge: float = 0.0

    # ── Public API ───────────────────────────────────────────────

    def set_soc_limits(self, min_soc: float, max_soc: float) -> None:
        """Set per-hour SoC limits (called by simulate loop)."""
        self._min_soc = min_soc
        self._max_soc = max_soc

    @abstractmethod
    def process_hour(self, gen_dc: float, load: float, hour: int) -> HourlyResult:
        """Process one simulation hour and return the energy flow result."""

    @property
    def soc(self) -> float:
        """Current state of charge in kWh."""
        return self._soc

    @property
    def soc_pct(self) -> float:
        """Current SoC as percentage (0-100)."""
        if self.cap_gross <= 0:
            return 0.0
        return (self._soc / self.cap_gross) * 100

    @property
    def total_discharge(self) -> float:
        """Cumulative discharge energy in kWh (AC-side)."""
        return self._total_discharge

    # ── Shared helpers ───────────────────────────────────────────

    def _get_inverter_efficiency(self, power_kw: float) -> float:
        """Get PV inverter efficiency for a given power level."""
        return get_inverter_efficiency(power_kw, self.inv_cap, self.inv_eff_curve)

    def _apply_target_regression(
            self,
            load: float,
            pv_to_target: float,
            batt_output_ac: float,
    ) -> tuple[float, float, float, float]:
        """
        Apply sub-hourly load regression to the combined system output and
        split self-consumed energy proportionally between PV and battery.

        Used by the target-based path (base_load / time_window) in both
        DC-coupled and AC-coupled subclasses.

        Returns:
            (direct_pv, battery_discharge, grid_import, feed_in_from_target)
        """
        from solarbatteryield.simulation.load_regression import get_direct_pv_fraction

        system_output = pv_to_target + batt_output_ac

        fraction = get_direct_pv_fraction(load * 1000, system_output * 1000, self.min_load_w)
        self_consumed = fraction * min(load, system_output)
        feed_in_from_target = system_output - self_consumed
        grid_import = load - self_consumed

        # Split self_consumed between PV and battery proportionally
        if system_output > 0:
            pv_share = pv_to_target / system_output
        else:
            pv_share = 1.0
        direct_pv = self_consumed * pv_share
        battery_discharge = self_consumed * (1 - pv_share)

        return direct_pv, battery_discharge, grid_import, feed_in_from_target

    def _apply_surplus_regression(
            self,
            remaining_load: float,
            pv_surplus_ac: float,
    ) -> tuple[float, float, float]:
        """
        Second regression pass for PV surplus that the battery could not absorb.

        When the battery is full (or partially full), PV surplus above the target
        is exported.  If there is still unmet load (remaining_load > 0), the
        surplus acts like uncontrolled PV — it can serve part of the remaining
        load, just as in the zero-feed-in path.

        This avoids the pessimistic assumption that surplus PV is *always*
        exported even when the household could use it.

        Args:
            remaining_load: Grid import left after the target regression (kW).
            pv_surplus_ac: PV surplus AC power being exported (kW).

        Returns:
            (bonus_direct_pv, reduced_grid_import, reduced_surplus)
        """
        if remaining_load <= 0 or pv_surplus_ac <= 0:
            return 0.0, remaining_load, pv_surplus_ac

        from solarbatteryield.simulation.load_regression import get_direct_pv_fraction

        fraction = get_direct_pv_fraction(remaining_load * 1000, pv_surplus_ac * 1000, self.min_load_w)
        bonus = fraction * min(remaining_load, pv_surplus_ac)

        return bonus, remaining_load - bonus, pv_surplus_ac - bonus

    def _commit(self, soc: float, battery_discharge: float) -> None:
        """Update internal SoC and cumulative discharge after processing an hour."""
        self._soc = soc
        self._total_discharge += battery_discharge
