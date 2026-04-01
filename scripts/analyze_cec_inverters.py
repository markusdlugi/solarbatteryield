#!/usr/bin/env python3
"""
Analyze CEC inverter efficiency data to derive realistic efficiency curves.

This script processes the CEC (California Energy Commission) inverter list
to calculate percentile-based efficiency curves for use in PV simulations.

The CEC list provides efficiency measurements at 6 power levels:
- 10%, 20%, 30%, 50%, 75%, 100% of rated capacity

At three voltage levels:
- Vmin, Vnom, Vmax

Data source: https://www.energy.ca.gov/programs-and-topics/programs/solar-equipment-lists
Download the "Grid Support Inverter List (Full Data)" Excel file.

Usage:
    python analyze_cec_inverters.py <path_to_cec_excel_file>
    
    Example:
    python analyze_cec_inverters.py ~/Downloads/Grid_Support_Inverter_List_Full_Data_ADA.xlsm
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


# Power levels measured by CEC
POWER_LEVELS = [10, 20, 30, 50, 75, 100]

# Column indices for efficiency data (0-indexed)
# Based on CEC Grid Support Inverter List structure:
# - Row 14: Main headers
# - Row 15: Sub-headers with power levels
# - Data starts at row 16
HEADER_ROW = 14  # 0-indexed, so this is Excel row 15
DATA_START_ROW = 16  # 0-indexed, so this is Excel row 17

# Efficiency column indices for Solar Inverters sheet
SOLAR_EFFICIENCY_COLS = {
    'vmin': {10: 40, 20: 41, 30: 42, 50: 43, 75: 44, 100: 45},
    'vnom': {10: 47, 20: 48, 30: 49, 50: 50, 75: 51, 100: 52},
    'vmax': {10: 54, 20: 55, 30: 56, 50: 57, 75: 58, 100: 59},
}

# Battery inverters may have different column structure - will detect dynamically
BATTERY_EFFICIENCY_COLS = None  # Will be detected


def find_efficiency_columns_by_header(df_raw: pd.DataFrame, header_row: int = 15) -> dict:
    """
    Find efficiency columns by examining the header row.
    
    Returns dict like: {'vmin': {10: col_idx, 20: col_idx, ...}, 'vnom': {...}, 'vmax': {...}}
    """
    row = df_raw.iloc[header_row]
    
    columns = {'vmin': {}, 'vnom': {}, 'vmax': {}}
    
    # Look for patterns like "10% Pwr Lvl (%)" in the header row
    for col_idx, val in enumerate(row):
        if pd.isna(val):
            continue
        val_str = str(val).strip()
        
        for power_level in POWER_LEVELS:
            pattern = f"{power_level}%"
            if pattern in val_str and "Pwr Lvl" in val_str:
                # Determine which voltage category based on nearby header
                # Check main header row (row 14)
                main_header = df_raw.iloc[header_row - 1]
                
                # Look backwards to find the voltage category
                for check_col in range(col_idx, max(col_idx - 10, -1), -1):
                    if pd.notna(main_header.iloc[check_col]):
                        main_val = str(main_header.iloc[check_col]).lower()
                        if 'vmin' in main_val:
                            columns['vmin'][power_level] = col_idx
                        elif 'vnom' in main_val:
                            columns['vnom'][power_level] = col_idx
                        elif 'vmax' in main_val:
                            columns['vmax'][power_level] = col_idx
                        break
    
    return columns


def analyze_inverter_data(
    excel_path: Path,
    sheet_index: int,
    inverter_type: str = "Solar",
    header_row: int = HEADER_ROW,
    data_start_row: int = DATA_START_ROW,
    efficiency_cols: dict | None = None,
) -> dict:
    """
    Analyze inverter efficiency data and compute statistics.
    
    Args:
        excel_path: Path to the Excel file
        sheet_index: Sheet index (0 for Solar, 1 for Battery)
        inverter_type: "Solar" or "Battery" for labeling
        header_row: Row index containing sub-headers (0-indexed)
        data_start_row: Row index where data starts (0-indexed)
        efficiency_cols: Column mapping, or None to use defaults
        
    Returns:
        Dictionary with efficiency statistics at each power level
    """
    print(f"\n🔍 Analyzing {inverter_type} Inverters...")
    
    # Read raw data to find columns
    df_raw = pd.read_excel(excel_path, sheet_name=sheet_index, header=None, nrows=20)
    
    # Use provided column mapping or detect from headers
    if efficiency_cols is None:
        if inverter_type == "Solar":
            efficiency_cols = SOLAR_EFFICIENCY_COLS
        else:
            # Try to detect for battery inverters
            efficiency_cols = find_efficiency_columns_by_header(df_raw, header_row + 1)
            if not any(efficiency_cols.values()):
                # Fall back to same as solar
                efficiency_cols = SOLAR_EFFICIENCY_COLS
    
    print(f"   Using efficiency columns:")
    for voltage, cols in efficiency_cols.items():
        if cols:
            print(f"     {voltage}: {cols}")
    
    # Read data starting from the data row
    df = pd.read_excel(excel_path, sheet_name=sheet_index, header=None, skiprows=data_start_row)
    print(f"   Total data rows: {len(df)}")
    
    # Extract and analyze efficiency data
    results = {}
    
    for power_level in POWER_LEVELS:
        all_values = []
        
        # Collect values from all voltage levels
        for voltage in ['vmin', 'vnom', 'vmax']:
            if voltage not in efficiency_cols or power_level not in efficiency_cols[voltage]:
                continue
            
            col_idx = efficiency_cols[voltage][power_level]
            values = pd.to_numeric(df.iloc[:, col_idx], errors='coerce')
            
            # Handle percentage format (values > 1 are percentages)
            if values.median() > 1:
                values = values / 100
            
            # Filter reasonable values
            valid = values[(values >= 0.70) & (values <= 1.0)].dropna()
            all_values.extend(valid.tolist())
        
        if not all_values:
            print(f"   ⚠️  No valid data for {power_level}%")
            continue
        
        values_series = pd.Series(all_values)
        
        results[power_level] = {
            'count': len(values_series),
            'mean': values_series.mean(),
            'std': values_series.std(),
            'min': values_series.min(),
            'max': values_series.max(),
            'p10': values_series.quantile(0.10),
            'p25': values_series.quantile(0.25),
            'p50': values_series.quantile(0.50),
            'p75': values_series.quantile(0.75),
            'p90': values_series.quantile(0.90),
        }
    
    return results


def print_statistics(results: dict, inverter_type: str) -> None:
    """Print formatted statistics table."""
    if not results:
        return
    
    print(f"\n📊 {inverter_type} Inverter Efficiency Statistics")
    print("=" * 80)
    
    # Header
    print(f"{'Power Level':<12} {'Count':>6} {'Mean':>7} {'Std':>6} "
          f"{'P10':>7} {'P50':>7} {'P90':>7} {'Min':>7} {'Max':>7}")
    print("-" * 80)
    
    for level in POWER_LEVELS:
        if level not in results:
            continue
        r = results[level]
        print(f"{level:>3}%         {r['count']:>6} {r['mean']:>7.4f} {r['std']:>6.4f} "
              f"{r['p10']:>7.4f} {r['p50']:>7.4f} {r['p90']:>7.4f} "
              f"{r['min']:>7.4f} {r['max']:>7.4f}")


def generate_python_curves(results: dict, inverter_type: str) -> None:
    """Generate Python code for efficiency curves."""
    if not results:
        return
    
    print(f"\n🐍 Python Code for {inverter_type} Inverter Efficiency Curves")
    print("=" * 80)
    
    # Generate curves for different percentiles
    for percentile, label in [(0.10, "pessimistic (P10)"), 
                               (0.50, "median (P50)"), 
                               (0.90, "optimistic (P90)")]:
        key = f"p{int(percentile * 100)}"
        
        print(f"\n# {inverter_type} inverter - {label}")
        print(f"{inverter_type.upper()}_INVERTER_EFFICIENCY_{key.upper()}: tuple[tuple[int, float], ...] = (")
        
        for level in POWER_LEVELS:
            if level not in results:
                continue
            eff = results[level][key]
            comment = f"  # {level:>3}% load"
            print(f"    ({level}, {eff:.4f}),{comment}")
        
        print(")")


def generate_combined_curve(solar_results: dict, battery_results: dict) -> None:
    """Generate a combined/averaged curve from both inverter types."""
    if not solar_results and not battery_results:
        return
    
    print("\n\n🔄 Combined Average Curve (Solar + Battery)")
    print("=" * 80)
    
    for percentile, label in [(0.10, "pessimistic (P10)"), 
                               (0.50, "median (P50)"), 
                               (0.90, "optimistic (P90)")]:
        key = f"p{int(percentile * 100)}"
        
        print(f"\n# Combined inverter efficiency - {label}")
        print(f"INVERTER_EFFICIENCY_{key.upper()}: tuple[tuple[int, float], ...] = (")
        
        for level in POWER_LEVELS:
            values = []
            if level in solar_results:
                values.append(solar_results[level][key])
            if level in battery_results:
                values.append(battery_results[level][key])
            
            if values:
                avg = sum(values) / len(values)
                print(f"    ({level}, {avg:.4f}),  # {level:>3}% load")
        
        print(")")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\n❌ Error: Please provide the path to the CEC Excel file.")
        print("\nYou can download it from:")
        print("  https://www.energy.ca.gov/programs-and-topics/programs/solar-equipment-lists")
        sys.exit(1)
    
    excel_path = Path(sys.argv[1])
    
    if not excel_path.exists():
        print(f"❌ Error: File not found: {excel_path}")
        sys.exit(1)
    
    print(f"📂 Loading: {excel_path}")
    
    # Try to read Excel file
    try:
        # First, list all sheets
        xl = pd.ExcelFile(excel_path)
        print(f"\n📑 Available sheets: {xl.sheet_names}")
        
        solar_results = {}
        battery_results = {}
        
        # Process Solar Inverters (first sheet)
        if len(xl.sheet_names) >= 1:
            solar_results = analyze_inverter_data(
                excel_path, 
                sheet_index=0, 
                inverter_type="Solar",
            )
            print_statistics(solar_results, "Solar")
            generate_python_curves(solar_results, "Solar")
        
        # Process Battery Inverters (second sheet)
        if len(xl.sheet_names) >= 2:
            battery_results = analyze_inverter_data(
                excel_path, 
                sheet_index=1, 
                inverter_type="Battery",
            )
            print_statistics(battery_results, "Battery")
            generate_python_curves(battery_results, "Battery")
        
        # Generate combined curves
        generate_combined_curve(solar_results, battery_results)
        
        print("\n\n✅ Analysis complete!")
        print("\nNext steps:")
        print("1. Review the generated curves above")
        print("2. Copy the appropriate curve to simulation.py")
        print("3. Consider offering P10/P50/P90 options in the UI for user selection")
        
    except Exception as e:
        import traceback
        print(f"❌ Error reading Excel file: {e}")
        traceback.print_exc()
        print("\nMake sure you have openpyxl installed:")
        print("  pip install openpyxl")
        sys.exit(1)


if __name__ == "__main__":
    main()



