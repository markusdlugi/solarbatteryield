"""
Sidebar components for PV analysis application.

This package provides modular sidebar rendering with separate components for:
- Location configuration
- Consumption profiles (simple, advanced, expert modes)
- PV module configuration
- Storage configuration
- Price settings
"""
from solarbatteryield.sidebar.core import render_sidebar

__all__ = ["render_sidebar"]

