# Testing Guidelines for SolarBatterYield

This document describes the testing philosophy and patterns used in this project.

## Core Philosophy

**Test behavior, not implementation.** Tests should verify what the system does, not how it does it. This makes tests more stable and less likely to break when refactoring internal code.

### Key Principles

1. **Component-level testing over unit testing** - Test the public API of components rather than individual internal methods. This prevents brittle tests that break when implementation details change.

2. **Behavior-focused** - Each test should verify a specific behavior that matters to users or the system as a whole.

3. **Simple and readable** - Tests should be easy to understand. If a test is complex, consider adding helper methods to improve readability.

## Naming Convention

All test methods must follow the "should" naming pattern:

```python
def test_should_<expected_behavior>(self):
    """Should <more detailed description of expected behavior>."""
```

Examples:
- `test_should_reject_expert_mode_without_yearly_profile`
- `test_should_increase_grid_import_compared_to_naive`
- `test_should_preserve_total_consumption`

The docstring provides additional context and is displayed in test output.

## Test Structure: Given/When/Then

Every test should have a clear separation between setup, action, and assertion using comments:

```python
def test_should_calculate_correct_consumption(self):
    """Should calculate consumption based on the provided yearly profile values."""
    # given
    constant_load_watts = 500.0
    yearly_profile = [constant_load_watts] * 8760
    params = _create_expert_params(yearly_profile=yearly_profile)
    pv_data = np.zeros(8760)

    # when
    result = simulate(pv_data, cap_gross=0.0, params=params)

    # then
    expected_consumption = constant_load_watts / 1000 * 8760
    assert result.total_consumption == pytest.approx(expected_consumption, rel=0.01)
```

### Guidelines for Given/When/Then

- **given**: Set up all preconditions and inputs
- **when**: Execute the action being tested (usually a single line)
- **then**: Verify the expected outcomes

Keep each section focused. If the given section is too long, consider extracting helper functions.

### Parameterized Tests

When testing the same behavior with different inputs, use `pytest.mark.parametrize`:

```python
@pytest.mark.parametrize("load_w,pv_w", [
    (-100, 500),
    (500, -100),
    (0, 500),
])
def test_should_return_zero_for_invalid_inputs(self, load_w, pv_w):
    """Should return zero fraction for invalid input combinations."""
    # given
    # (parameters provided by decorator)

    # when
    fraction = get_direct_pv_fraction(load_w, pv_w)

    # then
    assert fraction == pytest.approx(0.0)
```

This keeps each test focused on a single assertion while still covering multiple cases.

## Test Organization

### Test Classes

Group related tests into classes based on the behavior being tested:

```python
class TestExpertModeValidation:
    """Tests for configuration validation in expert mode."""
    
class TestExpertModeSimulation:
    """Tests for simulation behavior in expert mode."""

class TestExpertModeWithBattery:
    """Tests for expert mode simulation with battery storage."""
```

### Helper Functions

Create helper functions to reduce duplication and improve readability:

```python
def _create_expert_params(yearly_profile: list[float] | None = None) -> SimulationParams:
    """Create SimulationParams configured for expert mode."""
    return SimulationParams(
        batt_loss_pct=10,
        dc_coupled=True,
        # ... other parameters with sensible defaults
    )
```

Prefix helper functions with underscore to indicate they are test utilities.

### Fixtures

Use pytest fixtures for expensive setup that can be shared across tests:

```python
@pytest.fixture(scope="class")
def simulation_results(self):
    """Run simulations with and without regression for comparison."""
    pv_data = _generate_synthetic_pv_data()
    params = _create_simulation_params()
    # ... run expensive simulations once
    return {"regression": results_regression, "naive": results_naive}
```

### Shared Fixtures (conftest.py)

Common fixtures and helper functions are defined in `conftest.py` and automatically available to all test files:

**Fixtures:**
- `base_simulation_params` - SimulationParams with sensible defaults
- `expert_mode_params` - SimulationParams configured for expert mode
- `zero_pv_data` - 8760 hours of zero PV generation
- `constant_pv_data` - 1kW constant PV generation
- `daytime_pv_data` - 1kW PV during daytime hours (6-18)
- `synthetic_pv_data` - Realistic PV with seasonal variation
- `constant_load_profile` - 200W constant 24-hour profile
- `realistic_load_profile` - Realistic daily consumption pattern

**Factory Functions (importable from conftest):**
```python
from conftest import (
    create_simulation_params,
    create_constant_pv,
    create_daytime_pv,
    create_synthetic_pv_data,
    create_realistic_load_profile,
)

# Use with custom parameters
params = create_simulation_params(
    profile_base=[300] * 24,
    batt_loss_pct=15,
)
pv_data = create_daytime_pv(peak_kw=0.5, hours=744)
```

When a fixture is very specific to a single test module, keep it in that module rather than adding it to conftest.py.

## What to Test

### DO Test

- **Public API behavior** - Configuration validation, simulation results
- **Edge cases** - Zero values, negative inputs, boundary conditions
- **Integration points** - How components work together
- **Business rules** - Energy balance, autarky calculations, savings

### DON'T Test

- **Private methods directly** - Test them through the public API
- **Implementation details** - Don't test internal data structures
- **Third-party libraries** - Assume they work correctly
- **Trivial getters/setters** - Only test if they have logic

## Assertions

### Prefer pytest.approx for Floating Point

```python
# Good
assert result.consumption == pytest.approx(expected, rel=0.01)

# Avoid
assert result.consumption == expected  # May fail due to floating point
```

### Use Descriptive Assertion Messages

```python
assert regression_import > naive_import, (
    f"cap={cap}: regression ({regression_import:.1f}) "
    f"should exceed naive ({naive_import:.1f})"
)
```

## Example: Complete Test File Structure

```python
"""
Tests for the <component> functionality.

<Brief description of what this test file covers>
"""
import pytest
import numpy as np

from models import SimulationParams, SimulationConfig
from simulation import simulate


def _create_test_params(**overrides) -> SimulationParams:
    """Create test parameters with sensible defaults."""
    defaults = {
        "batt_loss_pct": 10,
        "dc_coupled": True,
        # ... other defaults
    }
    defaults.update(overrides)
    return SimulationParams(**defaults)


class TestComponentValidation:
    """Tests for configuration validation."""

    def test_should_reject_invalid_config(self):
        """Should mark configuration as invalid when required field is missing."""
        # given
        config = _create_invalid_config()

        # when
        is_valid, errors = config.is_valid()

        # then
        assert is_valid is False
        assert len(errors) > 0


class TestComponentBehavior:
    """Tests for core component behavior."""

    def test_should_produce_expected_output(self):
        """Should calculate correct output for standard input."""
        # given
        params = _create_test_params()
        input_data = _generate_test_input()

        # when
        result = process(input_data, params)

        # then
        assert result.value == pytest.approx(expected_value, rel=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

## Running Tests

```bash
# Run all tests with verbose output
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_expert_mode.py -v

# Run specific test class
python -m pytest tests/test_expert_mode.py::TestExpertModeValidation -v

# Run with short traceback
python -m pytest tests/ -v --tb=short
```

