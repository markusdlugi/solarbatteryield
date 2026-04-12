"""
AC-coupled battery implementation.

Battery has its own bidirectional inverter. PV goes through the PV inverter
first (DC→AC), then the battery charges/discharges through its separate
inverter (AC↔DC).
"""
from __future__ import annotations

from solarbatteryield.models import DischargeStrategyConfig, HourlyResult
from solarbatteryield.simulation.battery._base import Battery
from solarbatteryield.simulation.battery.strategy import get_discharge_target
from solarbatteryield.simulation.inverter_efficiency import (
    get_inverter_efficiency,
    DEFAULT_INVERTER_EFFICIENCY_CURVE,
)
from solarbatteryield.simulation.load_regression import get_direct_pv_fraction


class AcCoupledBattery(Battery):
    """AC-coupled battery with its own bidirectional inverter."""

    def __init__(
            self,
            cap_gross: float,
            batt_eff: float,
            inv_cap: float,
            inv_eff_curve: tuple[tuple[int, float], ...] = DEFAULT_INVERTER_EFFICIENCY_CURVE,
            batt_inv_eff_curve: tuple[tuple[int, float], ...] = DEFAULT_INVERTER_EFFICIENCY_CURVE,
            strategy_config: DischargeStrategyConfig | None = None,
            min_load_w: float = 0.0,
    ) -> None:
        super().__init__(cap_gross, batt_eff, inv_cap, inv_eff_curve, strategy_config, min_load_w)
        self.batt_inv_eff_curve = batt_inv_eff_curve

    def _get_batt_inverter_efficiency(self, power_kw: float) -> float:
        """Get battery inverter efficiency (1C assumption: rated power = cap_gross)."""
        return get_inverter_efficiency(power_kw, self.cap_gross, self.batt_inv_eff_curve)

    def process_hour(self, gen_dc: float, load: float, hour: int) -> HourlyResult:
        if self.strategy_config.mode == "zero_feed_in":
            return self._process_zero_feed_in(gen_dc, load, hour)
        return self._process_target_based(gen_dc, load, hour)

    # ── Path A: Zero-feed-in (smart meter, regression on PV only) ────

    def _process_zero_feed_in(self, gen_dc: float, load: float, hour: int) -> HourlyResult:
        soc = self._soc

        # Get PV inverter efficiency
        inv_eff = self._get_inverter_efficiency(min(gen_dc, self.inv_cap))

        # Step 1: Convert DC to AC (limited by PV inverter)
        dc_to_inverter = min(gen_dc, self.inv_cap / inv_eff)
        gen_ac = dc_to_inverter * inv_eff
        curtailed = gen_dc - dc_to_inverter

        # Apply sub-hourly load regression
        fraction = get_direct_pv_fraction(load * 1000, gen_ac * 1000, self.min_load_w)
        direct_pv = fraction * min(load, gen_ac)

        surplus = gen_ac - direct_pv
        deficit = load - direct_pv

        # Handle surplus: charge battery (through battery inverter), then feed in
        feed_in = 0.0
        if surplus > 0:
            batt_inv_eff = self._get_batt_inverter_efficiency(surplus)
            combined_charge_eff = batt_inv_eff * self.batt_eff
            charge = min(surplus, (self._max_soc - soc) / combined_charge_eff)
            soc += charge * combined_charge_eff
            feed_in = surplus - charge

        # Handle deficit: discharge battery (through battery inverter) or grid
        grid_import = 0.0
        battery_discharge = 0.0
        if deficit > 0:
            batt_inv_eff = self._get_batt_inverter_efficiency(deficit)
            combined_discharge_eff = self.batt_eff * batt_inv_eff
            discharge = min(deficit / combined_discharge_eff, max(0, soc - self._min_soc))
            soc -= discharge
            battery_discharge = discharge * combined_discharge_eff
            grid_import = deficit - battery_discharge

        # Update internal state
        self._commit(soc, battery_discharge)

        return HourlyResult(
            grid_import=grid_import,
            feed_in=feed_in,
            curtailed=curtailed,
            direct_pv=direct_pv,
            battery_discharge=battery_discharge,
            pv_generation=gen_dc,
            consumption=load,
        )

    # ── Path B: Target-based (baseLoad / time_window, regression on system output) ─

    def _process_target_based(self, gen_dc: float, load: float, hour: int) -> HourlyResult:
        soc = self._soc
        target = get_discharge_target(hour, load, self.strategy_config)

        inv_eff = self._get_inverter_efficiency(min(gen_dc, self.inv_cap))

        # Step 1: Convert all DC to AC (limited by PV inverter)
        dc_to_inverter = min(gen_dc, self.inv_cap / inv_eff)
        gen_ac = dc_to_inverter * inv_eff
        curtailed = gen_dc - dc_to_inverter

        # Step 2: Compose system output from PV + battery
        pv_to_target = min(gen_ac, target)
        batt_needed = max(0.0, target - pv_to_target)
        batt_output_ac = 0.0
        if batt_needed > 0:
            batt_inv_eff = self._get_batt_inverter_efficiency(batt_needed)
            combined_discharge_eff = self.batt_eff * batt_inv_eff
            if combined_discharge_eff > 0:
                discharge = min(batt_needed / combined_discharge_eff,
                                max(0, soc - self._min_soc))
                soc -= discharge
                batt_output_ac = discharge * combined_discharge_eff

        # Step 3: Regression on entire system output
        direct_pv, battery_discharge, grid_import, feed_in_from_target = (
            self._apply_target_regression(load, pv_to_target, batt_output_ac)
        )

        # Step 4: PV surplus above target → charge battery → feed in
        pv_surplus = gen_ac - pv_to_target
        feed_in_surplus = 0.0
        if pv_surplus > 0:
            batt_inv_eff = self._get_batt_inverter_efficiency(pv_surplus)
            combined_charge_eff = batt_inv_eff * self.batt_eff
            charge = min(pv_surplus, (self._max_soc - soc) / combined_charge_eff)
            soc += charge * combined_charge_eff
            feed_in_surplus = pv_surplus - charge

        # Step 5: Surplus PV that battery couldn't absorb can still serve load
        bonus_pv, grid_import, feed_in_surplus = self._apply_surplus_regression(
            grid_import, feed_in_surplus,
        )
        direct_pv += bonus_pv

        feed_in = feed_in_from_target + feed_in_surplus

        # Update internal state
        self._commit(soc, battery_discharge)

        return HourlyResult(
            grid_import=grid_import,
            feed_in=feed_in,
            curtailed=curtailed,
            direct_pv=direct_pv,
            battery_discharge=battery_discharge,
            pv_generation=gen_dc,
            consumption=load,
        )
