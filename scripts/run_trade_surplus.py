""" This script runs the bilateral trade under excess capacity scheme.
"""

from __future__ import annotations

import numpy as np
from pownet.core import (
    SystemInput,
    ModelBuilder,
    SystemRecord,
    OutputProcessor,
)
from pownet.modeling import PowerSystemModel
from pownet.data_utils import create_init_condition
from run_bilat_fixed import plot_fuelmix, combine_output_processors


def get_system_inputs(
    model_name: str,
    year: int,
    sim_horizon: int,
) -> list[str]:
    inputs = SystemInput(
        model_name=model_name,
        year=year,
        sim_horizon=sim_horizon,
    )
    inputs.load_data()
    return inputs


def get_thermal_units(region: str, year: int, sim_horizon: int) -> list[str]:
    inputs = get_system_inputs(region, year, sim_horizon)
    return inputs.thermal_units


def get_nodes(region: str, year: int, sim_horizon: int) -> list[str]:
    inputs = get_system_inputs(region, year, sim_horizon)
    return inputs.nodes


def create_model(
    model_builder: ModelBuilder, init_conds: dict, step_k: int
) -> "gp.Model":
    if step_k == 1:
        return model_builder.build(
            step_k=step_k,
            init_conds=init_conds,
        )
    else:
        return model_builder.update(
            step_k=step_k,
            init_conds=init_conds,
        )


def print_summary(objvals: list[float]) -> None:
    print("\n\n====== Summary ======")
    print("Total objective value: ", sum(objvals))
    print("Individual objective values: ", objvals)


def main():
    year = 2016
    sim_horizon = 24
    steps_to_run = 3
    mipgap = 0.001

    if steps_to_run is None:
        steps_to_run = 365 - (sim_horizon // 24 - 1)

    # Shared units
    nodes_A = get_nodes("RegionA", year, sim_horizon)
    nodes_B = get_nodes("RegionB", year, sim_horizon)
    shared_nodes = list(set(nodes_A) & set(nodes_B))

    #########################################################################
    # Initialize inputs, model builder, record, and initial conditions for each region
    #########################################################################
    inputs_A = SystemInput(
        model_name="RegionA",
        year=year,
        sim_horizon=sim_horizon,
    )
    inputs_A.load_and_check_data()
    model_builder_A = ModelBuilder(inputs_A)
    record_A = SystemRecord(inputs_A)
    init_conds_A = create_init_condition(inputs_A.thermal_units)

    # Since A is the importing region, we void its import capacity and prices to
    # avoid potential bugs
    inputs_A.import_capacity.loc[:, shared_nodes] = np.nan
    inputs_A.unit_marginal_cost.loc[:, shared_nodes] = np.nan

    inputs_B = SystemInput(
        model_name="RegionB",
        year=year,
        sim_horizon=sim_horizon,
    )
    inputs_B.load_and_check_data()
    model_builder_B = ModelBuilder(inputs_B)
    record_B = SystemRecord(inputs_B)
    init_conds_B = create_init_condition(inputs_B.thermal_units)

    objvals = []

    for step_k in range(1, steps_to_run):
        ################################
        # Build and solve model B
        ################################
        model_B = create_model(model_builder_B, init_conds_B, step_k)
        power_system_B = PowerSystemModel(model_B)
        power_system_B.optimize(mipgap=mipgap)

        record_B.keep(
            runtime=power_system_B.get_runtime(),
            objval=power_system_B.get_objval(),
            solution=power_system_B.get_solution(),
            lmp=power_system_B.solve_for_lmp(),
            step_k=step_k,
        )
        init_conds_B = record_B.get_init_conds()

        ################################
        # Exchange data between regions
        ################################

        export_capacity = power_system_B.solve_for_export_capacity(
            shared_nodes, inputs_B.sim_horizon, step_k
        )

        export_prices = power_system_B.solve_for_export_prices(
            shared_nodes, inputs_B.sim_horizon, step_k
        )

        for node in shared_nodes:
            inputs_A.import_capacity.loc[export_capacity.index, node] = export_capacity[
                node
            ]
            inputs_A.unit_marginal_cost.loc[export_capacity.index, node] = (
                export_prices[node]
            )

        ################################
        # Build and solve model A
        ################################
        model_A = create_model(model_builder_A, init_conds_A, step_k)
        power_system_A = PowerSystemModel(model_A)
        power_system_A.optimize(mipgap=mipgap)

        record_A.keep(
            runtime=power_system_A.get_runtime(),
            objval=power_system_A.get_objval(),
            solution=power_system_A.get_solution(),
            lmp=power_system_A.solve_for_lmp(),
            step_k=step_k,
        )
        init_conds_A = record_A.get_init_conds()

        objvals.append(power_system_A.get_objval() + power_system_B.get_objval())

    ################################
    # Process the results
    ################################
    output_processor_A = OutputProcessor(
        year=inputs_A.year,
        fuelmap=inputs_A.fuelmap,
        demand=inputs_A.demand,
    )
    node_var_df_A = record_A.get_node_variables()
    output_processor_A.load_from_dataframe(node_var_df_A)

    output_processor_B = OutputProcessor(
        year=inputs_B.year,
        fuelmap=inputs_B.fuelmap,
        demand=inputs_B.demand,
    )
    node_var_df_B = record_B.get_node_variables()
    output_processor_B.load_from_dataframe(node_var_df_B)

    plot_fuelmix(steps_to_run, inputs_A.model_id, output_processor_A)
    plot_fuelmix(steps_to_run, inputs_B.model_id, output_processor_B)

    # Combine the total dispatch
    output_processor = combine_output_processors(
        output_processor_A,
        output_processor_B,
    )

    # Visualize the results
    plot_fuelmix(steps_to_run, inputs_A.model_id, output_processor)

    print_summary(objvals)


if __name__ == "__main__":
    main()
