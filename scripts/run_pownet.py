from datetime import datetime
from pownet.core import (
    SystemInput,
    ModelBuilder,
    SystemRecord,
    OutputProcessor,
    Visualizer,
)
from pownet.modeling import PowerSystemModel
from pownet.data_utils import create_init_condition

import gurobipy as gp
import pandas as pd

##### User inputs #####
sim_horizon = 24
model_name = "dummy_trade"
#######################

inputs = SystemInput(
    model_name=model_name,
    year=2016,
    sim_horizon=sim_horizon,
    spin_reserve_factor=0.15,
    load_shortfall_penalty_factor=1000,
    spin_shortfall_penalty_factor=1000,
)

inputs.load_check_and_print_summary()
model_builder = ModelBuilder(inputs)
init_conditions = create_init_condition(inputs.thermal_units)

record = SystemRecord(inputs)

steps_to_run = 2  # 365 - (sim_horizon // 24 - 1)
build_times = []
for step_k in range(1, steps_to_run):
    start_time = datetime.now()
    if step_k == 1:
        model = model_builder.build(
            step_k=step_k,
            init_conds=init_conditions,
        )
    else:
        # model = model_builder.update(step_k=step_k, init_conds=init_conditions)
        model = model_builder.build(
            step_k=step_k,
            init_conds=init_conditions,
        )
    build_time = datetime.now() - start_time

    power_system_model = PowerSystemModel(model)
    power_system_model.optimize()

    record.keep(power_system_model, step_k)
    init_conditions = record.get_init_conds()
    build_times.append(build_time.total_seconds())

# Process the results
output_processor = OutputProcessor(inputs)
node_var_df = record.get_node_variables()
output_processor.load(node_var_df)

# Visualize the results
visualizer = Visualizer(inputs.model_id)
visualizer.plot_fuelmix_bar(
    dispatch=output_processor.get_hourly_dispatch(),
    demand=output_processor.get_hourly_demand(),
    to_save=False,
)

# ==============================================================================
# record.write_simulation_results()

# # Save build_times to a csv file
# pd.DataFrame(build_times).to_csv("build_times.csv", index=False)
