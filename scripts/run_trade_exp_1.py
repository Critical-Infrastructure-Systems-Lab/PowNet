from datetime import datetime
from pownet.core import (
    SystemInput,
    ModelBuilder,
    SystemRecord,
    OutputProcessor,
    Visualizer,
)
from pownet.modeling import PowerSystemModel
from pownet.data_processor import DataProcessor
from pownet.data_utils import create_init_condition

##### User inputs #####
to_process_inputs = True
sim_horizon = 24
steps_to_run = 3  # Default is None
do_plot = True


def subtract_hydro_capacity(import_values_A, inputs_B):
    inputs_B.hydro_capacity -= import_values_A
    return


def separate_node_variables(node_var_df):
    """Return the node variables for each region."""
    pass


#########################################
############### Region A ################
#########################################
if to_process_inputs:
    data_processor_A = DataProcessor(
        model_name="RegionA",
        year=2016,
        frequency=50,
    )
    data_processor_A.execute_data_pipeline()

inputs_A = SystemInput(
    model_name="RegionA",
    year=2016,
    sim_horizon=sim_horizon,
    spin_reserve_factor=0.15,
    load_shortfall_penalty_factor=1000,
    spin_shortfall_penalty_factor=1000,
)
inputs_A.load_and_check_data()


model_builder_A = ModelBuilder(inputs_A)
init_conditions_A = create_init_condition(inputs_A.thermal_units)

record_A = SystemRecord(inputs_A)

