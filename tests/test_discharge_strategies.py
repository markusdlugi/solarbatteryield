"""
Unit tests for discharge strategy target resolution.

Tests get_discharge_target() for all three modes (zero_feed_in, base_load,
time_window) including edge cases like midnight wrapping.
"""
import pytest

from solarbatteryield.models import DischargeStrategyConfig, TimeWindow
from solarbatteryield.simulation.battery.strategy import get_discharge_target


# ─── Zero Feed-in Strategy ────────────────────────────────────────────────────


class TestZeroFeedInStrategy:
    """Tests for zero_feed_in discharge mode."""

    def test_should_return_load_as_target(self):
        """Should return the current load as discharge target."""
        # given
        config = DischargeStrategyConfig(mode="zero_feed_in")
        load = 0.5  # kW

        # when
        target = get_discharge_target(hour=12, load=load, config=config)

        # then
        assert target == pytest.approx(load)

    def test_should_return_zero_target_when_load_is_zero(self):
        """Should return zero when there is no load."""
        # given
        config = DischargeStrategyConfig(mode="zero_feed_in")

        # when
        target = get_discharge_target(hour=12, load=0.0, config=config)

        # then
        assert target == pytest.approx(0.0)


# ─── Base Load Strategy ──────────────────────────────────────────────────────


class TestBaseLoadStrategy:
    """Tests for base_load discharge mode."""

    def test_should_return_constant_target_in_kw(self):
        """Should return base_load_w converted to kW regardless of load."""
        # given
        config = DischargeStrategyConfig(mode="base_load", base_load_w=200)

        # when
        target = get_discharge_target(hour=12, load=0.5, config=config)

        # then
        assert target == pytest.approx(0.2)  # 200W = 0.2 kW

    def test_should_be_independent_of_hour(self):
        """Should return the same target for any hour."""
        # given
        config = DischargeStrategyConfig(mode="base_load", base_load_w=500)

        # when/then
        for hour in range(24):
            target = get_discharge_target(hour=hour, load=1.0, config=config)
            assert target == pytest.approx(0.5)

    def test_should_be_independent_of_load(self):
        """Should return the same target regardless of current load."""
        # given
        config = DischargeStrategyConfig(mode="base_load", base_load_w=300)

        # when/then
        for load in [0.0, 0.1, 0.5, 1.0, 5.0]:
            target = get_discharge_target(hour=12, load=load, config=config)
            assert target == pytest.approx(0.3)


# ─── Time Window Strategy ────────────────────────────────────────────────────


class TestTimeWindowStrategy:
    """Tests for time_window discharge mode."""

    def test_should_return_window_power_during_active_window(self):
        """Should return the configured power when hour falls inside a window."""
        # given
        windows = (TimeWindow(start_hour=8, end_hour=16, power_w=400),)
        config = DischargeStrategyConfig(mode="time_window", time_windows=windows)

        # when
        target = get_discharge_target(hour=12, load=0.5, config=config)

        # then
        assert target == pytest.approx(0.4)  # 400W = 0.4 kW

    def test_should_return_zero_outside_active_window(self):
        """Should return 0 when hour is outside all configured windows."""
        # given
        windows = (TimeWindow(start_hour=8, end_hour=16, power_w=400),)
        config = DischargeStrategyConfig(mode="time_window", time_windows=windows)

        # when
        target = get_discharge_target(hour=20, load=0.5, config=config)

        # then
        assert target == pytest.approx(0.0)

    def test_should_handle_midnight_wrap(self):
        """Should handle windows that wrap around midnight (e.g. 22:00–06:00)."""
        # given
        windows = (TimeWindow(start_hour=22, end_hour=6, power_w=100),)
        config = DischargeStrategyConfig(mode="time_window", time_windows=windows)

        # when/then
        # Inside window
        assert get_discharge_target(hour=23, load=0.5, config=config) == pytest.approx(0.1)
        assert get_discharge_target(hour=0, load=0.5, config=config) == pytest.approx(0.1)
        assert get_discharge_target(hour=3, load=0.5, config=config) == pytest.approx(0.1)
        assert get_discharge_target(hour=5, load=0.5, config=config) == pytest.approx(0.1)
        # Outside window
        assert get_discharge_target(hour=6, load=0.5, config=config) == pytest.approx(0.0)
        assert get_discharge_target(hour=12, load=0.5, config=config) == pytest.approx(0.0)
        assert get_discharge_target(hour=21, load=0.5, config=config) == pytest.approx(0.0)

    def test_should_use_first_matching_window_on_overlap(self):
        """Should use the first matching window when windows overlap."""
        # given
        windows = (
            TimeWindow(start_hour=10, end_hour=14, power_w=200),
            TimeWindow(start_hour=12, end_hour=18, power_w=500),
        )
        config = DischargeStrategyConfig(mode="time_window", time_windows=windows)

        # when
        target = get_discharge_target(hour=13, load=0.5, config=config)

        # then — first window matches
        assert target == pytest.approx(0.2)

    def test_should_return_zero_with_empty_windows(self):
        """Should return 0 when no time windows are configured."""
        # given
        config = DischargeStrategyConfig(mode="time_window", time_windows=())

        # when
        target = get_discharge_target(hour=12, load=0.5, config=config)

        # then
        assert target == pytest.approx(0.0)

    def test_should_support_multiple_non_overlapping_windows(self):
        """Should return correct power for different non-overlapping windows."""
        # given
        windows = (
            TimeWindow(start_hour=6, end_hour=10, power_w=100),
            TimeWindow(start_hour=17, end_hour=22, power_w=300),
        )
        config = DischargeStrategyConfig(mode="time_window", time_windows=windows)

        # when/then
        assert get_discharge_target(hour=8, load=0.5, config=config) == pytest.approx(0.1)
        assert get_discharge_target(hour=19, load=0.5, config=config) == pytest.approx(0.3)
        assert get_discharge_target(hour=12, load=0.5, config=config) == pytest.approx(0.0)

    def test_should_handle_window_start_equals_end(self):
        """Should treat start==end as a 24-hour window (full day)."""
        # given — start == end wraps fully
        windows = (TimeWindow(start_hour=0, end_hour=0, power_w=250),)
        config = DischargeStrategyConfig(mode="time_window", time_windows=windows)

        # when/then — every hour matches (wraps from 0 to 0 = all hours)
        for hour in range(24):
            target = get_discharge_target(hour=hour, load=0.5, config=config)
            assert target == pytest.approx(0.25), f"hour={hour}"


# ─── Unknown Mode ────────────────────────────────────────────────────────────


class TestUnknownMode:
    """Tests for unknown/invalid strategy modes."""

    def test_should_fall_back_to_load_for_unknown_mode(self):
        """Should fall back to zero-feed-in behaviour for unknown modes."""
        # given
        config = DischargeStrategyConfig(mode="totally_unknown")

        # when
        target = get_discharge_target(hour=12, load=0.5, config=config)

        # then
        assert target == pytest.approx(0.5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
