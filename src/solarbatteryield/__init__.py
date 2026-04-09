"""
SolarBatterYield - PV Analysis Application

A Streamlit application for analyzing PV systems with battery storage.
Compares different storage configurations and investment scenarios.
"""

__version__ = "0.1.0"

# Pre-import modules to ensure they are fully loaded before concurrent access.
# This prevents race conditions with @dataclass decorators on Streamlit Cloud.
# Order matters: import dependencies before dependents.
# Use relative imports to avoid KeyError during package initialization.
from .simulation import inverter_efficiency  # noqa: F401  - needed by models, simulation
from .simulation import h0_profile  # noqa: F401  - needed by config, simulation
from .simulation import load_regression  # noqa: F401  - JSON loaded at module level
from . import config  # noqa: F401  - needed by state, sidebar, report
from . import models  # noqa: F401  - needed by simulation, report
