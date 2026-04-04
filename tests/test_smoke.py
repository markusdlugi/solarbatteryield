"""
Smoke tests for the Streamlit application.

These tests verify that the application can start and initialize without errors.
They do not test specific functionality but ensure the basic infrastructure works.
"""
import subprocess
import sys
import time

import pytest


class TestStreamlitAppStartup:
    """Tests verifying the Streamlit app can start successfully."""

    @pytest.fixture(scope="class")
    def streamlit_process(self):
        """Start the Streamlit app in a subprocess and yield the process."""
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "src/solarbatteryield/streamlit_app.py",
                "--server.headless=true",
                "--server.port=8599",
                "--browser.serverAddress=localhost",
                "--logger.level=error",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        
        # Give the app time to start
        time.sleep(5)
        
        yield process
        
        # Cleanup: terminate the process
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    def test_should_start_without_errors(self, streamlit_process):
        """Should start the Streamlit app without immediate crashes."""
        # given
        process = streamlit_process

        # when
        poll_result = process.poll()

        # then
        assert poll_result is None, (
            f"Streamlit process exited unexpectedly with code {poll_result}. "
            f"stderr: {process.stderr.read() if process.stderr else 'N/A'}"
        )

    def test_should_respond_to_health_check(self, streamlit_process):
        """Should respond to HTTP requests on the configured port."""
        # given
        import socket
        
        # when
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        
        try:
            result = sock.connect_ex(("localhost", 8599))
        finally:
            sock.close()

        # then
        assert result == 0, "Streamlit server is not accepting connections on port 8599"


class TestModuleImports:
    """Tests verifying all application modules can be imported."""

    def test_should_import_streamlit_app_module(self):
        """Should import the main streamlit_app module without errors."""
        # when/then
        from solarbatteryield import streamlit_app
        assert streamlit_app is not None

    def test_should_import_simulation_module(self):
        """Should import the simulation module without errors."""
        # when/then
        from solarbatteryield.simulation import simulate
        assert simulate is not None

    def test_should_import_models_module(self):
        """Should import the models module without errors."""
        # when/then
        from solarbatteryield.models import SimulationConfig, SimulationParams, SimulationResult
        assert SimulationConfig is not None

    def test_should_import_api_module(self):
        """Should import the API module without errors."""
        # when/then
        from solarbatteryield.api import get_pvgis_hourly
        assert get_pvgis_hourly is not None

    def test_should_import_h0_profile_module(self):
        """Should import the H0 profile module without errors."""
        # when/then
        from solarbatteryield.h0_profile import get_h0_load
        assert get_h0_load is not None

    def test_should_import_inverter_efficiency_module(self):
        """Should import the inverter efficiency module without errors."""
        # when/then
        from solarbatteryield.inverter_efficiency import get_inverter_efficiency
        assert get_inverter_efficiency is not None

    def test_should_import_load_regression_module(self):
        """Should import the load regression module without errors."""
        # when/then
        from solarbatteryield.load_regression import get_direct_pv_fraction
        assert get_direct_pv_fraction is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
