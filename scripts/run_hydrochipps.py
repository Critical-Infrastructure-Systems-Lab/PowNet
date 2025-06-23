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

#%%########################################
#     Input Processing and Simulation Loop
###########################################
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

# Dictionaries to store results and models
power_system_model = {}
export_results = {}

# Outer loop over each rolling horizon day
for start_day in range(1, end_day):

    # === Apply updated weekly hydro budgets for this day ===
    first_values = {unit: values[start_day - 1] for unit, values in updated_weekly_budgets.items()}
    update_weekly_hydro_capacity(inputs.weekly_hydro_capacity, start_day, first_values)

    # === Apply updated weekly prices for this day ===
    update_contract_costs(inputs, 'supplier', weekly_contract_costs[start_day-1], start_day)

    # Optional: push updates into the model (uncomment if needed)
    # inputs.update_capacity()

    # Initialize model and record-keeping objects
    model_builder = ModelBuilder(inputs)
    record = SystemRecord(inputs)
    build_times = []
    opt_times = []
    objvals = []

    # Get initial condition state (e.g., generator status)
    init_conditions = create_init_condition(inputs.thermal_units)

    # === Inner loop: run multiple steps from this starting day ===
    if steps_to_run is None:
        steps_to_run = 10  # 365 - (sim_horizon // 24 - 1)

    #todo:select the start date
    for step_k in range(start_day, start_day+steps_to_run-1):
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
            # lmp=power_system_model[start_day].solve_for_lmp(),
            step_k=step_k,
        )
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

# for i in range(1,6):
#     print(export_results[i][(export_results[i]['vartype'] == 'phydro') & (export_results[i]['unit'] == 'Barkley')]['value'].sum())
