"""
Discharge strategy target resolution.

Determines the AC-side system output target per hour based on the configured
discharge strategy. The Battery subclasses use this target to decide how much
energy to discharge.
"""
from __future__ import annotations

from solarbatteryield.models import DischargeStrategyConfig


def get_discharge_target(
        hour: int,
        load: float,
        config: DischargeStrategyConfig,
) -> float:
    """
    Determine the AC-side target output of the PV+battery system in kW.

    - ``zero_feed_in``: target = load (track consumption via smart meter)
    - ``base_load``:    target = base_load_w / 1000 (constant output)
    - ``time_window``:  target = active window's power_w / 1000, or 0.0

    Args:
        hour: Hour of the day (0–23).
        load: Current hourly load in kW.
        config: Discharge strategy configuration.

    Returns:
        Target AC output in kW.
    """
    if config.mode == "zero_feed_in":
        return load
    if config.mode == "base_load":
        return config.base_load_w / 1000
    if config.mode == "time_window":
        for w in config.time_windows:
            if _hour_in_window(hour, w.start_hour, w.end_hour):
                return w.power_w / 1000
        return 0.0
    # Unknown mode — fall back to zero-feed-in behaviour
    return load


def _hour_in_window(hour: int, start: int, end: int) -> bool:
    """Check whether *hour* falls inside [start, end) with midnight wrap."""
    if start == end:
        # start == end means "all 24 hours"
        return True
    if start < end:
        return start <= hour < end
    # Wraps around midnight, e.g. 22:00–06:00
    return hour >= start or hour < end
