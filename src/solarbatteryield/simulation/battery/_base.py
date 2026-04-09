"""
Abstract base class for battery implementations.

Encapsulates SoC state, efficiency curves, and the process_hour() contract.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from solarbatteryield.models import HourlyResult
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
    ) -> None:
        self.cap_gross = cap_gross
        self.batt_eff = batt_eff
        self.inv_cap = inv_cap
        self.inv_eff_curve = inv_eff_curve

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

