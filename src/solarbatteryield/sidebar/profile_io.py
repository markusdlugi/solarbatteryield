"""
CSV profile I/O utilities for expert mode.

Provides template generation and parsing for yearly consumption profiles.
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta

import pandas as pd


def is_leap_year(year: int) -> bool:
    """Check if a year is a leap year."""
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


def get_hours_in_year(year: int) -> int:
    """Get the number of hours in a year (accounting for leap years)."""
    return 8784 if is_leap_year(year) else 8760


def generate_yearly_template_csv(year: int) -> str:
    """
    Generate a CSV template with timestamps for a full year.

    Args:
        year: The year to generate timestamps for (determines leap year handling)

    Returns:
        CSV content as a string with Time and Power(W) columns, semicolon-separated
    """
    num_hours = get_hours_in_year(year)

    # Generate timestamps
    start_dt = datetime(year, 1, 1, 0, 0, 0)
    timestamps = [
        (start_dt + timedelta(hours=h)).strftime("%Y-%m-%d %H:%M")
        for h in range(num_hours)
    ]

    # Create CSV content with semicolon separator
    output = io.StringIO()
    output.write("Time;Power(W)\n")
    for ts in timestamps:
        output.write(f"{ts};\n")

    return output.getvalue()


def parse_yearly_profile_csv(
    uploaded_file, 
    expected_year: int
) -> tuple[list[float] | None, str | None]:
    """
    Parse an uploaded CSV file containing yearly consumption data.

    Args:
        uploaded_file: Streamlit uploaded file object
        expected_year: The expected PVGIS year for validation

    Returns:
        Tuple of (profile_data, error_message). One will be None.
    """
    try:
        # Read CSV with semicolon separator
        df = pd.read_csv(uploaded_file, sep=";")

        # Check required columns
        if len(df.columns) < 2:
            return None, "CSV muss mindestens 2 Spalten haben (Zeit und Leistung)"

        # Get power column (second column)
        power_col = df.columns[1]

        # Check for empty/null values
        if df[power_col].isna().any():
            missing_count = df[power_col].isna().sum()
            return None, f"CSV enthält {missing_count} leere Werte in der Leistungsspalte"

        # Convert to numeric, handling potential string values
        try:
            power_values = pd.to_numeric(df[power_col], errors='coerce')
            if power_values.isna().any():
                return None, "Einige Werte in der Leistungsspalte sind keine gültigen Zahlen"
        except Exception:
            return None, "Fehler beim Parsen der Leistungswerte"

        # Check for expected number of hours
        expected_hours = get_hours_in_year(expected_year)

        if len(power_values) != expected_hours:
            return None, (
                f"CSV enthält {len(power_values)} Zeilen, aber {expected_hours} werden "
                f"für das Jahr {expected_year} erwartet"
            )

        # Check for negative values
        if (power_values < 0).any():
            neg_count = (power_values < 0).sum()
            return None, f"CSV enthält {neg_count} negative Werte"

        return power_values.tolist(), None

    except pd.errors.EmptyDataError:
        return None, "CSV-Datei ist leer"
    except pd.errors.ParserError as e:
        error_msg = str(e).lower()
        if "no columns" in error_msg or "empty" in error_msg:
            return None, "CSV-Datei ist leer"
        return None, f"CSV-Parsing-Fehler: {e}"
    except Exception as e:
        error_msg = str(e).lower()
        if "no columns" in error_msg or "empty" in error_msg:
            return None, "CSV-Datei ist leer"
        return None, f"Unerwarteter Fehler: {e}"


def calculate_profile_stats(profile_data: list[float]) -> dict:
    """
    Calculate statistics for a yearly consumption profile.
    
    Args:
        profile_data: List of hourly power values in Watts
        
    Returns:
        Dictionary with total_kwh, avg_w, max_w, min_w
    """
    return {
        "total_kwh": sum(profile_data) / 1000,
        "avg_w": sum(profile_data) / len(profile_data),
        "max_w": max(profile_data),
        "min_w": min(profile_data),
    }

