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
model_name = "thailand"
steps_to_run = None  # Default is None
do_plot = True
#######################

############### Region A ################

if to_process_inputs:
    data_processor = DataProcessor(model_name=model_name, year=2016, frequency=50)
    data_processor.execute_data_pipeline()

inputs = SystemInput(
    model_name=model_name,
    year=2016,
    sim_horizon=sim_horizon,
    spin_reserve_factor=0.15,
    load_shortfall_penalty_factor=1000,
    spin_shortfall_penalty_factor=1000,
)
inputs.load_and_check_data()


model_builder = ModelBuilder(inputs)
init_conditions = create_init_condition(inputs.thermal_units)

record = SystemRecord(inputs)

build_times = []
opt_times = []
objvals = []

if steps_to_run is None:
    steps_to_run = 10  # 365 - (sim_horizon // 24 - 1)

for step_k in range(1, steps_to_run):
    start_time = datetime.now()
    if step_k == 1:
        model = model_builder.build(
            step_k=step_k,
            init_conds=init_conditions,
        )
    else:
        model = model_builder.update(
            step_k=step_k,
            init_conds=init_conditions,
        )
        # model = model_builder.build(
        #     step_k=step_k,
        #     init_conds=init_conditions,
        # )
    build_times.append((datetime.now() - start_time).total_seconds())

    power_system_model = PowerSystemModel(model)
    power_system_model.optimize(mipgap=0.001)
    objvals.append(power_system_model.get_objval())
    opt_times.append(power_system_model.get_runtime())

    record.keep(power_system_model, step_k)
    init_conditions = record.get_init_conds()

print(f"Objvals: {' '.join([str(int(objval)) for objval in record.get_objvals()])}")


# Process the results
output_processor = OutputProcessor(inputs)
node_var_df = record.get_node_variables()
output_processor.load_from_dataframe(node_var_df)

# Visualize the results
if do_plot:
    visualizer = Visualizer(inputs.model_id)
    if steps_to_run <= 3:
        visualizer.plot_fuelmix_bar(
            dispatch=output_processor.get_hourly_dispatch(),
            demand=output_processor.get_hourly_demand(),
            to_save=False,
        )
    else:
        visualizer = Visualizer(inputs.model_id)
        visualizer.plot_fuelmix_area(
            dispatch=output_processor.get_daily_dispatch(),
            demand=output_processor.get_daily_demand(),
            to_save=False,
        )


# record.write_simulation_results()

# Save build_times and objvals
import os
from pownet.folder_utils import get_output_dir
import pandas as pd

folder_dir = get_output_dir()
prefix_name = "warmstart"
df = pd.DataFrame(
    {
        "build_time": build_times,
        "opt_time": opt_times,
        "objval": objvals,
    }
)
df.to_csv(
    os.path.join(
        folder_dir, f"{prefix_name}_{inputs.model_name}_{sim_horizon}_modelstats.csv"
    ),
    index=False,
)
