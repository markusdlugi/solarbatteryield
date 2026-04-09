"""
Long-term PV vs ETF comparison chart component.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import altair as alt
import pandas as pd
import streamlit as st

from solarbatteryield.config import COLORS
from solarbatteryield.report.chart_config import configure_german_locale
from solarbatteryield.utils import de, build_yearly_data

if TYPE_CHECKING:
    from solarbatteryield.report.context import ReportContext


def render_longterm_comparison(ctx: ReportContext) -> None:
    """
    Render long-term PV vs ETF comparison chart.
    
    Shows cumulative net profit over the analysis period for both PV investment
    and equivalent ETF investment, for all scenarios.
    
    Args:
        ctx: Report context with config and results
    """
    st.header(f"📈 Langzeit-Vergleich: PV vs. ETF ({ctx.analysis_years} Jahre)")
    st.caption("Sollte ich mein Geld lieber anders investieren?")

    chart_frames = []
    for r in ctx.scenarios:
        df = build_yearly_data(
            r.saved_kwh, r.feed_in, ctx.feed_in_tariff,
            r.investment_cost, ctx.e_price, ctx.e_inc,
            ctx.etf_ret, ctx.analysis_years, ctx.reinvest_savings
        ).copy()
        df["Szenario"] = r.name
        chart_frames.append(df)
    all_data = pd.concat(chart_frames, ignore_index=True)

    pv_line = all_data[["Jahr", "PV netto (EUR)", "Szenario"]].rename(
        columns={"PV netto (EUR)": "Wert"}
    )
    pv_line["Anlage"] = "PV: " + pv_line["Szenario"]
    pv_line["Art"] = "PV"

    etf_line = all_data[["Jahr", "ETF netto (EUR)", "Szenario"]].rename(
        columns={"ETF netto (EUR)": "Wert"}
    )
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
        .mark_rule(strokeDash=[4, 4], color=COLORS.zero_line)
        .encode(y="y:Q")
    )
    
    st.altair_chart(
        configure_german_locale(chart + zero_rule),
        width="stretch",
    )

    assumptions = f"📌 Annahmen: Strompreis +{ctx.e_inc * 100:.0f} %/a · ETF +{ctx.etf_ret * 100:.0f} %/a"
    if ctx.feed_in_tariff > 0:
        assumptions += f" · Einspeisevergütung {de(ctx.feed_in_tariff * 100, 1)} ct/kWh (konstant)"
    st.caption(assumptions)

    _render_explanation_expander()


def _render_explanation_expander() -> None:
    """Render the explanation expander for the PV vs ETF comparison."""
    with st.expander("ℹ️ Wie funktioniert dieser Vergleich?"):
        st.markdown("""
**Fragestellung:** Lohnt sich die PV-Investition oder wäre das Geld in einem ETF besser angelegt?

**Vergleichslogik:** Beide Szenarien starten mit dem gleichen Investitionsbetrag:
- **PV:** Die Investition führt zu jährlichen Ersparnissen (reduzierter Netzbezug + ggf. Einspeisevergütung)
- **ETF:** Der gleiche Betrag wird mit der angenommenen Rendite verzinst

**Warum startet PV negativ?** Der „Netto-Gewinn" zeigt die kumulierte Ersparnis *abzüglich* der Anfangsinvestition. 
Da das Geld für die PV-Anlage bereits ausgegeben wurde und im PV-System gebunden ist, startet PV im Minus. 
Beim ETF ist der Netto-Gewinn = Wertzuwachs (Kapital bleibt erhalten), daher startet er bei 0.

**Stromkosten:** Stromkosten fallen in *beiden* Fällen an – bei PV sind sie nur reduziert durch Eigenverbrauch. Diese Einsparung ist genau das, was hier als „PV-Ersparnis" dargestellt wird. 
Die Stromkosten müssen also nicht noch einmal vom ETF-Gewinn abgezogen werden – sie stecken bereits im Vergleich.

**Vereinfachungen:** Abschreibung/Wertverlust der PV-Anlage sowie Wartungskosten sind nicht berücksichtigt. 
Ebenso wenig Kapitalertragsteuer auf ETF-Gewinne oder steuerliche Vorteile der PV-Anlage.

**Option „💸 Ersparnisse reinvestieren":** Diese Option simuliert, was passiert, wenn die monatliche Ersparnis im
PV-Szenario konsequent in einen ETF-Sparplan investiert wird. Die angezeigte „Monatl. Sparrate" basiert auf der
Ersparnis im ersten Jahr und bleibt konstant (wie bei einem typischen Dauerauftrag). Die Erträge aus diesem Sparplan
werden zum PV-Gewinn addiert.

⚠️ **Wichtig:** Dies zeigt das *theoretische Maximum*, das nur erreicht wird, wenn:
- Die Ersparnis jeden Monat diszipliniert investiert wird (statt sie auszugeben)
- Der Sparplan über den gesamten Zeitraum durchgehalten wird
- Der ETF tatsächlich die angenommene Rendite erzielt
        """)

