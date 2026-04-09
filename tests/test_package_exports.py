"""
Tests for report and sidebar package public API exports.

Ensures that the refactored packages export all expected symbols
and that imports work correctly after the modular restructuring.
"""
import pytest


class TestReportPackageExports:
    """Tests for report package public API."""

    def test_should_export_render_report(self):
        """Should export render_report function from package root."""
        # when
        from solarbatteryield.report import render_report

        # then
        assert callable(render_report)

    def test_should_export_report_class(self):
        """Should export Report class from package root."""
        # when
        from solarbatteryield.report import Report

        # then
        assert Report is not None

    def test_should_export_render_landing_page(self):
        """Should export render_landing_page from package root."""
        # when
        from solarbatteryield.report import render_landing_page

        # then
        assert callable(render_landing_page)

    def test_should_import_report_context(self):
        """Should allow importing ReportContext from submodule."""
        # when
        from solarbatteryield.report.context import ReportContext

        # then
        assert ReportContext is not None

    def test_should_import_chart_config(self):
        """Should allow importing chart config utilities from submodule."""
        # when
        from solarbatteryield.report.chart_config import GERMAN_LOCALE, configure_german_locale

        # then
        assert GERMAN_LOCALE is not None
        assert callable(configure_german_locale)

    def test_should_import_header_component(self):
        """Should allow importing header render function from submodule."""
        # when
        from solarbatteryield.report.header import render_header

        # then
        assert callable(render_header)

    def test_should_import_table_components(self):
        """Should allow importing all table render functions from submodule."""
        # when
        from solarbatteryield.report.tables import (
            render_scenario_overview,
            render_incremental_analysis,
            render_scenario_details,
            render_summary,
        )

        # then
        assert callable(render_scenario_overview)
        assert callable(render_incremental_analysis)
        assert callable(render_scenario_details)
        assert callable(render_summary)

    def test_should_import_monthly_chart_component(self):
        """Should allow importing monthly chart render function from submodule."""
        # when
        from solarbatteryield.report.monthly_chart import render_monthly_energy_balance

        # then
        assert callable(render_monthly_energy_balance)

    def test_should_import_soc_chart_component(self):
        """Should allow importing SoC chart render function from submodule."""
        # when
        from solarbatteryield.report.soc_chart import render_weekly_soc_comparison

        # then
        assert callable(render_weekly_soc_comparison)

    def test_should_import_longterm_chart_component(self):
        """Should allow importing longterm chart render function from submodule."""
        # when
        from solarbatteryield.report.longterm_chart import render_longterm_comparison

        # then
        assert callable(render_longterm_comparison)

    def test_should_import_footer_component(self):
        """Should allow importing footer render functions from submodule."""
        # when
        from solarbatteryield.report.footer import render_share_button, render_data_attribution

        # then
        assert callable(render_share_button)
        assert callable(render_data_attribution)

    def test_should_import_landing_page_component(self):
        """Should allow importing landing page component from submodule."""
        # when
        from solarbatteryield.report.landing import render_landing_page

        # then
        assert callable(render_landing_page)


class TestSidebarPackageExports:
    """Tests for sidebar package public API."""

    def test_should_export_render_sidebar(self):
        """Should export render_sidebar function from package root."""
        # when
        from solarbatteryield.sidebar import render_sidebar

        # then
        assert callable(render_sidebar)

    def test_should_import_location_component(self):
        """Should allow importing location render function from submodule."""
        # when
        from solarbatteryield.sidebar.location import render_location_section

        # then
        assert callable(render_location_section)

    def test_should_import_consumption_component(self):
        """Should allow importing consumption render function from submodule."""
        # when
        from solarbatteryield.sidebar.consumption import render_consumption_section

        # then
        assert callable(render_consumption_section)

    def test_should_import_pv_config_components(self):
        """Should allow importing PV config render functions from submodule."""
        # when
        from solarbatteryield.sidebar.pv_config import (
            render_pv_modules_section,
            render_pv_config_section,
        )

        # then
        assert callable(render_pv_modules_section)
        assert callable(render_pv_config_section)

    def test_should_import_storage_config_components(self):
        """Should allow importing storage config render functions from submodule."""
        # when
        from solarbatteryield.sidebar.storage_config import (
            render_storage_options_section,
            render_storage_config_section,
        )

        # then
        assert callable(render_storage_options_section)
        assert callable(render_storage_config_section)

    def test_should_import_prices_component(self):
        """Should allow importing prices render function from submodule."""
        # when
        from solarbatteryield.sidebar.prices import render_prices_section

        # then
        assert callable(render_prices_section)

    def test_should_import_profile_io_functions(self):
        """Should allow importing profile I/O functions from submodule."""
        # when
        from solarbatteryield.sidebar.profile_io import (
            is_leap_year,
            get_hours_in_year,
            generate_yearly_template_csv,
            parse_yearly_profile_csv,
            calculate_profile_stats,
        )

        # then
        assert callable(is_leap_year)
        assert callable(get_hours_in_year)
        assert callable(generate_yearly_template_csv)
        assert callable(parse_yearly_profile_csv)
        assert callable(calculate_profile_stats)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

