"""
Null-object battery for PV-only systems (no storage).

When cap_gross == 0, the factory returns NoBattery. This eliminates
all ``if cap_gross > 0`` guards from the simulation loop.
"""
from __future__ import annotations

from solarbatteryield.models import HourlyResult
from solarbatteryield.simulation.battery._base import Battery
from solarbatteryield.simulation.load_regression import get_direct_pv_fraction


class NoBattery(Battery):
    """PV-only system without battery storage."""

    def process_hour(self, gen_dc: float, load: float, hour: int) -> HourlyResult:
        inv_eff = self._get_inverter_efficiency(min(gen_dc, self.inv_cap))

        # PV → Inverter → AC (limited by inverter)
        dc_to_inverter = min(gen_dc, self.inv_cap / inv_eff)
        gen_ac = dc_to_inverter * inv_eff
        curtailed = gen_dc - dc_to_inverter

        # Direct PV with sub-hourly load regression
        fraction = get_direct_pv_fraction(load * 1000, gen_ac * 1000, self.min_load_w)
        direct_pv = fraction * min(load, gen_ac)

        return HourlyResult(
            grid_import=load - direct_pv,
            feed_in=gen_ac - direct_pv,
            curtailed=curtailed,
            direct_pv=direct_pv,
            battery_discharge=0.0,
            pv_generation=gen_dc,
            consumption=load,
        )
