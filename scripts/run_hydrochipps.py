#%%
"""
Hydropower Scheduling Using Pownet (HydroCHIPPs Project)

This script performs short-term hydropower scheduling for the Cumberland River Basin
using the PoWnet modeling framework in rolling-horizon mode.

Hydropower Units (underscore used instead of spaces for compatibility with HiGHS solver):
    - Barkley
    - Center_Hill
    - Cheatham
    - Cordell_Hull
    - Dale_Hollow
    - J_Percy_Priest
    - Old_Hickory
    - Wolf_Creek

Authors:
    - M. Pavičević, Ph.D. (Argonne National Laboratory)
    - P. Bunnak (Cornell University)

Project:
    - HydroCHIPPs (DoE-sponsored HydroWIRES project)
"""
import os
import pandas as pd
import numpy as np
from datetime import datetime
from pownet.core import (
    DataProcessor,
    Simulator,
    ModelBuilder,
    SystemRecord,
    OutputProcessor,
    Visualizer,
)
from pownet import SystemInput
from pownet.data_utils import create_init_condition

# === File Path and Simulation Controls ===
scen_path = "./model_library"      # Path to input data
model_name = "cumberland"          # Name of the model (scenario folder)
sim_horizon = 24 * 7               # Simulation horizon in hours (e.g., 7 days)
steps_to_run = 2                   # How many daily steps to simulate per iteration
end_day = 7                        # How many days to loop through in total
to_process_inputs = True           # If True, runs the data processing pipeline
do_plot = True                     # Currently unused, placeholder for plotting


#%%###################################################
## Functions to update the weekly budgets and prices
######################################################
def update_weekly_hydro_capacity(df, index, updated_values):
    """
    Update weekly hydro generation budgets in the DataFrame.

    Parameters:
    - df (pd.DataFrame): DataFrame containing weekly hydro capacities.
    - index (int): Row index to update (typically the day number).
    - updated_values (dict): Unit-wise capacity values for the specified index.

    Example:
    update_weekly_hydro_capacity(df, 2, {'Barkley': 12000, 'Cheatham': 2500, ...})
    """
    for column, new_value in updated_values.items():
        if column in df.columns:
            df.at[index, column] = new_value
        else:
            raise ValueError(f"Column '{column}' does not exist in the DataFrame.")


def update_contract_costs(inputs, supplier, new_values, start_day):
    """
    Update 168 hourly contract costs for a supplier, starting from a given day.

    Parameters:
    - inputs (dict): Must contain 'contract_costs' key.
    - supplier (str): Name of the supplier (e.g., 'gas').
    - new_values (list or np.ndarray): List of 168 new prices.
    - start_day (int): Start day for the update (1-based).

    Example:
    update_contract_costs(inputs, 'gas', np.random.rand(168), start_day=3)
    """

    # Access the contract_costs dictionary
    contract_costs = inputs.contract_costs

    if len(new_values) != 168:
        raise ValueError("new_values must contain exactly 168 entries.")

    start_hour = (start_day - 1) * 24 + 1

    for i, hour in enumerate(range(start_hour, start_hour + 168)):
        contract_costs[(supplier, hour)] = new_values[i]

#%%########################################
#    Weekly Budgets for Hydropower Units
###########################################

updated_weekly_budgets = {
    'Barkley':         [11000, 11100, 10950, 11050, 10980, 11020, 11010],
    'Center_Hill':     [1600, 1620, 1590, 1610, 1605, 1595, 1615],
    'Cheatham':        [2000, 2020, 1980, 1995, 2005, 2010, 1990],
    'Cordell_Hull':    [2800, 2820, 2780, 2795, 2805, 2810, 2790],
    'Dale_Hollow':     [630, 640, 620, 635, 625, 630, 638],
    'J_Percy_Priest':  [640, 650, 630, 645, 635, 640, 648],
    'Old_Hickory':     [3800, 3820, 3780, 3795, 3805, 3810, 3790],
    'Wolf_Creek':      [7000, 7020, 6980, 6995, 7005, 7010, 6990]
}

