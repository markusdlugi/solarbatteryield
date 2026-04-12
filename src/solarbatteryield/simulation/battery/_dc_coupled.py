"""
DC-coupled battery implementation.

Battery sits on the DC bus and shares the PV inverter. Charging bypasses the
inverter entirely; discharging goes through the shared inverter.
"""
from __future__ import annotations

from solarbatteryield.models import HourlyResult
from solarbatteryield.simulation.battery._base import Battery
from solarbatteryield.simulation.battery.strategy import get_discharge_target
from solarbatteryield.simulation.load_regression import get_direct_pv_fraction


class DcCoupledBattery(Battery):
    """DC-coupled battery: battery on DC bus, shared inverter."""

    def process_hour(self, gen_dc: float, load: float, hour: int) -> HourlyResult:
        if self.strategy_config.mode == "zero_feed_in":
            return self._process_zero_feed_in(gen_dc, load, hour)
        return self._process_target_based(gen_dc, load, hour)

    # ── Path A: Zero-feed-in (smart meter, regression on PV only) ────

    def _process_zero_feed_in(self, gen_dc: float, load: float, hour: int) -> HourlyResult:
        soc = self._soc

        # Get efficiency based on expected power through inverter
        inv_eff = self._get_inverter_efficiency(min(gen_dc, self.inv_cap))

        # Step 1: Determine maximum AC available from PV for load coverage
        max_dc_for_load = min(gen_dc, load / inv_eff, self.inv_cap / inv_eff)
        max_pv_to_load_ac = max_dc_for_load * inv_eff

        # Apply sub-hourly load regression
        fraction = get_direct_pv_fraction(load * 1000, max_pv_to_load_ac * 1000, self.min_load_w)
        pv_to_load_ac = fraction * min(load, max_pv_to_load_ac)
        actual_dc_for_load = pv_to_load_ac / inv_eff if inv_eff > 0 else 0.0
        load_deficit = load - pv_to_load_ac

        # Step 2: Charge battery from remaining DC (no inverter limit)
        dc_remaining = gen_dc - actual_dc_for_load
        charge = min(dc_remaining, (self._max_soc - soc) / self.batt_eff)
        soc += charge * self.batt_eff
        dc_after_charge = dc_remaining - charge

        # Step 3: Export surplus through inverter (limited by remaining capacity)
        remaining_inv_dc = max(0, self.inv_cap / inv_eff - actual_dc_for_load)
        dc_to_export = min(dc_after_charge, remaining_inv_dc)
        export_ac = dc_to_export * inv_eff
        curtailed = dc_after_charge - dc_to_export

        # Step 4: Cover deficit from battery or grid
        grid_import = 0.0
        battery_discharge = 0.0

        if load_deficit > 0:
            inv_headroom_dc = max(0, self.inv_cap / inv_eff - actual_dc_for_load - dc_to_export)
            combined_eff = self.batt_eff * inv_eff
            max_discharge = min(
                load_deficit / combined_eff,
                max(0, soc - self._min_soc),
                inv_headroom_dc / inv_eff / self.batt_eff,
            )
            soc -= max_discharge
            from_batt_ac = max_discharge * combined_eff
            grid_import = load_deficit - from_batt_ac
            battery_discharge = from_batt_ac

        # Update internal state
        self._commit(soc, battery_discharge)

        return HourlyResult(
            grid_import=grid_import,
            feed_in=export_ac,
            curtailed=curtailed,
            direct_pv=pv_to_load_ac,
            battery_discharge=battery_discharge,
            pv_generation=gen_dc,
            consumption=load,
        )

    # ── Path B: Target-based (baseLoad / time_window, regression on system output) ─

    def _process_target_based(self, gen_dc: float, load: float, hour: int) -> HourlyResult:
        soc = self._soc
        target = get_discharge_target(hour, load, self.strategy_config)

        inv_eff = self._get_inverter_efficiency(min(gen_dc, self.inv_cap))
        combined_eff = self.batt_eff * inv_eff

        # Step 1: PV contribution to target (DC side, through shared inverter)
        max_dc_for_target = min(gen_dc, target / inv_eff if inv_eff > 0 else 0.0,
                                self.inv_cap / inv_eff)
        pv_to_target_ac = max_dc_for_target * inv_eff

        # Step 2: Battery fills the gap between PV and target
        batt_needed_ac = max(0.0, target - pv_to_target_ac)
        batt_output_ac = 0.0
        if batt_needed_ac > 0 and combined_eff > 0:
            inv_headroom_dc = max(0, self.inv_cap / inv_eff - max_dc_for_target)
            max_discharge = min(
                batt_needed_ac / combined_eff,
                max(0, soc - self._min_soc),
                inv_headroom_dc / inv_eff / self.batt_eff if inv_eff > 0 else 0.0,
            )
            soc -= max_discharge
            batt_output_ac = max_discharge * combined_eff

        # Step 3: Regression on entire system output (both PV and battery are "blind")
        direct_pv, battery_discharge, grid_import, feed_in_from_target = (
            self._apply_target_regression(load, pv_to_target_ac, batt_output_ac)
        )

        # Step 4: PV surplus above target → charge battery → export rest
        dc_remaining = gen_dc - max_dc_for_target
        charge = min(dc_remaining, (self._max_soc - soc) / self.batt_eff)
        soc += charge * self.batt_eff
        dc_after_charge = dc_remaining - charge

        # Export through remaining inverter capacity
        batt_dc_used = (batt_output_ac / combined_eff) if combined_eff > 0 else 0.0
        inv_used_dc = max_dc_for_target + batt_dc_used
        remaining_inv_dc = max(0, self.inv_cap / inv_eff - inv_used_dc)
        dc_to_export = min(dc_after_charge, remaining_inv_dc)
        export_ac = dc_to_export * inv_eff
        curtailed = dc_after_charge - dc_to_export

        # Step 5: Surplus PV that battery couldn't absorb can still serve load
        bonus_pv, grid_import, export_ac = self._apply_surplus_regression(
            grid_import, export_ac,
        )
        direct_pv += bonus_pv

        feed_in = feed_in_from_target + export_ac

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
