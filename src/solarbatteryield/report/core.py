"""
Core Report class that orchestrates all report components.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from solarbatteryield.report.context import ReportContext
from solarbatteryield.report.header import render_header
from solarbatteryield.report.tables import (
    render_scenario_overview,
    render_incremental_analysis,
    render_scenario_details,
    render_summary,
)
from solarbatteryield.report.monthly_chart import render_monthly_energy_balance
from solarbatteryield.report.soc_chart import render_weekly_soc_comparison
from solarbatteryield.report.longterm_chart import render_longterm_comparison
from solarbatteryield.report.footer import render_share_button

if TYPE_CHECKING:
    from solarbatteryield.models import SimulationConfig, AnalysisResult


class Report:
    """
    Renders the complete PV analysis report.
    
    Orchestrates all report components in the correct order,
    using a shared ReportContext for configuration and results.
    """

    def __init__(self, config: SimulationConfig, results: AnalysisResult) -> None:
        """
        Initialize the report with configuration and results.
        
        Args:
            config: Simulation configuration
            results: Analysis results with all scenarios
        """
        self.ctx = ReportContext(config=config, results=results)

    def render(self) -> None:
        """Render the complete analysis report."""
        render_header(self.ctx)
        render_scenario_overview(self.ctx)
        render_monthly_energy_balance(self.ctx)
        render_weekly_soc_comparison(self.ctx)
        render_incremental_analysis(self.ctx)
        render_longterm_comparison(self.ctx)
        render_scenario_details(self.ctx)
        render_summary(self.ctx)
        render_share_button()


def render_report(config: SimulationConfig, results: AnalysisResult) -> None:
    """
    Convenience function to create and render a report.
    
    Args:
        config: Simulation configuration
        results: Analysis results with all scenarios
    """
    Report(config, results).render()

