"""
Inverter efficiency curves and calculations.

Contains power-dependent inverter efficiency data based on CEC 
(California Energy Commission) Grid Support Inverter List analysis.

Data source: https://www.energy.ca.gov/programs-and-topics/programs/solar-equipment-lists
Analyzed from ~2,000 solar inverters and ~1,000 battery inverters (March 2026).
"""
from __future__ import annotations


# ─── Inverter Efficiency Curves ────────────────────────────────────────────────
# Format: (threshold_percent, efficiency) - efficiency applies up to the threshold.
# Power levels: 10%, 20%, 30%, 50%, 75%, 100% of rated capacity

# Pessimistic estimate (10th percentile of CEC data)
# Use for conservative planning or older/budget inverters
INVERTER_EFFICIENCY_P10: tuple[tuple[int, float], ...] = (
    (10, 0.9051),   # 10% load
    (20, 0.9406),   # 20% load
    (30, 0.9513),   # 30% load
    (50, 0.9578),   # 50% load
    (75, 0.9578),   # 75% load
    (100, 0.9538),  # 100% load
)

# Median estimate (50th percentile of CEC data) - DEFAULT
# Representative of typical modern inverters
INVERTER_EFFICIENCY_P50: tuple[tuple[int, float], ...] = (
    (10, 0.9451),   # 10% load
    (20, 0.9616),   # 20% load
    (30, 0.9676),   # 30% load
    (50, 0.9715),   # 50% load
    (75, 0.9710),   # 75% load
    (100, 0.9681),  # 100% load
)

# Optimistic estimate (90th percentile of CEC data)
# Use for premium/high-efficiency inverters
INVERTER_EFFICIENCY_P90: tuple[tuple[int, float], ...] = (
    (10, 0.9704),   # 10% load
    (20, 0.9806),   # 20% load
    (30, 0.9832),   # 30% load
    (50, 0.9839),   # 50% load
    (75, 0.9827),   # 75% load
    (100, 0.9808),  # 100% load
)

# Mapping of curve names to curve data
INVERTER_EFFICIENCY_CURVES: dict[str, tuple[tuple[int, float], ...]] = {
    "pessimistic": INVERTER_EFFICIENCY_P10,
    "median": INVERTER_EFFICIENCY_P50,
    "optimistic": INVERTER_EFFICIENCY_P90,
}

# Default curve for simulations
DEFAULT_INVERTER_EFFICIENCY_CURVE = INVERTER_EFFICIENCY_P50

# Default custom efficiency values as percentages (for UI)
# Derived from P50 curve - used as initial values when user selects "custom" preset
DEFAULT_INVERTER_EFFICIENCY_CUSTOM_PCT: list[float] = [
    round(eff * 100, 2) for _, eff in INVERTER_EFFICIENCY_P50
]


def get_inverter_efficiency(
    power_kw: float,
    max_power_kw: float,
    efficiency_curve: tuple[tuple[int, float], ...] | None = None,
) -> float:
    """
    Calculate inverter efficiency based on current power output.
    
    Inverter efficiency varies with load - lower at partial load due to
    fixed standby losses, highest near 50% of rated capacity.
    
    Args:
        power_kw: Current power output in kW
        max_power_kw: Maximum rated power of inverter in kW
        efficiency_curve: Optional custom curve as ((threshold_pct, efficiency), ...)
                         If None, uses DEFAULT_INVERTER_EFFICIENCY_CURVE
    
    Returns:
        Efficiency as a decimal (0.0 to 1.0)
    """
    if efficiency_curve is None:
        efficiency_curve = DEFAULT_INVERTER_EFFICIENCY_CURVE
    
    if max_power_kw is None or max_power_kw <= 0:
        # No inverter limit defined - return peak efficiency (at 50%)
        return efficiency_curve[3][1]
    
    # Calculate power as percentage of rated capacity (capped at 100%)
    power_pct = min(power_kw / max_power_kw, 1.0) * 100
    
    # Find the applicable efficiency from the curve
    for threshold, efficiency in efficiency_curve:
        if power_pct <= threshold:
            return efficiency
    
    # Above all thresholds - return the last efficiency
    return efficiency_curve[-1][1]

