"""
Report tables: scenario overview, incremental analysis, summary, and scenario details.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from solarbatteryield.config import COLORS
from solarbatteryield.report.context import ReportContext
from solarbatteryield.utils import (
    de, de_styler, color_pos_neg, color_amort, color_rendite,
    color_autarkie, color_eigenverbrauch, color_vollzyklen, 
    build_yearly_data, find_breakeven, calc_amortization_with_price_increase
)


def render_scenario_overview(ctx: ReportContext) -> None:
    """
    Render the scenario overview table.
    
    Shows key metrics for each scenario: storage, investment, grid import,
    feed-in, savings, autarky, self-consumption, and full cycles.
    
    Args:
        ctx: Report context with config and results
    """
    st.header("📊 Szenario-Übersicht")

    overview_rows = []
    for r in ctx.scenarios:
        feed_rev = r.feed_in * ctx.feed_in_tariff
        row = {
            "Szenario": r.name,
            "Speicher (kWh)": de(r.storage_capacity, 2),
            "Investition (€)": r.investment_cost,
            "Netzbezug (kWh/a)": round(r.grid_import),
            "Einspeisung (kWh/a)": round(r.feed_in),
            "Eingespart (kWh/a)": round(r.saved_kwh),
            "Autarkie (%)": round(r.autarky, 1),
            "Eigenverbr. (%)": round(r.self_consumption, 1),
            "Vollzyklen/a": round(r.full_cycles, 1) if r.storage_capacity > 0 else 0,
        }
        if ctx.feed_in_tariff > 0:
            row["Vergütung (€/a)"] = round(feed_rev, 2)
        row["Ersparnis (€/a)"] = round(r.annual_savings(ctx.e_price, ctx.feed_in_tariff), 2)
        overview_rows.append(row)

    overview_fmt = {
        "Autarkie (%)": de_styler(1),
        "Eigenverbr. (%)": de_styler(1),
        "Vollzyklen/a": de_styler(1),
        "Ersparnis (€/a)": de_styler(2),
    }
    if ctx.feed_in_tariff > 0:
        overview_fmt["Vergütung (€/a)"] = de_styler(2)
    
    st.dataframe(
        pd.DataFrame(overview_rows).style
        .format(overview_fmt)
        .map(color_autarkie, subset=["Autarkie (%)"])
        .map(color_eigenverbrauch, subset=["Eigenverbr. (%)"])
        .map(color_vollzyklen, subset=["Vollzyklen/a"]),
        width="stretch", hide_index=True,
    )

    if ctx.e_inc > 0:
        st.caption(
            f"📌 Die Ersparnis (€/a) bezieht sich auf das 1. Jahr. Durch steigende Strompreise "
            f"(+{ctx.e_inc * 100:.0f} %/a) ist die tatsächliche Ersparnis in späteren Jahren höher."
        )


def render_incremental_analysis(ctx: ReportContext) -> None:
    """
    Render incremental analysis comparing storage upgrades.
    
    Shows the added value of each upgrade step: delta cost, delta savings,
    yield percentage, and amortization time.
    
    Args:
        ctx: Report context with config and results
    """
    if len(ctx.scenarios) <= 1:
        return

    st.header("🔋 Inkrementelle Analyse")
    st.caption(
        "Wie lange braucht ein Upgrade, bis es sich bezahlt gemacht hat? "
        "Mehrwert jeder Ausbaustufe gegenüber der vorherigen."
    )

    incr_rows = []
    for i in range(1, len(ctx.scenarios)):
        prev, curr = ctx.scenarios[i - 1], ctx.scenarios[i]
        d_cost = curr.investment_cost - prev.investment_cost
        d_kwh = prev.grid_import - curr.grid_import
        d_feed_in = curr.feed_in - prev.feed_in
        d_eur = d_kwh * ctx.e_price + d_feed_in * ctx.feed_in_tariff
        rend = (d_eur / d_cost) * 100 if d_cost > 0 else 0
        amort = calc_amortization_with_price_increase(
            d_cost, d_kwh, d_feed_in, ctx.e_price, ctx.e_inc, ctx.feed_in_tariff
        )
        incr_rows.append({
            "Upgrade": f"{prev.name}  →  {curr.name}",
            "Δ Invest (€)": d_cost,
            "Δ Ersparnis (kWh/a)": round(d_kwh),
            "Δ Ersparnis (€/a)": d_eur,
            "Rendite (%/a)": rend,
            "Amortisation (a)": amort,
        })

    incr_df = pd.DataFrame(incr_rows)
    styled_incr = (
        incr_df.style
        .format({
            "Δ Invest (€)": de_styler(0),
            "Δ Ersparnis (kWh/a)": de_styler(1),
            "Δ Ersparnis (€/a)": de_styler(2),
            "Rendite (%/a)": de_styler(2),
            "Amortisation (a)": de_styler(1),
        })
        .map(color_pos_neg, subset=["Δ Ersparnis (€/a)"])
        .map(color_rendite, subset=["Rendite (%/a)"])
        .map(color_amort, subset=["Amortisation (a)"])
    )
    st.dataframe(styled_incr, width="stretch", hide_index=True)

    if ctx.e_inc > 0:
        st.caption(
            f"📌 Die Ersparnis (€/a) bezieht sich auf das 1. Jahr. Durch steigende Strompreise "
            f"(+{ctx.e_inc * 100:.0f} %/a) ist die tatsächliche Ersparnis in späteren Jahren höher. "
            f"Die Amortisation berücksichtigt dies jedoch."
        )


def render_scenario_details(ctx: ReportContext) -> None:
    """
    Render detailed per-scenario tables with yearly breakdown.
    
    Shows amortization, PV vs ETF breakeven, and yearly data for each scenario.
    
    Args:
        ctx: Report context with config and results
    """
    tabs = st.tabs([r.name for r in ctx.scenarios])
    for tab, r in zip(tabs, ctx.scenarios):
        with tab:
            df = build_yearly_data(
                r.saved_kwh, r.feed_in, ctx.feed_in_tariff,
                r.investment_cost, ctx.e_price, ctx.e_inc,
                ctx.etf_ret, ctx.analysis_years, ctx.reinvest_savings
            )

            be_pv = find_breakeven(df, "PV netto (EUR)")
            be_etf = find_breakeven(df, "PV - ETF (EUR)")

            # Calculate monthly investment (annual savings / 12)
            first_year_savings = r.annual_savings(ctx.e_price, ctx.feed_in_tariff)
            monthly_invest = first_year_savings / 12

            if ctx.reinvest_savings:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric(
                    "Monatl. Sparrate",
                    f"{de(monthly_invest, 0)} €",
                    help="Empfohlener monatlicher Betrag für den ETF-Sparplan zur Reinvestition "
                         "der Ersparnisse, basierend auf der Ersparnis im ersten Jahr."
                )
                c2.metric("Amortisation", f"{be_pv} Jahre" if be_pv else "nie")
                c3.metric("PV schlägt ETF nach", f"{be_etf} Jahren" if be_etf else "nie")
                final = df.iloc[-1]
                c4.metric(
                    f"Δ PV − ETF nach {ctx.analysis_years}a",
                    f"{de(final['PV - ETF (EUR)'], sign=True)} €",
                )
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("Amortisation", f"{be_pv} Jahre" if be_pv else "nie")
                c2.metric("PV schlägt ETF nach", f"{be_etf} Jahren" if be_etf else "nie")
                final = df.iloc[-1]
                c3.metric(
                    f"Δ PV − ETF nach {ctx.analysis_years}a",
                    f"{de(final['PV - ETF (EUR)'], sign=True)} €",
                )

            euro_cols = [c for c in df.columns if "(EUR)" in c]
            fmt = {c: de_styler(0, sign=True) for c in euro_cols}
            fmt["Jahr"] = de_styler(0)
            styled_detail = (
                df.style
                .format(fmt)
                .map(color_pos_neg, subset=["PV netto (EUR)", "PV - ETF (EUR)"])
            )

            st.dataframe(styled_detail, width="stretch", hide_index=True)


def render_summary(ctx: ReportContext) -> None:
    """
    Render the final summary section.
    
    Shows profit comparison between PV and ETF for all scenarios,
    highlighting the best scenario.
    
    Args:
        ctx: Report context with config and results
    """
    st.header("🏆 Zusammenfassung")
    st.caption(
        f"Wie viel Gewinn habe ich nach {ctx.analysis_years} Jahr"
        f"{'en' if ctx.analysis_years > 1 else ''} gemacht?"
    )

    summary_rows = []
    for r in ctx.scenarios:
        df = build_yearly_data(
            r.saved_kwh, r.feed_in, ctx.feed_in_tariff,
            r.investment_cost, ctx.e_price, ctx.e_inc,
            ctx.etf_ret, ctx.analysis_years, ctx.reinvest_savings
        )
        final = df.iloc[-1]
        pv_profit = final["PV netto (EUR)"]
        etf_profit = final["ETF netto (EUR)"]

        row = {
            "Szenario": r.name,
            "Investition (€)": r.investment_cost,
            "PV Gewinn (€)": round(pv_profit, 2),
        }

        if ctx.reinvest_savings:
            row["davon Reinvest (€)"] = round(final["Reinvest-Ertrag (EUR)"], 2)

        row["ETF Gewinn (€)"] = round(etf_profit, 2)
        row["Besser"] = "PV" if pv_profit > etf_profit else "ETF"
        row["Differenz (€)"] = round(pv_profit - etf_profit, 2)

        summary_rows.append(row)

    summary_df = pd.DataFrame(summary_rows)
    fmt = {
        "Investition (€)": de_styler(0),
        "PV Gewinn (€)": de_styler(0, sign=True),
        "ETF Gewinn (€)": de_styler(0, sign=True),
        "Differenz (€)": de_styler(0, sign=True),
    }
    color_cols = ["PV Gewinn (€)", "ETF Gewinn (€)", "Differenz (€)"]

    if ctx.reinvest_savings:
        fmt["davon Reinvest (€)"] = de_styler(0, sign=True)

    styled_summary = (
        summary_df.style
        .format(fmt)
        .map(color_pos_neg, subset=color_cols)
    )
    st.dataframe(styled_summary, width="stretch", hide_index=True)

    best = max(summary_rows, key=lambda r: r["PV Gewinn (€)"])
    st.success(
        f"**{best['Szenario']}** erzielt den höchsten absoluten Gewinn nach "
        f"{ctx.analysis_years} Jahren: **{de(best['PV Gewinn (€)'], sign=True)} €**"
    )

