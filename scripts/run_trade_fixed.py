""" This script runs the bilateral under fixed contract scheme.
"""

import logging

from pownet.core import (
    SystemInput,
    ModelBuilder,
    SystemRecord,
    OutputProcessor,
    Visualizer,
)

import pandas as pd

from pownet.modeling import PowerSystemModel
from pownet.data_processor import DataProcessor
from pownet.data_utils import create_init_condition


def process_region(
    region_name: str,
    year: int,
    sim_horizon: int,
    steps_to_run: int = None,
    import_values: pd.DataFrame = None,
    to_process_inputs=True,
) -> tuple:

    if to_process_inputs:
        logging.info(f"Creating PowNet input files for {region_name}")
        data_processor = DataProcessor(model_name=region_name, year=year, frequency=50)
        data_processor.execute_data_pipeline()

    inputs = SystemInput(
        model_name=region_name,
        year=year,
        sim_horizon=sim_horizon,
        spin_reserve_factor=0,
        line_capacity_factor=0.9,
    )
    inputs.load_and_check_data()

    # Subtract hydro capacity from import values
    if import_values is not None:
        subtract_hydro_capacity(import_values, inputs)

    model_builder = ModelBuilder(inputs)
    init_conditions = create_init_condition(inputs.thermal_units)
    record = SystemRecord(inputs)

    if steps_to_run is None:
        steps_to_run = 365 - (sim_horizon // 24 - 1)

    for step_k in range(1, steps_to_run):
        if step_k == 1:
            model = model_builder.build(step_k=step_k, init_conds=init_conditions)
        else:
            model = model_builder.update(step_k=step_k, init_conds=init_conditions)

        power_system_model = PowerSystemModel(model)
        power_system_model.optimize(log_to_console=False)

        record.keep(
            runtime=power_system_model.get_runtime(),
            objval=power_system_model.get_objval(),
            solution=power_system_model.get_solution(),
            step_k=step_k,
        )
        init_conditions = record.get_init_conds()

    # Process results
    output_processor = OutputProcessor(
        year=inputs.year, fuelmap=inputs.fuelmap, demand=inputs.demand
    )
    node_var_df = record.get_node_variables()
    output_processor.load_from_dataframe(node_var_df)

    return inputs, output_processor, record


def subtract_hydro_capacity(import_values_A, inputs_B):
    inputs_B.hydro_capacity -= import_values_A
    return


def check_shared_units(output_processor_A, output_processor_B) -> set:
    """Check that shared units are import_units in A and export_units in B"""
    temp_df = output_processor_A.node_variables
    units_in_A = temp_df[temp_df["vartype"] == "pimp"].node.unique()
    units_in_B = output_processor_B.node_variables.node.unique()
    shared_units1 = set(units_in_A).intersection(set(units_in_B))
    shared_units2 = set(output_processor_A.node_variables.node.unique()).intersection(
        set(output_processor_B.node_variables.node.unique())
    )
    assert shared_units1 == shared_units2
    return shared_units1


def adjust_node_variables(output_processor_A, output_processor_B, shared_units):
    """Adjust node variables for shared units"""
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

    return node_variables_A_adjusted, node_variables_B_adjusted


def create_output_processor(year, fuelmap, demand, node_variables):
    """Helper function to create and load an OutputProcessor."""
    output_processor = OutputProcessor(year=year, fuelmap=fuelmap, demand=demand)
    output_processor.load_from_dataframe(node_variables.reset_index())
    return output_processor


def combine_output_processors(
    output_processor_A,
    output_processor_B,
):
    """Combine output processors from two regions."""
    year = output_processor_A.year
    fuelmap = output_processor_A.fuelmap.copy()
    fuelmap.update(output_processor_B.fuelmap)
    demand_AB = pd.concat(
        [output_processor_A.demand, output_processor_B.demand], axis=1
    )

    output_processor = OutputProcessor(year=year, fuelmap=fuelmap, demand=demand_AB)
    # Use the adjusted node variables from both regions
    node_var_df = pd.concat(
        [output_processor_A.node_variables, output_processor_B.node_variables], axis=0
    )
    output_processor.load_from_dataframe(node_var_df)
    return output_processor


def plot_fuelmix(steps_to_run: int, model_id: str, output_processor: OutputProcessor):
    if steps_to_run <= 3:
        visualizer = Visualizer(model_id)
        visualizer.plot_fuelmix_bar(
            dispatch=output_processor.get_hourly_dispatch(),
            demand=output_processor.get_hourly_demand(),
            to_save=False,
        )
    else:
        visualizer = Visualizer(model_id)
        visualizer.plot_fuelmix_area(
            dispatch=output_processor.get_daily_dispatch(),
            demand=output_processor.get_daily_demand(),
            to_save=False,
        )


def print_summary(objvals: list[float]) -> None:
    print("\n\n====== Summary ======")
    print("Total objective value: ", sum(objvals))
    print("Individual objective values: ", objvals)


def main():
    logging.basicConfig(level=logging.INFO)
    logging.basicConfig(format="%(message)s")

    steps_to_run = 3

    # Region A
    inputs_A, output_processor_A, record_A = process_region(
        region_name="RegionA",
        year=2016,
        sim_horizon=24,
        steps_to_run=steps_to_run,
    )

    # Region B
    inputs_B, output_processor_B, record_B = process_region(
        region_name="RegionB",
        year=2016,
        sim_horizon=24,
        steps_to_run=steps_to_run,
        import_values=output_processor_A.get_import_values(),
    )

    # Adjust import/export values
    shared_units = check_shared_units(output_processor_A, output_processor_B)
    node_variables_A_adj, node_variables_B_adj = adjust_node_variables(
        output_processor_A, output_processor_B, shared_units
    )

    # Create output processors
    output_processor_A_adj = create_output_processor(
        year=output_processor_A.year,
        fuelmap=output_processor_A.fuelmap,
        demand=output_processor_A.demand,
        node_variables=node_variables_A_adj,
    )

    output_processor_B_adj = create_output_processor(
        year=2016,
        fuelmap=output_processor_B.fuelmap,
        demand=output_processor_B.demand,
        node_variables=node_variables_B_adj,
    )

    # Visualize the results
    plot_fuelmix(steps_to_run, inputs_A.model_id, output_processor_A)
    plot_fuelmix(steps_to_run, inputs_B.model_id, output_processor_B)

    # Combine the total dispatch
    output_processor = combine_output_processors(
        output_processor_A,
        output_processor_B,
    )

    # Visualize the results
    plot_fuelmix(steps_to_run, inputs_A.model_id, output_processor)

    objvals_A = record_A.get_objvals()
    objvals_B = record_B.get_objvals()

    objvals = zip(objvals_A, objvals_B)

    objvals = [x + y for x, y in objvals]

    print_summary([record_A.get_objval(), record_B.get_objval()])


if __name__ == "__main__":
    main()
