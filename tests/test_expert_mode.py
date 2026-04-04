"""
Tests for the expert mode (yearly profile) functionality.
"""
import pytest
from datetime import date

from models import SimulationParams, ConsumptionConfig, SimulationConfig
from inverter_efficiency import DEFAULT_INVERTER_EFFICIENCY_CURVE
from simulation import _calculate_hourly_load


class TestConsumptionConfig:
    """Tests for ConsumptionConfig expert mode methods."""
    
    def test_has_yearly_profile_true(self):
        """Test that has_yearly_profile returns True when profile is set."""
        config = ConsumptionConfig(
            profile_mode="Experte",
            yearly_profile=[100.0] * 8760
        )
        assert config.has_yearly_profile() is True
    
    def test_has_yearly_profile_false_none(self):
        """Test that has_yearly_profile returns False when profile is None."""
        config = ConsumptionConfig(profile_mode="Experte", yearly_profile=None)
        assert config.has_yearly_profile() is False
    
    def test_has_yearly_profile_false_empty(self):
        """Test that has_yearly_profile returns False when profile is empty."""
        config = ConsumptionConfig(profile_mode="Experte", yearly_profile=[])
        assert config.has_yearly_profile() is False


class TestSimulationParams:
    """Tests for SimulationParams expert mode methods."""
    
    @pytest.fixture
    def expert_params(self):
        """Create SimulationParams for expert mode."""
        return SimulationParams(
            batt_loss_pct=10,
            dc_coupled=True,
            min_soc_summer_pct=10,
            min_soc_winter_pct=20,
            max_soc_summer_pct=100,
            max_soc_winter_pct=100,
            data_year=2015,
            inverter_limit_kw=0.8,
            inverter_efficiency_curve=((10, 0.91), (100, 0.96)),
            batt_inverter_efficiency_curve=DEFAULT_INVERTER_EFFICIENCY_CURVE,
            profile_mode="Experte",
            annual_kwh=None,
            profile_base=[100] * 24,
            profile_saturday=None,
            profile_sunday=None,
            yearly_profile=[150.0] * 8760,
            seasonal_enabled=False,
            season_winter_pct=100,
            season_summer_pct=100,
            flex_load_enabled=False,
            flex_min_yield=5.0,
            flex_pool_size=3,
            flex_delta=[0] * 24,
            flex_refresh_rate=0.5,
            periodic_load_enabled=False,
            periodic_delta=[0] * 24,
            periodic_interval_days=3,
        )
    
    def test_use_yearly_profile_true(self, expert_params):
        """Test use_yearly_profile returns True for expert mode with profile."""
        assert expert_params.use_yearly_profile() is True
    
    def test_use_h0_profile_false_in_expert_mode(self, expert_params):
        """Test use_h0_profile returns False for expert mode."""
        assert expert_params.use_h0_profile() is False
    
    def test_use_yearly_profile_false_without_profile(self):
        """Test use_yearly_profile returns False when no profile set."""
        params = SimulationParams(
            batt_loss_pct=10,
            dc_coupled=True,
            min_soc_summer_pct=10,
            min_soc_winter_pct=20,
            max_soc_summer_pct=100,
            max_soc_winter_pct=100,
            data_year=2015,
            inverter_limit_kw=0.8,
            inverter_efficiency_curve=((10, 0.91), (100, 0.96)),
            batt_inverter_efficiency_curve=DEFAULT_INVERTER_EFFICIENCY_CURVE,
            profile_mode="Experte",
            annual_kwh=None,
            profile_base=[100] * 24,
            profile_saturday=None,
            profile_sunday=None,
            yearly_profile=None,  # No profile
            seasonal_enabled=False,
            season_winter_pct=100,
            season_summer_pct=100,
            flex_load_enabled=False,
            flex_min_yield=5.0,
            flex_pool_size=3,
            flex_delta=[0] * 24,
            flex_refresh_rate=0.5,
            periodic_load_enabled=False,
            periodic_delta=[0] * 24,
            periodic_interval_days=3,
        )
        assert params.use_yearly_profile() is False


