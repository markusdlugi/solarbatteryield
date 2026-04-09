"""
AC-coupled battery implementation.

Battery has its own bidirectional inverter. PV goes through the PV inverter
first (DC→AC), then the battery charges/discharges through its separate
inverter (AC↔DC).
"""
from __future__ import annotations

from solarbatteryield.models import HourlyResult
from solarbatteryield.simulation.battery._base import Battery
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
    ) -> None:
        super().__init__(cap_gross, batt_eff, inv_cap, inv_eff_curve)
        self.batt_inv_eff_curve = batt_inv_eff_curve

    def _get_batt_inverter_efficiency(self, power_kw: float) -> float:
        """Get battery inverter efficiency (1C assumption: rated power = cap_gross)."""
        return get_inverter_efficiency(power_kw, self.cap_gross, self.batt_inv_eff_curve)

    def process_hour(self, gen_dc: float, load: float, hour: int) -> HourlyResult:
        soc = self._soc

        # Get PV inverter efficiency
        inv_eff = self._get_inverter_efficiency(min(gen_dc, self.inv_cap))

        # Step 1: Convert DC to AC (limited by PV inverter)
        dc_to_inverter = min(gen_dc, self.inv_cap / inv_eff)
        gen_ac = dc_to_inverter * inv_eff
        curtailed = gen_dc - dc_to_inverter

        # Apply sub-hourly load regression
        fraction = get_direct_pv_fraction(load * 1000, gen_ac * 1000)
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
        self._soc = soc
        self._total_discharge += battery_discharge

        return HourlyResult(
            grid_import=grid_import,
            feed_in=feed_in,
            curtailed=curtailed,
            direct_pv=direct_pv,
            battery_discharge=battery_discharge,
            pv_generation=gen_dc,
            consumption=load,
        )