weekly_contract_costs = []

for week in range(7):
    weekly_prices = np.round(np.random.uniform(5, 240, 168), 1)
    weekly_contract_costs.append(weekly_prices)

####################################
# Input Processing and Simulation Loop
#####################################

# Optional: re-process input data from scratch
if to_process_inputs:
    data_processor = DataProcessor(
        input_folder=scen_path,
        model_name=model_name,
        year=2016,
        frequency=50
    )
    data_processor.execute_data_pipeline()

# Load inputs from preprocessed files
inputs = SystemInput(
    input_folder=scen_path,
    model_name=model_name,
    year=2016,
    sim_horizon=sim_horizon,
    spin_reserve_factor=0,
    load_shortfall_penalty_factor=1000,
    load_curtail_penalty_factor=1,
    spin_shortfall_penalty_factor=1000,
    line_capacity_factor=1,
    line_loss_factor=0,
)

inputs.load_and_check_data()

# Check if penalty zones were loaded
print(inputs.use_hydro_penalty_zones)  # True
print(inputs.hydro_penalty_zones["Barkley"])

print("\n=== Hydro Ramping Rates ===")
for unit in inputs.hydro_units:
    print(f"{unit:20s} | RU: {inputs.hydro_RU[unit]:6.1f} MW/h | RD: {inputs.hydro_RD[unit]:6.1f} MW/h")

# Dictionaries to store results and models
power_system_model = {}
export_results = {}

