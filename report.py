"""
Report rendering components for the PV analysis application.
Contains all visualization and display logic.
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from api import reverse_geocode
from config import MONTH_LABELS
from models import SimulationConfig, AnalysisResult, ScenarioResult
from utils import (
    de, de_styler, color_pos_neg, color_amort, color_rendite,
    color_autarkie, color_eigenverbrauch, build_yearly_data,
    find_breakeven, calc_amortization_with_price_increase
)
from state import encode_config


class Report:
    """Renders the complete PV analysis report."""
    
    def __init__(self, config: SimulationConfig, results: AnalysisResult) -> None:
        self.config = config
        self.results = results
    
    # Convenience properties for frequently accessed values
    @property
    def e_price(self) -> float:
        return self.config.economics.e_price
    
    @property
    def e_inc(self) -> float:
        return self.config.economics.e_inc
    
    @property
    def etf_ret(self) -> float:
        return self.config.economics.etf_ret
    
    @property
    def feed_in_tariff(self) -> float:
        return self.config.feed_in_tariff_eur
    
    @property
    def analysis_years(self) -> int:
        return self.config.economics.analysis_years
    
    @property
    def total_consumption(self) -> float:
        return self.results.total_consumption
    
    @property
    def scenarios(self) -> list[ScenarioResult]:
        return self.results.scenarios

    def render(self) -> None:
        """Render the complete analysis report."""
        self._render_header()
        self._render_scenario_overview()
        self._render_monthly_energy_balance()
        self._render_incremental_analysis()
        self._render_longterm_comparison()
        self._render_scenario_details()
        self._render_summary()
        self._render_share_button()

    def _render_header(self) -> None:
        """Render the main header section with key metrics."""
        st.title("☀️ PV-Analyse mit Speichervergleich")
        place_name = reverse_geocode(self.config.lat, self.config.lon)
        location_str = f"{place_name} ({self.config.lat}°N / {self.config.lon}°E)" if place_name else f"{self.config.lat}°N / {self.config.lon}°E"
        st.caption(f"PVGIS-Stundenwerte {self.config.pv_system.data_year}  ·  Standort {location_str}")

        subtitle_parts = []
        if self.config.pv_system.inverter_limit_enabled:
            coupling = "DC" if self.config.storage.dc_coupled else "AC"
            subtitle_parts.append(f"WR-Limit {self.config.pv_system.inverter_limit_w} W ({coupling}-gekoppelt)")
        if self.feed_in_tariff > 0:
            subtitle_parts.append(f"Einspeisevergütung {de(self.feed_in_tariff * 100, 1)} ct/kWh")
        if subtitle_parts:
            st.caption(" · ".join(subtitle_parts))

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Gesamtverbrauch", f"{de(self.total_consumption)} kWh/a")
        col2.metric("Stromkosten ohne PV", f"{de(self.total_consumption * self.e_price)} €/a")
        col3.metric("PV-Leistung", f"{de(self.config.total_peak_kwp, 1)} kWp")
        col4.metric("PV-Erzeugung", f"{de(self.results.pv_generation_total)} kWh/a")

    def _render_scenario_overview(self) -> None:
        """Render the scenario overview table."""
        st.header("📊 Szenario-Übersicht")
        
        overview_rows = []
        for r in self.scenarios:
            feed_rev = r.feed_in * self.feed_in_tariff
            row = {
                "Szenario": r.name,
                "Speicher (kWh)": de(r.storage_capacity, 2),
                "Investition (€)": r.investment_cost,
                "Netzbezug (kWh/a)": round(r.grid_import),
                "Einspeisung (kWh/a)": round(r.feed_in),
                "Eingespart (kWh/a)": round(r.saved_kwh),
                "Autarkie (%)": round(r.autarky, 1),
                "Eigenverbr. (%)": round(r.self_consumption, 1),
            }
            if self.feed_in_tariff > 0:
                row["Vergütung (€/a)"] = round(feed_rev, 2)
            row["Ersparnis (€/a)"] = round(r.annual_savings(self.e_price, self.feed_in_tariff), 2)
            overview_rows.append(row)

        overview_fmt = {
            "Autarkie (%)": de_styler(1),
            "Eigenverbr. (%)": de_styler(1),
            "Ersparnis (€/a)": de_styler(2),
        }
        if self.feed_in_tariff > 0:
            overview_fmt["Vergütung (€/a)"] = de_styler(2)
        st.dataframe(
            pd.DataFrame(overview_rows).style
            .format(overview_fmt)
            .map(color_autarkie, subset=["Autarkie (%)"])
            .map(color_eigenverbrauch, subset=["Eigenverbr. (%)"]),
            use_container_width=True, hide_index=True,
        )

        if self.e_inc > 0:
            st.caption(f"📌 Die Ersparnis (€/a) bezieht sich auf das 1. Jahr. Durch steigende Strompreise "
                       f"(+{self.e_inc * 100:.0f} %/a) ist die tatsächliche Ersparnis in späteren Jahren höher.")

    def _render_monthly_energy_balance(self) -> None:
        """Render monthly energy balance charts for all scenarios."""
        st.header("⚡ Monatliche Energiebilanz")
        st.caption("Woher kommt der Strom? Verbrauchsdeckung nach Quelle pro Monat.")

        # Compute shared Y-axis range across all scenarios
        y_max_all = 0.0
        y_min_all = 0.0
        for r in self.scenarios:
            for m in range(1, 13):
                d = r.monthly[m]
                positive = d.direct_pv + d.battery + d.grid_import
                negative = -d.feed_in
                y_max_all = max(y_max_all, positive)
                y_min_all = min(y_min_all, negative)
        y_max_all *= 1.05
        y_min_all *= 1.05

        energy_tabs = st.tabs([r.name for r in self.scenarios])
        for etab, r in zip(energy_tabs, self.scenarios):
            with etab:
                self._render_single_energy_balance(r, y_min_all, y_max_all)

    def _render_single_energy_balance(self, scenario: ScenarioResult, y_min: float, y_max: float) -> None:
        """Render a single energy balance chart."""
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
                        range=["#ff9800", "#4db68a", "#488fc2", "#a280db"],
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
            .mark_rule(color="gray", strokeWidth=1)
            .encode(y="y:Q")
        )

        cons_df = pd.DataFrame([
            {"Monat": MONTH_LABELS[m - 1], "Verbrauch": scenario.monthly[m].consumption}
            for m in range(1, 13)
        ])
        line = (
            alt.Chart(cons_df)
            .mark_line(color="#78909c", strokeWidth=2, strokeDash=[6, 3])
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
            .mark_point(color="#78909c", size=30, filled=True)
            .encode(
                x=alt.X("Monat:N", sort=MONTH_LABELS),
                y=alt.Y("Verbrauch:Q"),
            )
        )

        st.altair_chart(
            (bars + zero + line + points).configure(
                locale={
                    "number": {
                        "decimal": ",", "thousands": ".", "grouping": [3],
                        "currency": ["", " €"],
                    }
                }
            ),
            use_container_width=True,
        )
        st.caption("📊 Balken = Verbrauchsdeckung (☀️ Direkt-PV, 🔋 Batterie, 🔵 Netzbezug) · "
                   "🟣 Einspeisung (negativ) · Gestrichelte Linie = Gesamtverbrauch")

    def _render_incremental_analysis(self) -> None:
        """Render incremental analysis comparing storage upgrades."""
        if len(self.scenarios) <= 1:
            return
            
        st.header("🔋 Inkrementelle Analyse")
        st.caption("Mehrwert jeder Ausbaustufe gegenüber der vorherigen.")
        
        incr_rows = []
        for i in range(1, len(self.scenarios)):
            prev, curr = self.scenarios[i - 1], self.scenarios[i]
            d_cost = curr.investment_cost - prev.investment_cost
            d_kwh = prev.grid_import - curr.grid_import
            d_feed_in = curr.feed_in - prev.feed_in
            d_eur = d_kwh * self.e_price + d_feed_in * self.feed_in_tariff
            rend = (d_eur / d_cost) * 100 if d_cost > 0 else 0
            amort = calc_amortization_with_price_increase(
                d_cost, d_kwh, d_feed_in, self.e_price, self.e_inc, self.feed_in_tariff
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
        st.dataframe(styled_incr, use_container_width=True, hide_index=True)
        
        if self.e_inc > 0:
            st.caption(f"📌 Die Ersparnis (€/a) bezieht sich auf das 1. Jahr. Durch steigende Strompreise "
                       f"(+{self.e_inc * 100:.0f} %/a) ist die tatsächliche Ersparnis in späteren Jahren höher. "
                       f"Die Amortisation berücksichtigt dies jedoch.")

    def _render_longterm_comparison(self) -> None:
        """Render long-term PV vs ETF comparison chart."""
        st.header(f"📈 Langzeit-Vergleich: PV vs. ETF ({self.analysis_years} Jahre)")
        assumptions = f"Annahmen: Strompreis +{self.e_inc * 100:.0f} %/a · ETF +{self.etf_ret * 100:.0f} %/a"
        if self.feed_in_tariff > 0:
            assumptions += f" · Einspeisevergütung {de(self.feed_in_tariff * 100, 1)} ct/kWh (konstant)"
        st.caption(assumptions)

        chart_frames = []
        for r in self.scenarios:
            df = build_yearly_data(
                r.saved_kwh, r.feed_in, self.feed_in_tariff,
                r.investment_cost, self.e_price, self.e_inc,
                self.etf_ret, self.analysis_years
            ).copy()
            df["Szenario"] = r.name
            chart_frames.append(df)
        all_data = pd.concat(chart_frames, ignore_index=True)

        pv_line = all_data[["Jahr", "PV netto (EUR)", "Szenario"]].rename(columns={"PV netto (EUR)": "Wert"})
        pv_line["Anlage"] = "PV: " + pv_line["Szenario"]
        pv_line["Art"] = "PV"

        etf_line = all_data[["Jahr", "ETF netto (EUR)", "Szenario"]].rename(columns={"ETF netto (EUR)": "Wert"})
        etf_line["Anlage"] = "ETF: " + etf_line["Szenario"]
        etf_line["Art"] = "ETF"

        chart_df = pd.concat([pv_line, etf_line], ignore_index=True)

        chart = (
            alt.Chart(chart_df)
            .mark_line(strokeWidth=2)
            .encode(
                x=alt.X("Jahr:Q", title="Jahr", axis=alt.Axis(format="d")),
                y=alt.Y("Wert:Q", title="Netto-Gewinn (€)", axis=alt.Axis(format=",.0f")),
                color=alt.Color("Anlage:N", title="Anlage"),
                strokeDash=alt.StrokeDash(
                    "Art:N",
                    scale=alt.Scale(domain=["PV", "ETF"], range=[[0], [6, 4]]),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("Anlage:N"),
                    alt.Tooltip("Jahr:Q", format="d"),
                    alt.Tooltip("Wert:Q", title="€", format="+,.0f"),
                ],
            )
            .properties(height=420)
            .interactive()
        )
        zero_rule = (
            alt.Chart(pd.DataFrame({"y": [0]}))
            .mark_rule(strokeDash=[4, 4], color="gray")
            .encode(y="y:Q")
        )
        st.altair_chart(
            (chart + zero_rule).configure(
                locale={
                    "number": {
                        "decimal": ",",
                        "thousands": ".",
                        "grouping": [3],
                        "currency": ["", " €"],
                    }
                }
            ),
            use_container_width=True,
        )

    def _render_scenario_details(self) -> None:
        """Render detailed per-scenario tables."""
        tabs = st.tabs([r.name for r in self.scenarios])
        for tab, r in zip(tabs, self.scenarios):
            with tab:
                df = build_yearly_data(
                    r.saved_kwh, r.feed_in, self.feed_in_tariff,
                    r.investment_cost, self.e_price, self.e_inc,
                    self.etf_ret, self.analysis_years
                )

                be_pv = find_breakeven(df, "PV netto (EUR)")
                be_etf = find_breakeven(df, "PV - ETF (EUR)")

                c1, c2, c3 = st.columns(3)
                c1.metric("Amortisation", f"{be_pv} Jahre" if be_pv else "nie")
                c2.metric("PV schlägt ETF nach", f"{be_etf} Jahren" if be_etf else "nie")
                final = df.iloc[-1]
                c3.metric(
                    f"Δ PV − ETF nach {self.analysis_years}a",
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
                st.dataframe(styled_detail, use_container_width=True, hide_index=True)

    def _render_summary(self) -> None:
        """Render the final summary section."""
        st.header("🏆 Zusammenfassung")

        summary_rows = []
        for r in self.scenarios:
            pv_savings = sum(
                r.saved_kwh * self.e_price * (1 + self.e_inc) ** y + r.feed_in * self.feed_in_tariff
                for y in range(self.analysis_years)
            )
            pv_profit = pv_savings - r.investment_cost
            etf_profit = r.investment_cost * (1 + self.etf_ret) ** self.analysis_years - r.investment_cost
            summary_rows.append({
                "Szenario": r.name,
                "Investition (€)": r.investment_cost,
                "PV Gewinn (€)": round(pv_profit, 2),
                "ETF Gewinn (€)": round(etf_profit, 2),
                "Besser": "PV" if pv_profit > etf_profit else "ETF",
                "Differenz (€)": round(pv_profit - etf_profit, 2),
            })

        summary_df = pd.DataFrame(summary_rows)
        styled_summary = (
            summary_df.style
            .format({
                "Investition (€)": de_styler(0),
                "PV Gewinn (€)": de_styler(0, sign=True),
                "ETF Gewinn (€)": de_styler(0, sign=True),
                "Differenz (€)": de_styler(0, sign=True),
            })
            .map(color_pos_neg, subset=["PV Gewinn (€)", "ETF Gewinn (€)", "Differenz (€)"])
        )
        st.dataframe(styled_summary, use_container_width=True, hide_index=True)

        best = max(summary_rows, key=lambda r: r["PV Gewinn (€)"])
        st.success(
            f"**{best['Szenario']}** erzielt den höchsten absoluten Gewinn nach "
            f"{self.analysis_years} Jahren: **{de(best['PV Gewinn (€)'], sign=True)} €**"
        )

    def _render_share_button(self) -> None:
        """Render the configuration sharing button."""
        st.divider()
        if st.button("🔗 Link mit aktueller Konfiguration erstellen"):
            try:
                encoded = encode_config()
                base_url = st.context.headers.get("Origin", "")
                share_url = f"{base_url}/?cfg={encoded}"
                st.code(share_url, language=None)
                st.caption("Link kopieren und teilen – alle Parameter sind im Link gespeichert.")
            except Exception as exc:
                st.error(f"Fehler beim Erstellen des Links: {exc}")


def render_report(config: SimulationConfig, results: AnalysisResult) -> None:
    """Convenience function to create and render a report."""
    Report(config, results).render()


def render_missing_config_message(missing: list[str]) -> None:
    """Render message when required configuration is missing."""
    st.title("☀️ PV-Analyse mit Speichervergleich")
    st.info(
        "Bitte konfiguriere mindestens folgende Parameter in der **Seitenleiste** (⚙️), "
        "um die Analyse zu starten:"
    )
    for m in missing:
        st.markdown(f"- {m}")

    st.markdown("Nach Hinzufügen der erforderlichen Parameter wird ein Report mit Standardwerten generiert.")
    st.divider()
    st.caption(
        "💡 Tipp: Öffne die Abschnitte in der Seitenleiste links, um Standort und "
        "Verbrauchsdaten einzugeben."
    )

