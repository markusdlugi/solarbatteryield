"""
Weekly State of Charge (SoC) comparison chart component.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import altair as alt
import pandas as pd
import streamlit as st

from solarbatteryield.config import COLORS
from solarbatteryield.report.chart_config import configure_german_locale

if TYPE_CHECKING:
    from solarbatteryield.models import ScenarioResult
    from solarbatteryield.report.context import ReportContext


# Day labels for the weekly chart x-axis
DAY_LABELS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def render_weekly_soc_comparison(ctx: ReportContext) -> None:
    """
    Render weekly SoC comparison charts for summer, winter, and transition seasons.
    
    Shows how battery state of charge evolves over a typical week, with PV
    generation and consumption as background areas.
    
    Args:
        ctx: Report context with config and results
    """
    # Check if any scenario has battery storage and sort by capacity
    storage_scenarios = sorted(
        [s for s in ctx.scenarios if s.storage_capacity > 0],
        key=lambda s: s.storage_capacity
    )
    if not storage_scenarios:
        return

    st.header("🌤️ Speicher-Ladezustand pro Jahreszeit")
    st.caption(
        "Der Verlauf des Ladezustands (SoC) über eine typische Woche zeigt, wie gut die Speichergröße "
        "zum Verbrauchsprofil passt. Zu große Speicher bleiben im Sommer dauerhaft voll, "
        "zu kleine sind in der Übergangszeit oft noch vor Mitternacht leer."
    )

    # Calculate consistent y-axis maximum across all seasons
    energy_max = _calculate_energy_max(storage_scenarios)

    # Create tabs for summer, transition, and winter
    summer_tab, transition_tab, winter_tab = st.tabs([
        "☀️ Sommer (Juli)",
        "🌤️ Übergang (April)",
        "❄️ Winter (Januar)"
    ])

    with summer_tab:
        _render_soc_week_chart(storage_scenarios, "summer", "Juli", energy_max)

    with transition_tab:
        _render_soc_week_chart(storage_scenarios, "transition", "April", energy_max)

    with winter_tab:
        _render_soc_week_chart(storage_scenarios, "winter", "Januar", energy_max)


def _calculate_energy_max(scenarios: list[ScenarioResult]) -> float:
    """Calculate the maximum energy value for consistent y-axis scaling."""
    energy_max = 0.0
    for scenario in scenarios:
        for weekly_data in [
            scenario.simulation.weekly_summer,
            scenario.simulation.weekly_transition,
            scenario.simulation.weekly_winter
        ]:
            if weekly_data is not None and weekly_data.hours:
                for data in weekly_data.hours:
                    energy_max = max(energy_max, data.pv_generation, data.consumption)
    return max(energy_max * 1.1, 0.1)  # Add 10% headroom, ensure minimum


def _render_soc_week_chart(
    scenarios: list[ScenarioResult],
    season: str,
    month_name: str,
    energy_max: float
) -> None:
    """
    Render a single SoC week chart for all scenarios in a given season.
    
    Args:
        scenarios: List of scenarios with battery storage
        season: Season identifier ("summer", "transition", "winter")
        month_name: Display name for the month
        energy_max: Maximum energy value for y-axis scaling
    """
    # Collect data from all scenarios
    soc_rows = []
    background_rows = []

    for scenario in scenarios:
        if season == "summer":
            weekly_data = scenario.simulation.weekly_summer
        elif season == "transition":
            weekly_data = scenario.simulation.weekly_transition
        else:
            weekly_data = scenario.simulation.weekly_winter

        if weekly_data is None or not weekly_data.hours:
            continue

        for data in weekly_data.hours:
            day_idx = data.hour // 24
            hour_of_day = data.hour % 24
            day_label = DAY_LABELS[day_idx] if day_idx < len(DAY_LABELS) else f"Tag {day_idx + 1}"

            soc_rows.append({
                "Stunde": data.hour,
                "Tag": day_label,
                "Uhrzeit": f"{hour_of_day:02d}:00",
                "SoC (%)": data.soc_pct,
                "Szenario": scenario.name,
                "Speicher (kWh)": scenario.storage_capacity,
            })

            # Only add PV/consumption data once (it's the same for all scenarios)
            if scenario == scenarios[-1]:
                background_rows.append({
                    "Stunde": data.hour,
                    "PV (kWh)": data.pv_generation,
                    "Verbrauch (kWh)": data.consumption,
                })

    if not soc_rows:
        st.info(f"Keine Daten für {month_name} verfügbar.")
        return

    soc_df = pd.DataFrame(soc_rows)
    background_df = pd.DataFrame(background_rows)

    # Generate blue color scale for storage scenarios (light to dark)
    num_scenarios = len(scenarios)
    blue_colors = COLORS.soc_color_scale(num_scenarios)
    scenario_names = [s.name for s in scenarios]

    # Common x-axis configuration (7 days * 24 hours = 168 hours)
    x_axis = alt.X(
        "Stunde:Q",
        title="Wochentag",
        axis=alt.Axis(
            values=[0, 24, 48, 72, 96, 120, 144],
            labelExpr="['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'][floor(datum.value / 24)]",
        ),
        scale=alt.Scale(domain=[0, 167], nice=False),
    )

    # SoC lines for each scenario
    soc_chart = (
        alt.Chart(soc_df)
        .mark_line(strokeWidth=2)
        .encode(
            x=x_axis,
            y=alt.Y(
                "SoC (%):Q",
                title="Ladezustand (%)",
                scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(titleColor=COLORS.soc_axis_title),
            ),
            color=alt.Color(
                "Szenario:N",
                title="Speicher",
                legend=alt.Legend(orient="bottom"),
                sort=scenario_names,
                scale=alt.Scale(domain=scenario_names, range=blue_colors),
            ),
            order=alt.Order("Speicher (kWh):Q", sort="ascending"),
            tooltip=[
                alt.Tooltip("Szenario:N"),
                alt.Tooltip("Tag:N"),
                alt.Tooltip("Uhrzeit:N"),
                alt.Tooltip("SoC (%):Q", format=".1f"),
                alt.Tooltip("Speicher (kWh):Q", format=".1f"),
            ],
        )
    )

    # PV generation as area chart
    pv_chart = (
        alt.Chart(background_df)
        .mark_area(opacity=0.4, color=COLORS.soc_pv_area)
        .encode(
            x=alt.X("Stunde:Q", scale=alt.Scale(domain=[0, 167], nice=False)),
            y=alt.Y(
                "PV (kWh):Q",
                title="PV / Verbrauch (kWh)",
                scale=alt.Scale(domain=[0, energy_max]),
                axis=alt.Axis(titleColor=COLORS.soc_axis_title),
            ),
            tooltip=[
                alt.Tooltip("Stunde:Q", title="Stunde"),
                alt.Tooltip("PV (kWh):Q", format=".2f", title="PV-Erzeugung"),
            ],
        )
    )

    # Consumption as area chart
    consumption_chart = (
        alt.Chart(background_df)
        .mark_area(opacity=0.4, color=COLORS.soc_consumption_area)
        .encode(
            x=alt.X("Stunde:Q", scale=alt.Scale(domain=[0, 167], nice=False)),
            y=alt.Y(
                "Verbrauch (kWh):Q",
                scale=alt.Scale(domain=[0, energy_max]),
            ),
            tooltip=[
                alt.Tooltip("Stunde:Q", title="Stunde"),
                alt.Tooltip("Verbrauch (kWh):Q", format=".2f", title="Verbrauch"),
            ],
        )
    )

    # Vertical lines for day boundaries
    day_boundaries = pd.DataFrame({"Stunde": [24, 48, 72, 96, 120, 144]})
    day_rules = (
        alt.Chart(day_boundaries)
        .mark_rule(strokeDash=[4, 4], color=COLORS.soc_day_boundary, strokeWidth=1)
        .encode(x="Stunde:Q")
    )

    # Layer background charts
    background_layer = alt.layer(pv_chart, consumption_chart)

    # Combine all layers
    combined = (
        alt.layer(background_layer, day_rules)
        .resolve_scale(y="independent")
        + soc_chart
    ).resolve_scale(
        y="independent"
    ).properties(
        height=350
    )

    st.altair_chart(configure_german_locale(combined), width="stretch")

    # Add interpretation hints based on season
    _render_season_caption(season)


def _render_season_caption(season: str) -> None:
    """Render season-specific interpretation hints."""
    if season == "summer":
        st.caption(
            "☀️ **Sommer**: Hohe PV-Erzeugung (🟠 orange) übersteigt oft den Verbrauch (⚪ grau). "
            "Speicher, die dauerhaft über 50% bleiben, sind möglicherweise überdimensioniert. "
            "Achte auf Tage mit schlechtem Wetter (niedrigere PV-Spitzen), "
            "um zu sehen, ob der Speicher dann entladen wird."
        )
    elif season == "transition":
        st.caption(
            "🌤️ **Übergangszeit (Frühling/Herbst)**: PV-Erzeugung (🟠 orange) und Verbrauch (⚪ grau) sind ähnlicher. "
            "Diese Jahreszeit zeigt am besten, wie gut der Speicher zur Überbrückung "
            "der Nacht- und Morgenstunden genutzt wird."
        )
    else:
        st.caption(
            "❄️ **Winter**: Geringe PV-Erzeugung (🟠 orange), oft unter dem Verbrauch (⚪ grau). "
            "In dieser Zeit sind Speicher nur selten von Nutzen, da die Nächte lang sind und wenig Sonne scheint."
        )

