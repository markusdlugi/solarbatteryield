"""
DC-coupled battery implementation.

Battery sits on the DC bus and shares the PV inverter. Charging bypasses the
inverter entirely; discharging goes through the shared inverter.
"""
from __future__ import annotations

from solarbatteryield.models import HourlyResult
from solarbatteryield.simulation.battery._base import Battery
from solarbatteryield.simulation.load_regression import get_direct_pv_fraction


class DcCoupledBattery(Battery):
    """DC-coupled battery: battery on DC bus, shared inverter."""

    def process_hour(self, gen_dc: float, load: float, hour: int) -> HourlyResult:
        soc = self._soc

        # Get efficiency based on expected power through inverter
        inv_eff = self._get_inverter_efficiency(min(gen_dc, self.inv_cap))

        # Step 1: Determine maximum AC available from PV for load coverage
        max_dc_for_load = min(gen_dc, load / inv_eff, self.inv_cap / inv_eff)
        max_pv_to_load_ac = max_dc_for_load * inv_eff

        # Apply sub-hourly load regression
        fraction = get_direct_pv_fraction(load * 1000, max_pv_to_load_ac * 1000)
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
        self._soc = soc
        self._total_discharge += battery_discharge

        return HourlyResult(
            grid_import=grid_import,
            feed_in=export_ac,
            curtailed=curtailed,
            direct_pv=pv_to_load_ac,
            battery_discharge=battery_discharge,
            pv_generation=gen_dc,
            consumption=load,
        )
