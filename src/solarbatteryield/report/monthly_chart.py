"""
Monthly energy balance chart component.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import altair as alt
import pandas as pd
import streamlit as st

from solarbatteryield.config import MONTH_LABELS, COLORS
from solarbatteryield.report.chart_config import configure_german_locale

if TYPE_CHECKING:
    from solarbatteryield.models import ScenarioResult
    from solarbatteryield.report.context import ReportContext


def render_monthly_energy_balance(ctx: ReportContext) -> None:
    """
    Render monthly energy balance charts for all scenarios.
    
    Shows stacked bar chart with energy sources (direct PV, battery, grid)
    and feed-in as negative bars, with consumption line overlay.
    
    Args:
        ctx: Report context with config and results
    """
    st.header("⚡ Monatliche Energiebilanz")
    st.caption("Woher kommt der Strom? Verbrauchsdeckung nach Quelle pro Monat.")

    # Compute shared Y-axis range across all scenarios
    y_max_all = 0.0
    y_min_all = 0.0
    for r in ctx.scenarios:
        for m in range(1, 13):
            d = r.monthly[m]
            positive = d.direct_pv + d.battery + d.grid_import
            negative = -d.feed_in
            y_max_all = max(y_max_all, positive)
            y_min_all = min(y_min_all, negative)
    y_max_all *= 1.05
    y_min_all *= 1.05

    energy_tabs = st.tabs([r.name for r in ctx.scenarios])
    for etab, r in zip(energy_tabs, ctx.scenarios):
        with etab:
            _render_single_energy_balance(r, y_min_all, y_max_all)


def _render_single_energy_balance(
    scenario: ScenarioResult, 
    y_min: float, 
    y_max: float
) -> None:
    """
    Render a single energy balance chart for one scenario.
    
    Args:
        scenario: The scenario result to render
        y_min: Minimum Y-axis value (shared across scenarios)
        y_max: Maximum Y-axis value (shared across scenarios)
    """
    rows = []
    for m in range(1, 13):
        d = scenario.monthly[m]
        rows.append({
            "Monat": MONTH_LABELS[m - 1],
            "Monat_Nr": m,
            "Direkt-PV": d.direct_pv,
            "Batterie": d.battery,
            "Netzbezug": d.grid_import,
            "Einspeisung": -d.feed_in,
        })
    mdf = pd.DataFrame(rows)

    melted = mdf.melt(
        id_vars=["Monat", "Monat_Nr"],
        value_vars=["Direkt-PV", "Batterie", "Netzbezug", "Einspeisung"],
        var_name="Quelle", value_name="kWh",
    )

    bars = (
        alt.Chart(melted)
        .mark_bar()
        .encode(
            x=alt.X("Monat:N", sort=MONTH_LABELS, title=None),
            y=alt.Y("kWh:Q", title="kWh", scale=alt.Scale(domain=[y_min, y_max])),
            color=alt.Color(
                "Quelle:N",
                scale=alt.Scale(
                    domain=["Direkt-PV", "Batterie", "Netzbezug", "Einspeisung"],
                    range=[COLORS.direct_pv, COLORS.battery, COLORS.grid_import, COLORS.feed_in],
                ),
                title="Quelle",
            ),
            order=alt.Order("order:Q"),
            tooltip=[
                alt.Tooltip("Monat:N"),
                alt.Tooltip("Quelle:N"),
                alt.Tooltip("kWh:Q", format=",.0f"),
            ],
        )
        .transform_calculate(
            order="datum.Quelle === 'Direkt-PV' ? 0 : datum.Quelle === 'Batterie' ? 1 "
                  ": datum.Quelle === 'Netzbezug' ? 2 : 3"
        )
        .properties(height=320)
    )

    zero = (
        alt.Chart(pd.DataFrame({"y": [0]}))
        .mark_rule(color=COLORS.zero_line, strokeWidth=1)
        .encode(y="y:Q")
    )

    cons_df = pd.DataFrame([
        {"Monat": MONTH_LABELS[m - 1], "Verbrauch": scenario.monthly[m].consumption}
        for m in range(1, 13)
    ])
    line = (
        alt.Chart(cons_df)
        .mark_line(color=COLORS.consumption_line, strokeWidth=2, strokeDash=[6, 3])
        .encode(
            x=alt.X("Monat:N", sort=MONTH_LABELS),
            y=alt.Y("Verbrauch:Q"),
            tooltip=[
                alt.Tooltip("Monat:N"),
                alt.Tooltip("Verbrauch:Q", title="Verbrauch (kWh)", format=",.0f"),
            ],
        )
    )
    points = (
        alt.Chart(cons_df)
        .mark_point(color=COLORS.consumption_line, size=30, filled=True)
        .encode(
            x=alt.X("Monat:N", sort=MONTH_LABELS),
            y=alt.Y("Verbrauch:Q"),
        )
    )

    st.altair_chart(
        configure_german_locale(bars + zero + line + points),
        width="stretch",
    )
    st.caption(
        "📊 Balken = Verbrauchsdeckung (☀️ Direkt-PV, 🔋 Batterie, 🔵 Netzbezug) · "
        "🟣 Einspeisung (negativ) · Gestrichelte Linie = Gesamtverbrauch"
    )

