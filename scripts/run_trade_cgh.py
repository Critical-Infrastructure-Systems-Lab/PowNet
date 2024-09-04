""" This script runs the bilateral trade under excess capacity scheme.
"""

import os
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")

import pandas as pd
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
from pypolp.dw.dw import DantzigWolfe, DWRecord
from pypolp.parser import parse_mps_with_orders, parse_mps, get_dataframe_orders


def create_dec_file(
    dec_filename: str,
    constr_df: pd.DataFrame,
) -> None:

    num_blocks = constr_df["block_id"].max()

    with open(dec_filename, "w") as f:
        # Unspecified constraints are put into the master problem
        f.write("CONSDEFAULTMASTER")
        f.write("\n")
        f.write("1")
        f.write("\n")

        # The decomposition was not from a presolved problem
        f.write("PRESOLVED")
        f.write("\n")
        f.write("0")
        f.write("\n")

        # The number of blocks is the number of thermal units
        f.write("NBLOCKS")
        f.write("\n")
        f.write(str(num_blocks))
        f.write("\n")

        # The indexing of .dec starts at one
        for subp_id in range(1, num_blocks + 1):
            # Write the block header
            f.write(f"BLOCK {subp_id}")
            f.write("\n")
            # Dump the constraints in each block
            block_constrs = constr_df.loc[
                constr_df["block_id"] == subp_id, "name"
            ].tolist()
            for block_constr in block_constrs:
                f.write(block_constr)
                f.write("\n")

        f.write("MASTERCONSS")
        f.write("\n")

        # Master constraints
        master_constrs = constr_df.loc[constr_df["block_id"] == 0, "name"].tolist()
        for master_constr in master_constrs:
            f.write(master_constr)
            f.write("\n")


def create_builder_and_record(
    model_name: str, year: int, sim_horizon: int, to_process_data: bool
) -> tuple:
    if to_process_data:
        logging.info(f"Creating PowNet input files for {model_name}")
        data_processor = DataProcessor(model_name=model_name, year=year, frequency=50)
        data_processor.execute_data_pipeline()

    inputs = SystemInput(
        model_name=model_name,
        year=year,
        sim_horizon=sim_horizon,
    )
    inputs.load_and_check_data()
    record = SystemRecord(inputs)
    return inputs, record


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


if __name__ == "__main__":

    model_name = "RegionAB"
    year = 2016
    sim_horizon = 48
    to_process_data = True
    steps_to_run = 3
    do_plot = True

    inputs, record = create_builder_and_record(
        model_name=model_name,
        year=year,
        sim_horizon=sim_horizon,
        to_process_data=to_process_data,
    )

    if steps_to_run is None:
        steps_to_run = 365 - (sim_horizon // 24 - 1)

    # Create DEC file first
    model_builder = ModelBuilder(inputs)
    init_conditions = create_init_condition(inputs.thermal_units)
    step_k = 1
    model = model_builder.build(step_k=step_k, init_conds=init_conditions)
    # Write the MPS file
    model.write(f"{model_name}_0.mps")

    # Group thermal units by region
    thermal_units_A = get_thermal_units("RegionA", year, sim_horizon)
    thermal_units_B = get_thermal_units("RegionB", year, sim_horizon)

    # Shared units
    nodes_A = get_nodes("RegionA", year, sim_horizon)
    nodes_B = get_nodes("RegionB", year, sim_horizon)
    shared_nodes = ["pHydro", "Node1", "Node2"]  # list(set(nodes_A) & set(nodes_B))

    thermal_unit_constrs = [
        "link_uvw_init",
        "link_uvw",
        "link_pthermal",
        "link_spin",
        "link_ppbar",
        "pthermal_lb",
        "pthermal_ub",
        "minDownInit",
        "minUpInit",
        "minDown",
        "minUp",
        "rampDownInit",
        "rampDown",
        "rampUpInit",
        "rampUp",
    ]

    # Loop through constr_names and assign to region A or B
    block_id = []
    constr_names = [constr.constrName for constr in model.getConstrs()]
    for constr_name in constr_names:
        # if any(prefix in constr_name for prefix in ["flowBal", "reserveReq1"]):
        #     block_id.append(0)
        if "reserveReq1" in constr_name:
            block_id.append(0)
        elif any([unit in constr_name for unit in shared_nodes]):
            block_id.append(0)
        elif any([unit in constr_name for unit in thermal_units_A]):
            block_id.append(1)
        elif any([unit in constr_name for unit in thermal_units_B]):
            block_id.append(2)
        elif any([node in constr_name for node in nodes_A]):
            block_id.append(1)
        elif any([node in constr_name for node in nodes_B]):
            block_id.append(2)

    constr_df = pd.DataFrame({"name": constr_names, "block_id": block_id})

    # Create a DEC file
    dec_filename = f"{model_name}.dec"
    create_dec_file(dec_filename, constr_df)

    # Get the row and column orders
    (_, A_df, _, _, col_df) = parse_mps(f"{model_name}_0.mps")
    row_order, col_order = get_dataframe_orders(dec_filename, A_df, col_df)
    del A_df
    del col_df

    for step_k in range(1, steps_to_run):
        if step_k == 1:
            model = model_builder.build(step_k=step_k, init_conds=init_conditions)
        else:
            model = model_builder.update(step_k=step_k, init_conds=init_conditions)

        # Write the MPS file
        mps_filename = f"{model_name}_{step_k}.mps"
        model.write(mps_filename)

        # Solve the model with Dantzig-Wolfe
        dw_problem = parse_mps_with_orders(mps_filename, row_order, col_order)
        # Remove MPS file
        os.remove(mps_filename)

        dw_record = DWRecord()
        dw_record.fit(dw_problem)

        dw_model = DantzigWolfe(
            max_iter=1000,
            dw_rmpgap=0.0000,
            dw_improve=0.0000,
        )

        dw_model.fit(dw_problem, dw_record)
        dw_model.solve(dw_record)
        dw_model.reoptimize_with_binary_weights()

        # Keep the results
        objval, solution = dw_model.get_solution(dw_record)
        solution = solution.reset_index(names=["varname"])

        record.keep(
            runtime=dw_model.get_total_runtime(),
            objval=objval,
            solution=solution,
            step_k=step_k,
        )

        init_conditions = record.get_init_conds()

    # Process the results
    output_processor = OutputProcessor(
        year=inputs.year,
        fuelmap=inputs.fuelmap,
        demand=inputs.demand,
    )
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

    # Remove DEC file
    # os.remove(dec_filename)


# Look at shortfall to s
