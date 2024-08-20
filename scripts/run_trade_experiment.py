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
model_name = "RegionB"
has_import = False
steps_to_run = None  # Default is None
do_plot = True
#######################

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

if steps_to_run is None:
    steps_to_run = 365 - (sim_horizon // 24 - 1)
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
    power_system_model.optimize(log_to_console=False)

    record.keep(power_system_model, step_k)
    init_conditions = record.get_init_conds()
    build_times.append(build_time.total_seconds())

# Process the results
output_processor = OutputProcessor(inputs)
node_var_df = record.get_node_variables()
output_processor.load_from_dataframe(node_var_df)

if has_import:
    import_values = output_processor.get_import_values()


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