# Outer loop over each rolling horizon day
for start_day in range(1, end_day):

    # === Apply updated weekly hydro budgets for this day ===
    first_values = {unit: values[start_day - 1] for unit, values in updated_weekly_budgets.items()}
    update_weekly_hydro_capacity(inputs.weekly_hydro_capacity, start_day, first_values)

    # === Apply updated weekly prices for this day ===
    update_contract_costs(inputs, 'supplier', weekly_contract_costs[start_day - 1], start_day)

    # Initialize model and record-keeping objects
    model_builder = ModelBuilder(inputs)
    record = SystemRecord(inputs)

    build_times = []
    opt_times = []
    objvals = []

    # ========================================================================
    # CRITICAL FIX: Initialize with proper hydro initial conditions
    # ========================================================================
    init_conditions = create_init_condition(
        thermal_units=inputs.thermal_units,
        storage_units=inputs.storage_units,
        ess_max_capacity=inputs.ess_max_capacity,
        hydro_units=inputs.hydro_units,
    )

    # === Inner loop: run multiple steps from this starting day ===
    if steps_to_run is None:
        steps_to_run = 10

    for step_k in range(start_day, start_day + steps_to_run - 1):
        start_time = datetime.now()

        # Build or update the model for the current step
        if step_k == start_day:
            power_system_model[start_day] = model_builder.build(
                step_k=step_k,
                init_conds=init_conditions,
            )
        else:
            power_system_model[start_day] = model_builder.update(
                step_k=step_k,
                init_conds=init_conditions,
            )

        build_times.append((datetime.now() - start_time).total_seconds())

        # Solve the model using HiGHS solver
        power_system_model[start_day].optimize(mipgap=0.001, solver='highs')

        # Fail fast if infeasible
        if not power_system_model[start_day].check_feasible():
            raise ValueError("Model is not feasible.")

        # Save objective value and runtime
        objvals.append(power_system_model[start_day].get_objval())
        opt_times.append(power_system_model[start_day].get_runtime())

        # Record solution results
        record.keep(
            runtime=power_system_model[start_day].get_runtime(),
            objval=power_system_model[start_day].get_objval(),
            solution=power_system_model[start_day].get_solution(),
            step_k=step_k,
        )

        # ========================================================================
        # CRITICAL FIX: Extract hydro dispatch at t=24 for next iteration
        # ========================================================================
        if step_k == start_day:
            # Get the solution DataFrame
            first_solution = power_system_model[start_day].get_solution()

            # Initialize dictionary to store hydro dispatch at t=24
            initial_phydro = {}

            # Iterate through all variables to find phydro at t=24
            for idx, row in first_solution.iterrows():
                varname = row['varname']

                # Check if this is a phydro variable
                if varname.startswith('phydro['):
                    # Extract unit and timestep using string operations
                    # Format: phydro[unit, timestep]
                    try:
                        # Remove 'phydro[' prefix and ']' suffix
                        content = varname[7:-1]  # Skip 'phydro[' and ']'

                        # Split by comma
                        parts = content.split(', ')

                        if len(parts) == 2:
                            unit = parts[0].strip()
                            timestep = int(parts[1].strip())

                            # Only keep values at t=24
                            if timestep == 24:
                                initial_phydro[unit] = row['value']
                    except (ValueError, IndexError) as e:
                        print(f"⚠️  Warning: Could not parse varname '{varname}': {e}")
                        continue

            # Update init_conditions if we found any hydro dispatch values
            if initial_phydro:
                init_conditions['initial_phydro'] = initial_phydro
                print(f"✓ Initialized hydro ramping for {len(initial_phydro)} units at step {step_k}")
                print(f"  Sample values: {dict(list(initial_phydro.items())[:3])}")
            else:
                print(f"⚠️  Warning: No hydro dispatch found at t=24 for step {step_k}")

        # Update initial conditions from record for subsequent iterations
        init_conditions = record.get_init_conds()

        #########################################
        ##### Export results to csv file ########
        #########################################
        # === Process and Export Results ===
        export_results[start_day] = power_system_model[start_day].get_solution()

        # Parse variable names into components (type, unit, node, hour)
        two_elements = export_results[start_day]['varname'].str.extract(r'([^\[]+)\[([^,]+),(\d+)\]')
        three_elements = export_results[start_day]['varname'].str.extract(r'([^\[]+)\[([^,]+),([^,]+),(\d+)\]')
        has_three_elements = three_elements.notna().all(axis=1)
        export_results[start_day]['vartype'] = np.where(has_three_elements, three_elements[0], two_elements[0])
        export_results[start_day]['unit'] = np.where(has_three_elements, three_elements[1], two_elements[1])
        export_results[start_day]['node'] = np.where(has_three_elements, three_elements[2], np.nan)
        export_results[start_day]['hour'] = np.where(has_three_elements, three_elements[3], two_elements[2])
        export_results[start_day] = export_results[start_day][['hour', 'vartype', 'unit', 'node', 'value']]

        # Export results to CSV
        output_folder = "./results/cumberland/"
        os.makedirs(output_folder, exist_ok=True)
        export_results[start_day].to_csv(output_folder + f'results_day_{str(start_day)}.csv', index=False)

####################################
##### Quick hydro ramping check ####
####################################

import matplotlib.pyplot as plt

# =========================
# Hydro ramping check + plot
# =========================

EPS = 1e-3  # tolerance for float noise; adjust to 1e-5 if needed

