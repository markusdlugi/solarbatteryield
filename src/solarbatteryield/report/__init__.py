"""
Report components for PV analysis visualization.

This package provides modular report rendering with separate components for:
- Tables (scenario overview, incremental analysis, summary)
- Charts (monthly energy balance, SoC comparison, longterm PV vs ETF)
- Header and footer sections
"""
from solarbatteryield.report.core import Report, render_report
from solarbatteryield.report.landing import render_landing_page

__all__ = [
    "Report",
    "render_report",
    "render_landing_page",
]

