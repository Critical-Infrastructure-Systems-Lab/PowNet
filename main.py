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


def main():
    ##### User inputs #####
    to_process_inputs = True
    model_year = 2016
    sim_horizon = 24
    model_name = "RegionAB"
    steps_to_run = 3  # If None, then run the whole year
    do_plot = True
    do_write_results = True

    ####################### Processing inputs
    if steps_to_run is None:
        steps_to_run = 365 - (sim_horizon // 24 - 1)

    # To create files with "pownet_" prefix
    if to_process_inputs:
        data_processor = DataProcessor(
            model_name=model_name, year=model_year, frequency=50
        )
        data_processor.execute_data_pipeline()

    inputs = SystemInput(
        model_name=model_name,
        year=model_year,
        sim_horizon=sim_horizon,
        spin_reserve_factor=0.15,
        load_shortfall_penalty_factor=1000,
        load_curtail_penalty_factor=1,
        spin_shortfall_penalty_factor=1000,
    )
    # Produce an error if the data is not making sense
    inputs.load_and_check_data()

    ####################### Simulation
    record = SystemRecord(inputs)
    model_builder = ModelBuilder(inputs)

    # Initially, all thermal units are off. They have to be switched on from cold start
    init_conditions = create_init_condition(inputs.thermal_units)

    for step_k in range(1, steps_to_run):
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

        power_system_model = PowerSystemModel(model)
        power_system_model.optimize(mipgap=0.001)

        record.keep(
            runtime=power_system_model.get_runtime(),
            objval=power_system_model.get_objval(),
            solution=power_system_model.get_solution(),
            step_k=step_k,
        )
        init_conditions = record.get_init_conds()

    ####################### Processing outputs
    output_processor = OutputProcessor(
        year=inputs.year,
        fuelmap=inputs.fuelmap,
        demand=inputs.demand,
    )
    node_var_df = record.get_node_variables()
    output_processor.load_from_dataframe(node_var_df)

    # If objvals are needed
    objvals = record.get_objvals()

    ####################### Visualize the results
    if do_plot:
        visualizer = Visualizer(inputs.model_id)
        if steps_to_run <= 3:
            visualizer.plot_fuelmix_bar(
                dispatch=output_processor.get_hourly_dispatch(),
                demand=output_processor.get_hourly_demand(),
                to_save=False,
            )
        else:
            visualizer = Visualizer(model_id=inputs.model_id)
            visualizer.plot_fuelmix_area(
                dispatch=output_processor.get_daily_dispatch(),
                demand=output_processor.get_daily_demand(),
                to_save=False,
            )

    ####################### Write outputs
    # Write three csv files to the output directory: node variables,
    # system variables, and flow variables
    if do_write_results:
        record.write_simulation_results()


if __name__ == "__main__":
    main()