def plot_hydro_ramping_check(
    hydro_data: pd.DataFrame,
    hydro_RU: dict,
    hydro_RD: dict,
    output_folder: str,
    units_to_plot=None,
    eps: float = EPS,
):
    """
    hydro_data: long dataframe with columns ['hour','unit','value'] for vartype='phydro'
    hydro_RU / hydro_RD: dict[unit] -> MW/h
    """
    if hydro_data.empty:
        print("No hydro dispatch to check.")
        return

    # --- Clean hour, ensure numeric, sort ---
    df = hydro_data.copy()
    df["hour"] = pd.to_numeric(df["hour"], errors="coerce")
    df = df.dropna(subset=["hour"])
    df["hour"] = df["hour"].astype(int)
    df = df.sort_values(["unit", "hour"])

    # --- Pivot: hour index, unit columns ---
    pivot = df.pivot(index="hour", columns="unit", values="value").sort_index()

    # Validate index integrity
    if pivot.index.has_duplicates:
        dupes = pivot.index[pivot.index.duplicated()].unique().tolist()
        raise ValueError(f"Duplicate hours in hydro pivot index: {dupes[:20]} ...")

    # Choose units
    units = list(pivot.columns) if units_to_plot is None else [u for u in units_to_plot if u in pivot.columns]
    if not units:
        print("No matching hydro units to plot.")
        return

    os.makedirs(output_folder, exist_ok=True)

    for unit in units:
        dispatch = pivot[unit].dropna().sort_index()
        if dispatch.empty or len(dispatch) < 2:
            print(f"{unit}: not enough data to compute ramps.")
            continue

        ru = float(hydro_RU.get(unit, np.inf))
        rd = float(hydro_RD.get(unit, np.inf))

        ramps = dispatch.diff()  # MW/h; first is NaN
        ramps_no_na = ramps.dropna()

        pen = float(getattr(inputs, "hydro_ramp_penalty", {}).get(unit, 0.0))
        ramp_cost_series = pen * ramps_no_na.abs()
        total_ramp_cost = float(ramp_cost_series.sum())

        # --- Violation logic with tolerance ---
        # ramp-up violation if change > RU + eps
        # ramp-down violation if change < -RD - eps
        viol_up_mask = ramps_no_na > (ru + eps)
        viol_dn_mask = ramps_no_na < (-rd - eps)
        viol_mask = viol_up_mask | viol_dn_mask

        n_up = int(viol_up_mask.sum())
        n_dn = int(viol_dn_mask.sum())

        # --- Diagnostics: show exact float residuals for "near-limit" issues ---
        max_ramp = float(ramps_no_na.max())
        min_ramp = float(ramps_no_na.min())

        if (n_up > 0) or (n_dn > 0):
            print(f"\n⚠️  RAMPING VIOLATIONS DETECTED for {unit}:")
            print(f"   Ramp-up violations: {n_up}")
            print(f"   Ramp-down violations: {n_dn}")
            print(f"   Max ramp change: {max_ramp:.12f} MW/h (limit: {ru:.12f})")
            print(f"   Min ramp change: {min_ramp:.12f} MW/h (limit: {-rd:.12f})")
            print("   Violation details (full precision):")
            viol_series = ramps_no_na[viol_mask].copy()
            # show residual above RU for up, below -RD for down
            resid = pd.Series(index=viol_series.index, dtype=float)
            resid.loc[viol_up_mask[viol_mask].index] = viol_series.loc[viol_up_mask] - ru
            resid.loc[viol_dn_mask[viol_mask].index] = (-rd) - viol_series.loc[viol_dn_mask]  # positive means beyond limit
            out = pd.DataFrame({"ramp": viol_series, "residual": resid})
            pd.set_option("display.precision", 15)
            print(out)
            print(f"   Ramping cost (${pen}/MW): {total_ramp_cost:.2f}")
        else:
            print(f"\n✅ {unit}: all ramps within limits (eps={eps}).")
            print(f"   Max ramp change: {max_ramp:.12f} MW/h (limit: {ru:.12f})")
            print(f"   Min ramp change: {min_ramp:.12f} MW/h (limit: {-rd:.12f})")
            print(f"   Ramping cost (${pen}/MW): {total_ramp_cost:.2f}")

        # --- Colors for bars (correct, sign-aware) ---
        colors = []
        for h, c in ramps_no_na.items():
            if c > ru + eps:
                colors.append("red")
            elif c < -rd - eps:
                colors.append("red")
            else:
                colors.append("green")

        # --- Plot ---
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

        # Dispatch plot
        ax1.plot(dispatch.index, dispatch.values, "-o", linewidth=2, markersize=3, color="blue")
        ax1.set_ylabel("Power (MW)")
        ax1.set_title(f"{unit} - Dispatch and Ramping Check")
        ax1.grid(True, alpha=0.3)

        # Ramp bars
        ax2.bar(ramps_no_na.index, ramps_no_na.values, color=colors, alpha=0.75, edgecolor="black", linewidth=0.4)
        ax2.axhline(ru, color="darkred", linestyle="--", linewidth=2, label=f"Ramp-up limit (+{ru:g} MW/h)")
        ax2.axhline(-rd, color="darkred", linestyle="--", linewidth=2, label=f"Ramp-down limit (-{rd:g} MW/h)")
        ax2.axhline(0, color="black", linewidth=0.8)

        ax2.set_xlabel("Hour")
        ax2.set_ylabel("Ramp (MW/h)")
        ax2.grid(True, alpha=0.3, axis="y")
        ax2.legend(loc="upper right")

        # Annotation
        if n_up + n_dn > 0:
            ax2.text(
                0.02, 0.98,
                f"Violations: {n_up + n_dn} ({n_up} up, {n_dn} down)",
                transform=ax2.transAxes,
                va="top",
                fontsize=11,
                bbox=dict(boxstyle="round", facecolor="yellow", alpha=0.85),
            )
        else:
            ax2.text(
                0.02, 0.98,
                "All ramps within limits",
                transform=ax2.transAxes,
                va="top",
                fontsize=11,
                bbox=dict(boxstyle="round", facecolor="lightgreen", alpha=0.85),
            )

        plt.tight_layout()
        fname = os.path.join(output_folder, f"{unit}_ramping_check.png")
        plt.savefig(fname, dpi=300, bbox_inches="tight")
        plt.show()