class TestCalculateHourlyLoadExpert:
    """Tests for _calculate_hourly_load with expert mode."""
    
    @pytest.fixture
    def expert_params(self):
        """Create SimulationParams for expert mode with varying profile."""
        # Create a profile where each hour has a unique value for easy testing
        yearly_profile = [float(i * 10) for i in range(8760)]
        return SimulationParams(
            batt_loss_pct=10,
            dc_coupled=True,
            min_soc_summer_pct=10,
            min_soc_winter_pct=20,
            max_soc_summer_pct=100,
            max_soc_winter_pct=100,
            data_year=2015,
            inverter_limit_kw=0.8,
            inverter_efficiency_curve=((10, 0.91), (100, 0.96)),
            batt_inverter_efficiency_curve=DEFAULT_INVERTER_EFFICIENCY_CURVE,
            profile_mode="Experte",
            annual_kwh=None,
            profile_base=[100] * 24,
            profile_saturday=None,
            profile_sunday=None,
            yearly_profile=yearly_profile,
            seasonal_enabled=False,
            season_winter_pct=100,
            season_summer_pct=100,
            flex_load_enabled=False,
            flex_min_yield=5.0,
            flex_pool_size=3,
            flex_delta=[0] * 24,
            flex_refresh_rate=0.5,
            periodic_load_enabled=False,
            periodic_delta=[0] * 24,
            periodic_interval_days=3,
        )
    
    def test_load_from_yearly_profile_hour_0(self, expert_params):
        """Test load is read from yearly profile at hour 0."""
        current_date = date(2015, 1, 1)
        load = _calculate_hourly_load(
            hour=0,
            current_date=current_date,
            params=expert_params,
            day=0,
            use_flex_today=False,
            hour_index=0
        )
        # Profile value is 0 * 10 = 0 W, converted to kWh = 0
        assert load == 0.0
    
    def test_load_from_yearly_profile_hour_100(self, expert_params):
        """Test load is read from yearly profile at hour 100."""
        current_date = date(2015, 1, 5)  # Day 4, hour 4 = index 100
        load = _calculate_hourly_load(
            hour=4,
            current_date=current_date,
            params=expert_params,
            day=4,
            use_flex_today=False,
            hour_index=100
        )
        # Profile value is 100 * 10 = 1000 W, converted to kWh = 1.0
        assert load == 1.0
    
    def test_load_with_flex_load(self, expert_params):
        """Test flex load is added to yearly profile load."""
        # Set up flex delta
        expert_params.flex_delta[5] = 500  # 500W additional at hour 5
        
        current_date = date(2015, 1, 1)
        load = _calculate_hourly_load(
            hour=5,
            current_date=current_date,
            params=expert_params,
            day=0,
            use_flex_today=True,  # Flex is active
            hour_index=5
        )
        # Profile: 5 * 10 = 50 W = 0.05 kWh
        # Flex: 500 W = 0.5 kWh
        # Total: 0.55 kWh
        assert load == pytest.approx(0.55)
    
    def test_load_with_periodic_load(self, expert_params):
        """Test periodic load is added to yearly profile load."""
        expert_params.periodic_load_enabled = True
        expert_params.periodic_interval_days = 3
        expert_params.periodic_delta[10] = 200  # 200W additional at hour 10
        
        current_date = date(2015, 1, 1)
        # Day 0 should trigger periodic load (0 % 3 == 0)
        load = _calculate_hourly_load(
            hour=10,
            current_date=current_date,
            params=expert_params,
            day=0,
            use_flex_today=False,
            hour_index=10
        )
        # Profile: 10 * 10 = 100 W = 0.1 kWh
        # Periodic: 200 W = 0.2 kWh
        # Total: 0.3 kWh
        assert load == pytest.approx(0.3)


class TestSimulationConfigValidation:
    """Tests for SimulationConfig validation with expert mode."""
    
    def test_invalid_without_yearly_profile(self):
        """Test that expert mode without profile is invalid."""
        from models import LocationConfig, PVSystemConfig, StorageConfig, EconomicsConfig
        
        config = SimulationConfig(
            location=LocationConfig(lat=48.0, lon=11.0),
            consumption=ConsumptionConfig(
                profile_mode="Experte",
                yearly_profile=None,
            ),
            pv_system=PVSystemConfig(),
            storage=StorageConfig(),
            economics=EconomicsConfig(),
        )
        
        is_valid, missing = config.is_valid()
        assert is_valid is False
        assert any("Jahreslastprofil" in m for m in missing)
    
    def test_valid_with_yearly_profile(self):
        """Test that expert mode with profile is valid."""
        from models import LocationConfig, PVSystemConfig, StorageConfig, EconomicsConfig
        
        config = SimulationConfig(
            location=LocationConfig(lat=48.0, lon=11.0),
            consumption=ConsumptionConfig(
                profile_mode="Experte",
                yearly_profile=[100.0] * 8760,
            ),
            pv_system=PVSystemConfig(),
            storage=StorageConfig(),
            economics=EconomicsConfig(),
        )
        
        is_valid, missing = config.is_valid()
        assert is_valid is True
        assert len(missing) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

