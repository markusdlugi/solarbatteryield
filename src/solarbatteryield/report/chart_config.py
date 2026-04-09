"""
Altair chart configuration helpers.

Provides shared configuration for German locale and consistent styling
across all charts in the report.
"""
from __future__ import annotations

from typing import Any

# German locale configuration for Altair charts
GERMAN_LOCALE: dict[str, Any] = {
    "number": {
        "decimal": ",",
        "thousands": ".",
        "grouping": [3],
        "currency": ["", " €"],
    }
}


def configure_german_locale(chart):
    """
    Apply German locale configuration to an Altair chart.
    
    Args:
        chart: Altair chart object
        
    Returns:
        Chart with German locale configuration applied
    """
    return chart.configure(locale=GERMAN_LOCALE)