# final_day_results should be a dataframe with columns: ['hour','vartype','unit','node','value']
final_day_results = export_results[start_day + steps_to_run - 2]

hydro_data = final_day_results.loc[final_day_results["vartype"] == "phydro", ["hour", "unit", "value"]]

# plot_hydro_ramping_check(
#     hydro_data=hydro_data,
#     hydro_RU=inputs.hydro_RU,
#     hydro_RD=inputs.hydro_RD,
#     output_folder=output_folder,
#     units_to_plot=None,   # or e.g. ["J_Percy_Priest"]
#     eps=1e-6,
# )


def plot_hydro_ramping(
    hydro_data: pd.DataFrame,
    hydro_RU: dict,
    hydro_RD: dict,
    output_folder: str,
    units_to_plot=None,
    eps: float = 1e-3,
    penalty_zones: dict[str, list[dict]] = None,
    hydro_max_capacity: dict[str, float] = None,
) -> None:
    """
    hydro_data: long dataframe with columns ['hour', 'unit', 'value'] for vartype='phydro'
    hydro_RU / hydro_RD: dict[unit] -> MW/h
    penalty_zones: dict[unit] -> list of dicts with keys 'min_pct', 'max_pct', 'penalty'
    hydro_max_capacity: dict[unit] -> MW (max capacity for converting percentages)
    eps: tolerance for ramping violations
    """
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import os

    if hydro_data.empty:
        print("No hydro dispatch to check.")
        return

    # --- Clean hour, ensure numeric, sort ---
    df = hydro_data.copy()
    df["hour"] = pd.to_numeric(df["hour"], errors="coerce")
    df = df.dropna(subset=["hour"])
    df["hour"] = df["hour"].astype(int)
    df = df.sort_values(["unit", "hour"])

    # --- Pivot: hour index, unit columns ---
    pivot = df.pivot(index="hour", columns="unit", values="value").sort_index()

    # Validate index integrity
    if pivot.index.has_duplicates:
        dupes = pivot.index[pivot.index.duplicated()].unique().tolist()
        raise ValueError(f"Duplicate hours in hydro pivot index: {dupes[:20]}...")

    # Choose units
    units = list(pivot.columns) if units_to_plot is None else [u for u in units_to_plot if u in pivot.columns]

    if not units:
        print("No matching hydro units to plot.")
        return

    os.makedirs(output_folder, exist_ok=True)

    for unit in units:
        dispatch = pivot[unit].dropna().sort_index()

        if dispatch.empty or len(dispatch) < 2:
            print(f"{unit}: not enough data to compute ramps.")
            continue

        ru = float(hydro_RU.get(unit, np.inf))
        rd = float(hydro_RD.get(unit, np.inf))

        ramps = dispatch.diff()  # MW/h; first is NaN
        ramps_no_na = ramps.dropna()

        # --- Violation logic with tolerance ---
        viol_up_mask = ramps_no_na > (ru + eps)
        viol_dn_mask = ramps_no_na < (-rd - eps)
        viol_mask = viol_up_mask | viol_dn_mask

        n_up = int(viol_up_mask.sum())
        n_dn = int(viol_dn_mask.sum())

        # --- Diagnostics ---
        max_ramp = float(ramps_no_na.max())
        min_ramp = float(ramps_no_na.min())

        if (n_up > 0) or (n_dn > 0):
            print(f"\n⚠️ RAMPING VIOLATIONS DETECTED for {unit}:")
            print(f"   Ramp-up violations: {n_up}")
            print(f"   Ramp-down violations: {n_dn}")
            print(f"   Max ramp change: {max_ramp:.12f} MW/h (limit: {ru:.12f})")
            print(f"   Min ramp change: {min_ramp:.12f} MW/h (limit: {-rd:.12f})")
            print("   Violation details (full precision):")
            viol_series = ramps_no_na[viol_mask].copy()
            resid = pd.Series(index=viol_series.index, dtype=float)
            resid.loc[viol_up_mask[viol_mask].index] = viol_series.loc[viol_up_mask] - ru
            resid.loc[viol_dn_mask[viol_mask].index] = (-rd) - viol_series.loc[viol_dn_mask]
            out = pd.DataFrame({"ramp": viol_series, "residual": resid})
            pd.set_option("display.precision", 15)
            print(out)
        else:
            print(f"\n✓ {unit}: all ramps within limits (eps={eps}).")
            print(f"   Max ramp change: {max_ramp:.12f} MW/h (limit: {ru:.12f})")
            print(f"   Min ramp change: {min_ramp:.12f} MW/h (limit: {-rd:.12f})")

        # --- Colors for bars (correct, sign-aware) ---
        colors = []
        for h, c in ramps_no_na.items():
            if c > ru + eps:
                colors.append("red")
            elif c < -rd - eps:
                colors.append("red")
            else:
                colors.append("green")

        # --- Plot ---
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

        # ============================================================
        # TOP PANEL: Dispatch with penalty zones
        # ============================================================

        # Get x-axis limits (hour range)
        x_min = dispatch.index.min()
        x_max = dispatch.index.max()

        # Plot penalty zones FIRST (so they appear behind the dispatch line)
        if penalty_zones and unit in penalty_zones and hydro_max_capacity:
            max_cap = hydro_max_capacity.get(unit, dispatch.max())
            zones = penalty_zones[unit]

            print(f"\n📊 Plotting penalty zones for {unit}:")
            print(f"   Max capacity: {max_cap:.2f} MW")
            print(f"   Number of zones: {len(zones)}")

            # Sort zones by penalty (ascending) for consistent shading
            zones_sorted = sorted(zones, key=lambda z: z["penalty"])

            # Create blue gradient: light blue for cheap, dark blue for expensive
            n_zones = len(zones_sorted)

            # Define color range
            light_blue = np.array([227/255, 242/255, 253/255])  # #E3F2FD
            dark_blue = np.array([13/255, 71/255, 161/255])     # #0D47A1

            legend_added = set()

            for idx, zone in enumerate(zones_sorted):
                # Calculate color intensity (0 = lightest, 1 = darkest)
                intensity = idx / max(1, n_zones - 1)

                # Interpolate color
                color = light_blue + intensity * (dark_blue - light_blue)

                # Convert percentages to MW
                min_mw = (zone["min_pct"] / 100.0) * max_cap
                max_mw = (zone["max_pct"] / 100.0) * max_cap

                print(f"   Zone {idx+1}: {zone['min_pct']:.0f}%-{zone['max_pct']:.0f}% "
                      f"({min_mw:.2f}-{max_mw:.2f} MW), penalty=${zone['penalty']:.0f}/MWh")

                # Determine zone label
                if zone["penalty"] >= 500:
                    zone_label = "High Penalty (≥$500/MWh)"
                    zone_type = "high"
                elif zone["penalty"] >= 50:
                    zone_label = "Medium Penalty ($50-500/MWh)"
                    zone_type = "medium"
                else:
                    zone_label = "Low/Zero Penalty (<$50/MWh)"
                    zone_type = "low"

                # Fill the entire zone area using axhspan (horizontal span)
                ax1.axhspan(
                    min_mw,
                    max_mw,
                    color=color,
                    alpha=0.4,
                    label=zone_label if zone_type not in legend_added else None,
                    zorder=1
                )
                legend_added.add(zone_type)

                # Add penalty annotation on the right side
                mid_mw = (min_mw + max_mw) / 2
                ax1.text(
                    1.01,
                    mid_mw,
                    f"${zone['penalty']:.0f}/MWh",
                    transform=ax1.get_yaxis_transform(),
                    verticalalignment='center',
                    fontsize=9,
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.9, edgecolor='gray')
                )

        # Plot dispatch line (on top of zones)
        ax1.plot(dispatch.index, dispatch.values, "-o", linewidth=2, markersize=3,
                color="darkblue", label="Dispatch", zorder=10)
        ax1.set_ylabel("Power (MW)", fontsize=12)
        ax1.set_title(f"{unit} - Dispatch and Ramping Check", fontsize=14, weight='bold')
        ax1.grid(True, alpha=0.3, zorder=0)
        ax1.legend(loc='upper left', fontsize=10, framealpha=0.95)

        # ============================================================
        # BOTTOM PANEL: Ramp bars
        # ============================================================
        ax2.bar(ramps_no_na.index, ramps_no_na.values, color=colors, alpha=0.75,
               edgecolor="black", linewidth=0.4)
        ax2.axhline(ru, color="darkred", linestyle="--", linewidth=2,
                   label=f"Ramp-up limit (+{ru:g} MW/h)")
        ax2.axhline(-rd, color="darkred", linestyle="--", linewidth=2,
                   label=f"Ramp-down limit (-{rd:g} MW/h)")
        ax2.axhline(0, color="black", linewidth=0.8)
        ax2.set_xlabel("Hour", fontsize=12)
        ax2.set_ylabel("Ramp (MW/h)", fontsize=12)
        ax2.grid(True, alpha=0.3, axis="y")
        ax2.legend(loc="upper right", fontsize=10)

        # Annotation
        if n_up + n_dn > 0:
            ax2.text(
                0.02, 0.98,
                f"Violations: {n_up + n_dn} ({n_up} up, {n_dn} down)",
                transform=ax2.transAxes,
                va="top",
                fontsize=11,
                bbox=dict(boxstyle="round", facecolor="yellow", alpha=0.85),
            )
        else:
            ax2.text(
                0.02, 0.98,
                "All ramps within limits",
                transform=ax2.transAxes,
                va="top",
                fontsize=11,
                bbox=dict(boxstyle="round", facecolor="lightgreen", alpha=0.85),
            )

        plt.tight_layout()
        fname = os.path.join(output_folder, f"{unit}_ramping_check.png")
        plt.savefig(fname, dpi=300, bbox_inches="tight")
        plt.show()


# Call the function
plot_hydro_ramping(
    hydro_data=hydro_data,
    hydro_RU=inputs.hydro_RU,
    hydro_RD=inputs.hydro_RD,
    penalty_zones=inputs.hydro_penalty_zones if inputs.use_hydro_penalty_zones else None,
    hydro_max_capacity=inputs.hydro_contracted_capacity,
    output_folder="./outputs"
)

# for i in range(1,6):
#     print(export_results[i][(export_results[i]['vartype'] == 'phydro') & (export_results[i]['unit'] == 'Barkley')]['value'].sum())
