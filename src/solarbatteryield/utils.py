"""
Utility functions for formatting and styling in the PV analysis application.
"""
import pandas as pd
import streamlit as st

from solarbatteryield.config import COLORS


def de(val, decimals: int = 0, sign: bool = False) -> str:
    """Format a number with German locale (. = thousands, , = decimal)."""
    if not isinstance(val, (int, float)):
        return str(val)
    s = f"{val:{'+' if sign else ''},.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def de_styler(decimals: int = 0, sign: bool = False):
    """Return a callable for use in pandas Styler .format()."""
    return lambda v: de(v, decimals, sign)


def color_pos_neg(val) -> str:
    """Color positive values green, negative values red."""
    if not isinstance(val, (int, float)):
        return ""
    return f"color: {COLORS.positive}" if val >= 0 else f"color: {COLORS.negative}"


def color_amort(val) -> str:
    """Color amortization values: green <=5, orange <=10, red >10."""
    if not isinstance(val, (int, float)):
        return ""
    if val <= COLORS.amortization_good:
        return f"color: {COLORS.positive}"
    if val <= COLORS.amortization_medium:
        return f"color: {COLORS.warning}"
    return f"color: {COLORS.negative}"


def color_rendite(val) -> str:
    """Color yield values: green >=15%, orange >=8%, red <8%."""
    if not isinstance(val, (int, float)):
        return ""
    if val >= COLORS.yield_good:
        return f"color: {COLORS.positive}"
    if val >= COLORS.yield_medium:
        return f"color: {COLORS.warning}"
    return f"color: {COLORS.negative}"


def color_autarkie(val) -> str:
    """Color autarky values: green >=50%, orange >=30%, red <30%."""
    if not isinstance(val, (int, float)):
        return ""
    if val >= COLORS.autarky_good:
        return f"color: {COLORS.positive}"
    if val >= COLORS.autarky_medium:
        return f"color: {COLORS.warning}"
    return f"color: {COLORS.negative}"


def color_eigenverbrauch(val) -> str:
    """Color self-consumption values: green >=70%, orange >=50%, red <50%."""
    if not isinstance(val, (int, float)):
        return ""
    if val >= COLORS.self_consumption_good:
        return f"color: {COLORS.positive}"
    if val >= COLORS.self_consumption_medium:
        return f"color: {COLORS.warning}"
    return f"color: {COLORS.negative}"


def color_vollzyklen(val) -> str:
    """
    Color full cycles/year: green 150-350 (optimal), orange outside (sub-optimal).
    
    - < 150: Battery may be oversized, low utilization
    - 150-350: Optimal balance between utilization and longevity
    - > 350: High utilization, faster battery aging
    """
    if not isinstance(val, (int, float)) or val == 0:
        return ""
    if COLORS.cycles_low <= val <= COLORS.cycles_high:
        return f"color: {COLORS.positive}"
    return f"color: {COLORS.warning}"


@st.cache_data
def build_yearly_data(saved_kwh: float, feed_in_kwh: float, feed_in_tariff: float,
                      cost: float, e_price: float, e_inc: float, 
                      etf_ret: float, years: int,
                      reinvest_savings: bool = False) -> pd.DataFrame:
    """
    Build yearly comparison data for PV vs ETF investment.
    
    Args:
        saved_kwh: Annual energy saved in kWh
        feed_in_kwh: Annual feed-in energy in kWh
        feed_in_tariff: Feed-in tariff in EUR/kWh
        cost: Initial investment cost
        e_price: Current electricity price in EUR/kWh
        e_inc: Annual electricity price increase (decimal, e.g., 0.03 for 3%)
        etf_ret: Annual ETF return (decimal, e.g., 0.07 for 7%)
        years: Number of years to simulate
        reinvest_savings: Whether to reinvest PV savings with ETF return rate
        
    Returns:
        DataFrame with yearly comparison data
    """
    rows = []
    pv_cum = 0.0
    
    # For reinvested savings calculation
    # Monthly investment = CONSTANT based on first year savings (realistic: fixed standing order)
    # This is more realistic than adjusting the savings plan each year with electricity prices
    first_year_savings = saved_kwh * e_price + feed_in_kwh * feed_in_tariff
    monthly_invest = first_year_savings / 12
    
    reinvest_portfolio = 0.0
    monthly_etf_ret = (1 + etf_ret) ** (1 / 12) - 1  # Monthly return rate
    
    # Track total contributions for reinvest return calculation
    total_contributions = 0.0
    
    for y in range(1, years + 1):
        price = e_price * (1 + e_inc) ** (y - 1)
        yearly_savings = saved_kwh * price + feed_in_kwh * feed_in_tariff
        pv_cum += yearly_savings
        
        # Calculate reinvest returns if enabled
        reinvest_returns = 0.0
        if reinvest_savings:
            # Fixed monthly investment (same every month, every year)
            for _m in range(12):
                # Add monthly contribution at start of month
                reinvest_portfolio += monthly_invest
                total_contributions += monthly_invest
                # Apply monthly return at end of month
                reinvest_portfolio *= (1 + monthly_etf_ret)
            
            # Returns = portfolio value - total contributions
            reinvest_returns = reinvest_portfolio - total_contributions
        
        # PV netto includes reinvest returns when enabled
        pv_net = pv_cum + reinvest_returns - cost
        
        etf_val = cost * (1 + etf_ret) ** y
        etf_net = etf_val - cost
        
        row = {
            "Jahr": y,
            "PV kumuliert (EUR)": pv_cum,
        }
        
        if reinvest_savings:
            row["Reinvest-Ertrag (EUR)"] = reinvest_returns
        
        row["PV netto (EUR)"] = pv_net
        row["ETF Wert (EUR)"] = etf_val
        row["ETF netto (EUR)"] = etf_net
        row["PV - ETF (EUR)"] = pv_net - etf_net
        
        rows.append(row)
    return pd.DataFrame(rows)


def find_breakeven(df: pd.DataFrame, col: str) -> int | None:
    """Find the first year where a column value becomes positive."""
    pos = df[df[col] >= 0]
    return int(pos.iloc[0]["Jahr"]) if len(pos) > 0 else None


def calc_amortization_with_price_increase(invest: float, d_kwh: float, d_feed_in: float,
                                          e_price: float, e_inc: float, feed_in_tariff: float,
                                          max_years: int = 50) -> float:
    """
    Calculate amortization considering rising electricity prices.
    
    Args:
        invest: Investment amount
        d_kwh: Annual energy savings in kWh
        d_feed_in: Annual feed-in change in kWh
        e_price: Current electricity price
        e_inc: Annual price increase (decimal)
        feed_in_tariff: Feed-in tariff
        max_years: Maximum years to calculate
        
    Returns:
        Number of years until investment is recovered (with decimal precision)
    """
    if d_kwh <= 0 and d_feed_in <= 0:
        return float("inf")
    cumulative = 0.0
    for y in range(1, max_years + 1):
        price = e_price * (1 + e_inc) ** (y - 1)
        yearly_savings = d_kwh * price + d_feed_in * feed_in_tariff
        cumulative += yearly_savings
        if cumulative >= invest:
            prev_cumulative = cumulative - yearly_savings
            remaining = invest - prev_cumulative
            fraction = remaining / yearly_savings if yearly_savings > 0 else 0
            return y - 1 + fraction
    return float("inf")

