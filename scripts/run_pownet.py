import os
from datetime import datetime
from pownet.core import (
    DataProcessor,
    SystemInput,
    ModelBuilder,
    SystemRecord,
    OutputProcessor,
    Visualizer,
)
from pownet.data_utils import create_init_condition

##### User inputs #####
to_process_inputs = True
sim_horizon = 24
model_name = "dummy"
steps_to_run = 2  # Default is None
do_plot = True

input_folder = os.path.join("..", "model_library")
#######################

if to_process_inputs:
    data_processor = DataProcessor(
        input_folder=input_folder, model_name=model_name, year=2016, frequency=50
    )
    data_processor.execute_data_pipeline()

inputs = SystemInput(
    input_folder=input_folder,
    model_name=model_name,
    year=2016,
    sim_horizon=sim_horizon,
    spin_reserve_factor=0.15,
    load_shortfall_penalty_factor=1000,
    load_curtail_penalty_factor=1,
    spin_shortfall_penalty_factor=1000,
)
inputs.load_and_check_data()


model_builder = ModelBuilder(inputs)
record = SystemRecord(inputs)

build_times = []
init_conditions = create_init_condition(inputs.thermal_units)

if steps_to_run is None:
    steps_to_run = 10  # 365 - (sim_horizon // 24 - 1)

for step_k in range(1, steps_to_run):
    start_time = datetime.now()
    if step_k == 1:
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
    power_system_model.optimize(mipgap=0.001)

    # Raise an error if the model is not feasible
    if not power_system_model.check_feasible():
        raise ValueError("Model is not feasible.")

    record.keep(
        runtime=power_system_model.get_runtime(),
        objval=power_system_model.get_objval(),
        solution=power_system_model.get_solution(),
        step_k=step_k,
    )
    init_conditions = record.get_init_conds()


# Process the results
node_variables = record.get_node_variables()

output_processor = OutputProcessor()
output_processor.load(inputs)
hourly_generation = output_processor.get_hourly_generation(node_variables)
hourly_demand = output_processor.get_hourly_demand(inputs.demand)

# Similar methods are available to get monthly values
# monthly_generation = output_processor.get_monthly_generation(node_variables)
# monthly_demand = output_processor.get_monthly_demand(inputs.demand)

# Visualize the results
if do_plot:
    visualizer = Visualizer(inputs.model_id)

    visualizer.plot_fuelmix_bar(dispatch=hourly_generation, demand=hourly_demand)
