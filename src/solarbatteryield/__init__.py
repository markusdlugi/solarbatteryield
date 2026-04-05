"""
SolarBatterYield - PV Analysis Application

A Streamlit application for analyzing PV systems with battery storage.
Compares different storage configurations and investment scenarios.
"""

__version__ = "0.1.0"

# Pre-import modules to ensure they are fully loaded before concurrent access.
# This prevents race conditions with @dataclass decorators on Streamlit Cloud.
from solarbatteryield import h0_profile  # noqa: F401
from solarbatteryield import config  # noqa: F401
from solarbatteryield import models  # noqa: F401
