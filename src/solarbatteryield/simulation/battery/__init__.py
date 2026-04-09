"""
Battery abstraction for the simulation engine.

Provides a Battery ABC and concrete implementations for different coupling types.
The factory function create_battery() selects the right subclass based on config.
"""
from __future__ import annotations

from solarbatteryield.simulation.battery._base import Battery
from solarbatteryield.simulation.battery._no_battery import NoBattery
from solarbatteryield.simulation.battery._dc_coupled import DcCoupledBattery
from solarbatteryield.simulation.battery._ac_coupled import AcCoupledBattery
from solarbatteryield.simulation.inverter_efficiency import DEFAULT_INVERTER_EFFICIENCY_CURVE


def create_battery(
    cap_gross: float,
    batt_eff: float,
    inv_cap: float,
    inv_eff_curve: tuple[tuple[int, float], ...],
    dc_coupled: bool,
    batt_inv_eff_curve: tuple[tuple[int, float], ...] = DEFAULT_INVERTER_EFFICIENCY_CURVE,
) -> Battery:
    """
    Factory: create the appropriate Battery instance.

    Returns NoBattery when cap_gross <= 0, otherwise DcCoupledBattery or
    AcCoupledBattery depending on dc_coupled flag.
    """
    if cap_gross <= 0:
        return NoBattery(
            cap_gross=0.0,
            batt_eff=batt_eff,
            inv_cap=inv_cap,
            inv_eff_curve=inv_eff_curve,
        )
    if dc_coupled:
        return DcCoupledBattery(
            cap_gross=cap_gross,
            batt_eff=batt_eff,
            inv_cap=inv_cap,
            inv_eff_curve=inv_eff_curve,
        )
    return AcCoupledBattery(
        cap_gross=cap_gross,
        batt_eff=batt_eff,
        inv_cap=inv_cap,
        inv_eff_curve=inv_eff_curve,
        batt_inv_eff_curve=batt_inv_eff_curve,
    )


__all__ = [
    "Battery",
    "NoBattery",
    "DcCoupledBattery",
    "AcCoupledBattery",
    "create_battery",
]

