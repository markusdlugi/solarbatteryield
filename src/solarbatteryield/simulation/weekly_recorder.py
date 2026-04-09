"""
Weekly SoC data recording for representative weeks.

Captures hourly battery state-of-charge during one summer, one winter,
and one transition week for detailed SoC visualisation.
"""
from __future__ import annotations

from solarbatteryield.models import WeeklyHourlyData
from solarbatteryield.simulation.battery import Battery


class WeeklySoCRecorder:
    """Records hourly SoC data for three representative weeks per season.

    Weeks selected (0-indexed day-of-year):
      - Summer:     July 1–7
      - Transition: April 8–14
      - Winter:     Jan 8–14

    Becomes a no-op when cap_gross <= 0 (no battery).
    """

    def __init__(self, data_year: int, cap_gross: float) -> None:
        self._active = cap_gross > 0
        if not self._active:
            self._summer = None
            self._transition = None
            self._winter = None
            return

        is_leap = data_year % 4 == 0 and (data_year % 100 != 0 or data_year % 400 == 0)

        summer_start = (182 if not is_leap else 183) * 24
        transition_start = (98 if not is_leap else 99) * 24
        winter_start = 7 * 24

        self._summer = _WeekWindow(WeeklyHourlyData(), summer_start)
        self._transition = _WeekWindow(WeeklyHourlyData(), transition_start)
        self._winter = _WeekWindow(WeeklyHourlyData(), winter_start)
        self._windows = (self._summer, self._transition, self._winter)

    def record(self, hour_index: int, battery: Battery,
               pv_generation: float, consumption: float) -> None:
        """Record SoC data if *hour_index* falls within a tracked week."""
        if not self._active:
            return
        for w in self._windows:
            if w.hour_start <= hour_index < w.hour_end:
                w.data.add_hour(
                    hour=hour_index - w.hour_start,
                    soc=battery.soc,
                    soc_pct=battery.soc_pct,
                    pv_generation=pv_generation,
                    consumption=consumption,
                )

    @property
    def weekly_summer(self) -> WeeklyHourlyData | None:
        return self._summer.data if self._summer else None

    @property
    def weekly_transition(self) -> WeeklyHourlyData | None:
        return self._transition.data if self._transition else None

    @property
    def weekly_winter(self) -> WeeklyHourlyData | None:
        return self._winter.data if self._winter else None


class _WeekWindow:
    """Internal helper: a 168-hour window with its data collector."""
    __slots__ = ("data", "hour_start", "hour_end")

    def __init__(self, data: WeeklyHourlyData, hour_start: int) -> None:
        self.data = data
        self.hour_start = hour_start
        self.hour_end = hour_start + 168

