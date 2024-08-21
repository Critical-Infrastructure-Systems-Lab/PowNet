from datetime import datetime
import logging
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

# Print INFO level logs
logging.basicConfig(level=logging.INFO)

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
        # model_A = model_builder_A.update(
        #     step_k=step_k,
        #     init_conds=init_conditions_A,
        # )
        model_A = model_builder_A.build(
            step_k=step_k,
            init_conds=init_conditions_A,
        )

    power_system_model_A = PowerSystemModel(model_A)
    power_system_model_A.optimize()

    record_A.keep(power_system_model_A, step_k)
    init_conditions_A = record_A.get_init_conds()
# Process the results
output_processor_A = OutputProcessor(inputs_A)
node_var_df_A = record_A.get_node_variables()
output_processor_A.load_from_dataframe(node_var_df_A)

import_values_A = output_processor_A.get_import_values()


# # Visualize the results
# if do_plot:
#     visualizer_A = Visualizer(inputs_A.model_id)
#     if steps_to_run <= 3:
#         visualizer_A.plot_fuelmix_bar(
#             dispatch=output_processor_A.get_hourly_dispatch(),
#             demand=output_processor_A.get_hourly_demand(),
#             to_save=False,
#         )
#     else:
#         visualizer = Visualizer(inputs_A.model_id)
#         visualizer.plot_fuelmix_area(
#             dispatch=output_processor_A.get_daily_dispatch(),
#             demand=output_processor_A.get_daily_demand(),
#             to_save=False,
#         )

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

    record_B.keep(power_system_model_B, step_k)
    init_conditions_B = record_B.get_init_conds()
# Process the results
output_processor_B = OutputProcessor(inputs_B)
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


######### Print the results #########
# Total objective value of Region A
print(f"Total objective value of Region A: {int(sum(record_A.get_objvals()))}")
print(record_A.get_objvals())
# print(f"Total objective value of Region A: {int(sum(record_B.get_objvals()))}")