if steps_to_run is None:
    steps_to_run = 365 - (sim_horizon // 24 - 1)

for step_k in range(1, steps_to_run):
    if step_k == 1:
        model_A = model_builder_A.build(
            step_k=step_k,
            init_conds=init_conditions_A,
        )
    else:
        model_A = model_builder_A.update(
            step_k=step_k,
            init_conds=init_conditions_A,
        )

    power_system_model_A = PowerSystemModel(model_A)
    power_system_model_A.optimize()

    record_A.keep(
        runtime=power_system_model_A.get_runtime(),
        objval=power_system_model_A.get_objval(),
        solution=power_system_model_A.get_solution(),
        step_k=step_k,
    )
    init_conditions_A = record_A.get_init_conds()

# Process the results
output_processor_A = OutputProcessor(
    year=inputs_A.year,
    fuelmap=inputs_A.fuelmap,
    demand=inputs_A.demand,
)
node_var_df_A = record_A.get_node_variables()
output_processor_A.load_from_dataframe(node_var_df_A)

import_values_A = output_processor_A.get_import_values()

#########################################
############### Region B ################
#########################################

if to_process_inputs:
    data_processor_B = DataProcessor(
        model_name="RegionB",
        year=2016,
        frequency=50,
    )
    data_processor_B.execute_data_pipeline()

inputs_B = SystemInput(
    model_name="RegionB",
    year=2016,
    sim_horizon=sim_horizon,
    spin_reserve_factor=0.15,
    load_shortfall_penalty_factor=1000,
    spin_shortfall_penalty_factor=1000,
)
inputs_B.load_and_check_data()

# Subtract hydropower_capacity from what Region A is importing
subtract_hydro_capacity(import_values_A, inputs_B)

model_builder_B = ModelBuilder(inputs_B)
init_conditions_B = create_init_condition(inputs_B.thermal_units)

record_B = SystemRecord(inputs_B)

if steps_to_run is None:
    steps_to_run = 365 - (sim_horizon // 24 - 1)

for step_k in range(1, steps_to_run):
    if step_k == 1:
        model_B = model_builder_B.build(
            step_k=step_k,
            init_conds=init_conditions_B,
        )
    else:
        # model = model_builder.update(step_k=step_k, init_conds=init_conditions)
        model_B = model_builder_B.build(
            step_k=step_k,
            init_conds=init_conditions_B,
        )

    power_system_model_B = PowerSystemModel(model_B)
    power_system_model_B.optimize(log_to_console=False)

    record_B.keep(
        runtime=power_system_model_B.get_runtime(),
        objval=power_system_model_B.get_objval(),
        solution=power_system_model_B.get_solution(),
        step_k=step_k,
    )
    init_conditions_B = record_B.get_init_conds()
# Process the results
output_processor_B = OutputProcessor(
    year=inputs_B.year,
    fuelmap=inputs_B.fuelmap,
    demand=inputs_B.demand,
)
node_var_df_B = record_B.get_node_variables()
output_processor_B.load_from_dataframe(node_var_df_B)

# Visualize the results
if do_plot:
    visualizer_B = Visualizer(inputs_B.model_id)
    if steps_to_run <= 3:
        visualizer_B.plot_fuelmix_bar(
            dispatch=output_processor_B.get_hourly_dispatch(),
            demand=output_processor_B.get_hourly_demand(),
            to_save=False,
        )
    else:
        visualizer = Visualizer(inputs_B.model_id)
        visualizer.plot_fuelmix_area(
            dispatch=output_processor_B.get_daily_dispatch(),
            demand=output_processor_B.get_daily_demand(),
            to_save=False,
        )


#########################################
#### Separate data by region ############
#########################################
""" Things to do:
- Shared units should be only those units that are imported from Region A
"""
units_in_A = output_processor_A.node_variables.node.unique()
units_in_B = output_processor_B.node_variables.node.unique()

shared_units = set(units_in_A).intersection(set(units_in_B))
# Check that shared units are considered as 'pimp' in one of the regions
for unit in shared_units:

    if unit in output_processor_A.node_variables.node.unique():
        print(f"{unit} is in A")
    if unit in output_processor_B.node_variables.node.unique():
        print(f"{unit} is in B")

# Add dispatch from import units in Region A to their respective units in Region B
import_df = output_processor_A.node_variables[
    output_processor_A.node_variables.node.isin(shared_units)
].copy()

export_df = output_processor_B.node_variables[
    output_processor_B.node_variables.node.isin(shared_units)
].copy()

# Add the value columns of both data frames
# if the dispatch when "node" and hour are the same.
import_df = import_df.set_index(["node", "hour"])
export_df = export_df.set_index(["node", "hour"])
export_df.loc[import_df.index, "value"] += import_df["value"]

# Adjust the node variables in both regions
node_variables_A_adjusted = output_processor_A.node_variables.copy()
node_variables_A_adjusted = node_variables_A_adjusted.set_index(["node", "hour"])
node_variables_B_adjusted = output_processor_B.node_variables.copy()
node_variables_B_adjusted = node_variables_B_adjusted.set_index(["node", "hour"])

# Update the values of the shared units in Region B
node_variables_B_adjusted.loc[export_df.index, "value"] = export_df["value"]

# Update the values of the shared units in Region A to zero
node_variables_A_adjusted.loc[import_df.index, "value"] = 0


output_processor_A_adjusted = OutputProcessor(
    year=inputs_A.year, fuelmap=inputs_A.fuelmap, demand=output_processor_A.demand
)
output_processor_A_adjusted.load_from_dataframe(node_variables_A_adjusted.reset_index())

output_processor_B_adjusted = OutputProcessor(
    year=inputs_B.year, fuelmap=inputs_B.fuelmap, demand=output_processor_B.demand
)
output_processor_B_adjusted.load_from_dataframe(node_variables_B_adjusted.reset_index())


#########################################
#### Plot data by region ################
#########################################

visualizer_A_adjusted = Visualizer(inputs_A.model_id)
visualizer_A_adjusted.plot_fuelmix_bar(
    dispatch=output_processor_A_adjusted.get_hourly_dispatch(),
    demand=output_processor_A.get_hourly_demand(),
    to_save=False,
)

visualizer_B = Visualizer(inputs_B.model_id)
visualizer_B.plot_fuelmix_bar(
    dispatch=output_processor_B_adjusted.get_hourly_dispatch(),
    demand=output_processor_B.get_hourly_demand(),
    to_save=False,
)


#########################################
#### Combine the total dispatch
#########################################
import pandas as pd

# Total objective value
print(f"Total objective value of Region A: {int(sum(record_A.get_objvals()))}")
print(f"Total objective value of Region B: {int(sum(record_B.get_objvals()))}")

year = inputs_A.year
fuelmap = inputs_A.fuelmap.copy()
fuelmap.update(inputs_B.fuelmap)
demand_AB = pd.concat([output_processor_A.demand, output_processor_B.demand], axis=1)

output_processor = OutputProcessor(year=year, fuelmap=fuelmap, demand=demand_AB)

node_var_df_A = record_A.get_node_variables()
node_var_df_B = record_B.get_node_variables()
node_var_df = pd.concat([node_var_df_A, node_var_df_B], axis=0)
output_processor.load_from_dataframe(node_var_df)

# Visualize the results
if do_plot:
    visualizer = Visualizer(inputs_A.model_id)
    if steps_to_run <= 3:
        visualizer.plot_fuelmix_bar(
            dispatch=output_processor.get_hourly_dispatch(),
            demand=output_processor.get_hourly_demand(),
            to_save=False,
        )
    else:
        visualizer = Visualizer(inputs_A.model_id)
        visualizer.plot_fuelmix_area(
            dispatch=output_processor.get_daily_dispatch(),
            demand=output_processor.get_daily_demand(),
            to_save=False,
        )
