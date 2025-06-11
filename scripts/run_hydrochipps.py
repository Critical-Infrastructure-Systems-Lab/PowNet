#%%
import os
from pownet.core import Simulator, DataProcessor, OutputProcessor

##### User inputs #####
scen_path = ".\\model_library"
results_path = ".\\results"
to_process_inputs = True
sim_horizon = 24*7
model_name = "cumberland"
steps_to_run = 3  # Default is None
do_plot = True


if to_process_inputs:
    data_processor = DataProcessor(
        input_folder=scen_path, model_name=model_name, year=2016, frequency=50
    )
    data_processor.execute_data_pipeline()

simulator = Simulator(
    input_folder=scen_path,
    model_name=model_name,
    model_year=2016,
    spin_reserve_factor=0,
    load_shortfall_penalty_factor=1000,
    load_curtail_penalty_factor=1,
    spin_shortfall_penalty_factor=1000,
    line_capacity_factor=1,
    line_loss_factor=0
)

simulator.run(
    sim_horizon=sim_horizon,
    steps_to_run=steps_to_run,
    # solver='gurobi',
)

# Write the simulation results
output_folder = results_path + '\\' + model_name
if not os.path.exists(output_folder):
    os.makedirs(output_folder)
simulator.write_results(output_folder)

simulator.plot_fuelmix("area", output_folder)

output_processor = OutputProcessor()
hourly_demand = output_processor.get_hourly_demand(simulator.inputs.demand)

# old code
#%%
import os
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

scen_path = ".\\model_library"
##### User inputs #####
to_process_inputs = True
sim_horizon = 24*7
model_name = "cumberland"
steps_to_run = 3  # Default is None
do_plot = True
#######################

if to_process_inputs:
    data_processor = DataProcessor(
        input_folder=scen_path, model_name=model_name, year=2016, frequency=50
    )
    data_processor.execute_data_pipeline()

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
    line_loss_factor=0
)
inputs.load_and_check_data()


model_builder = ModelBuilder(inputs)
record = SystemRecord(inputs)

build_times = []
opt_times = []
objvals = []
init_conditions = create_init_condition(inputs.thermal_units) # init conditions should be empty dict if we dont have any thermal generators

if steps_to_run is None:
    steps_to_run = 10  # 365 - (sim_horizon // 24 - 1)

start_day = 1
for step_k in range(start_day, steps_to_run):
    start_time = datetime.now()
    if step_k == start_day:
        power_system_model = model_builder.build(
            step_k=step_k,
            init_conds=init_conditions,
        )
    else:
        power_system_model = model_builder.update(
            step_k=step_k,
            init_conds=init_conditions,
        )
    build_times.append((datetime.now() - start_time).total_seconds())

    # power_system_model.model.write(str(step_k) + '.lp')
    power_system_model.optimize(mipgap=0.001)

    # Raise an error if the model is not feasible
    if not power_system_model.check_feasible():
        raise ValueError("Model is not feasible.")

    objvals.append(power_system_model.get_objval())
    opt_times.append(power_system_model.get_runtime())

    record.keep(
        runtime=power_system_model.get_runtime(),
        objval=power_system_model.get_objval(),
        solution=power_system_model.get_solution(),
        lmp=power_system_model.solve_for_lmp(),
        step_k=step_k,
    )
    init_conditions = record.get_init_conds()

import os
output_folder = ".//outputs"
if not os.path.exists(output_folder):
    os.makedirs(output_folder)
record.write_simulation_results(output_folder)



# output_folder = ".//outputs"
# if not os.path.exists(output_folder):
#     os.makedirs(output_folder)
# results.write_results(output_folder)

import pandas as pd
# Process the results
output_processor = OutputProcessor()
output_processor.load(inputs=inputs)
# output_processor = OutputProcessor(inputs)
node_var_df = record.get_node_variables()
output_processor.get_hourly_generation(node_var_df)
# output_processor.load_from_dataframe(node_var_df)

output_processor.get_thermal_unit_hourly_dispatch(node_var_df)
a = output_processor.get_unit_hourly_generation(node_var_df)
# Visualize the results
if do_plot:
    visualizer = Visualizer(inputs.model_id)
    if steps_to_run <= 7:
        visualizer.plot_fuelmix_bar(
            dispatch=output_processor.get_hourly_generation(node_var_df),
            demand=output_processor.get_hourly_demand(inputs.demand),
        )
        visualizer.plot_lmp(record.lmp_df)
    else:
        visualizer = Visualizer(inputs.model_id)
        visualizer.plot_fuelmix_area(
            dispatch=output_processor.get_daily_dispatch(),
            demand=output_processor.get_daily_demand(),
        )


# # Save other modeling statistics
# import os
# from pownet.folder_utils import get_output_dir
# import pandas as pd
#
# folder_dir = get_output_dir()
# prefix_name = "warmstart"
# df = pd.DataFrame(
#     {
#         "build_time": build_times,
#         "opt_time": opt_times,
#         "objval": objvals,
#     }
# )
# df.to_csv(
#     os.path.join(
#         folder_dir,
#         f"branch{prefix_name}_{inputs.model_name}_{sim_horizon}_modelstats.csv",
#     ),
#     index=False,
# )