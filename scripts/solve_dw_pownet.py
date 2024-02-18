"""
Run experments with Dantzig-Wolfe decomposition for the PowNet model
The script will collect statistics of each instance and save them in a csv file.
"""

import csv
from datetime import datetime
import os

import gurobipy as gp
import pandas as pd

from pownet.folder_sys import get_temp_dir, get_output_dir, count_mps_files
from pypolp.dw.dw import DantzigWolfe, DWRecord
from pypolp.parser import parse_mps_with_orders, parse_mps, get_dataframe_orders
from pypolp.functions import get_non_binary_from_df
from solve_new_rounding_pownet import calculate_set_mipgap


def run_dw_experiment(
    model_name: str,
    T_simulate: int,
    set_rmpgap: float,
    set_dwimprove: float,
    relax_subproblems: bool,
) -> None:
    # Start time
    timer_script = datetime.now()
    ctime = timer_script.strftime("%Y%m%d_%H%M")

    true_objvals = pd.read_csv(
        os.path.join(
            get_temp_dir(),
            "true_values",
            f"{model_name}_{T_simulate}.csv",
        ),
        usecols=["mip_objval"],
        header=0,
    )

    print(f"\nDW-PowNet: ==== Begin collecting statistics for {model_name} ====")

    # Define the session name and create a folder to save the outputs
    output_dir = os.path.join(get_temp_dir(), "new_dw_stats")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    session_name = f"{ctime}_{model_name}_{T_simulate}_{set_rmpgap}_{set_dwimprove}_{relax_subproblems}"

    # Extract row/column orders to parse the DW structure
    instance_folder = os.path.join(
        get_output_dir(), f"{model_name}_{T_simulate}_instances"
    )
    path_dec = os.path.join(instance_folder, f"{model_name}.dec")
    path_mps = os.path.join(instance_folder, f"{model_name}_0.mps")
    (_, A_df, _, _, col_df) = parse_mps(path_mps)
    row_order, col_order = get_dataframe_orders(path_dec, A_df, col_df)
    del A_df
    del col_df

    # Collect statistics to compare computational performance
    FIELDS = [
        "model_name",
        "T_simulate",
        "set_rmpgap",
        "set_dwimprove",
        "master_itercount",
        "master_time",
        "master_mip_time",  # Time to reoptimize with binary weights
        "subp_itercount",
        "subp_time",
        "dw_itercount",
        "dw_total_time",
        "dw_objval",
        "dw_rmpgap",
        "dw_improve",
        "dw_mip_objval",
        "set_mipgap",  # Competitive MIPGap for Gurobi
        "mip_gurobi_time",
        "mip_objval",
        "lp_gurobi_time",
        "lp_objval",
        "wall_clock_dw",
        "wall_clock_mip_gurobi",
        "wall_clock_lp_gurobi",
        "true_objval",
    ]

    # Create a csv file with only headers. We will append to this csv later.
    csv_name = os.path.join(output_dir, f"{session_name}_dwstats.csv")
    with open(csv_name, "w", newline="", encoding="utf-8") as csvfile:
        # creating a csv writer object
        csvwriter = csv.writer(csvfile)
        # writing the fields
        csvwriter.writerow(FIELDS)

    # Count the number of files ending with .mps
    # Days are labeled from k = 0 to k = 364 (max)
    num_instances = count_mps_files(instance_folder)
    for k in range(num_instances):
        print(f"\n\nDW-PowNet: === Solving step {k} ===")
        path_mps = os.path.join(instance_folder, f"{model_name}_{k}.mps")

        # ----- Solve with Dantzig-Wolfe
        timer_dw = datetime.now()
        dw_problem = parse_mps_with_orders(path_mps, row_order, col_order)
        record = DWRecord()
        record.fit(dw_problem)

        dw_model = DantzigWolfe(
            dw_rmpgap=set_rmpgap,
            dw_improve=set_dwimprove,
            relax_subproblems=relax_subproblems,
        )

        dw_model.fit(dw_problem, record)
        dw_model.solve(record)

        master_time, subp_time = dw_model.get_stats("runtime")
        master_itercount, subp_itercount = dw_model.get_stats("itercount")
        dw_rmpgap = dw_model.rmpgap
        dw_improve = dw_model.incre_improve

        timer_dw = (datetime.now() - timer_dw).total_seconds()

        dw_objval, _ = dw_model.get_solution(record)
        dw_itercount = dw_model.dw_iter

        # ----- Reoptimize DW to recover integer solution
        dw_model.reoptimize_with_binary_weights()
        dw_mip_objval, dw_solution_mip = dw_model.get_solution(record)
        master_mip_time = dw_model.master_problem.model.runtime

        #  Verify subproblems produce integer solutions
        dw_solution_mip = dw_solution_mip.reset_index(names="name")
        non_bin_variables = get_non_binary_from_df(
            df=dw_solution_mip,
            target_varnames=["status", "start", "shut"],
        )
        dw_is_int = len(non_bin_variables) == 0
        if not dw_is_int:
            fname = f"dw_nonbin_{model_name}_{k}.csv"
            print(f"DW-PowNet: Saving {fname}...")
            non_bin_variables.to_csv(os.path.join(output_dir, fname), index=False)
            raise ValueError("DW-PowNet: Subproblems do not produce integer solutions.")

        # ----- Solve as MIP with Gurobi
        # Set the MIPGap competitively to the rounding objective value
        # Assume k represents the same instance
        true_objval = true_objvals.loc[k, "mip_objval"]
        set_mipgap = calculate_set_mipgap(dw_mip_objval, true_objval)
        # Compare to Gurobi getting less than 50% of the optimal solution
        if set_mipgap > 1:
            set_mipgap = 0.50

        timer_mip = datetime.now()

        mip_model = gp.read(path_mps)
        mip_model.optimize()
        mip_objval = mip_model.objval
        mip_gurobi_time = mip_model.runtime

        timer_mip = (datetime.now() - timer_mip).total_seconds()

        # ----- Solve as LP with Gurobi
        timer_lp = datetime.now()

        lp_model = mip_model.relax()
        lp_model.optimize()
        lp_objval = lp_model.objval
        lp_gurobi_time = lp_model.runtime

        timer_lp = (datetime.now() - timer_lp).total_seconds()

        # ----- Saving intermediate results
        with open(csv_name, "a", newline="", encoding="utf-8") as csvfile:
            # creating a csv writer object
            csvwriter = csv.writer(csvfile)
            # writing the data rows
            csvwriter.writerow(
                [
                    model_name,
                    T_simulate,
                    set_rmpgap,
                    set_dwimprove,
                    master_itercount,
                    master_time,
                    master_mip_time,
                    subp_itercount,
                    subp_time,
                    dw_itercount,
                    master_time + subp_time + master_mip_time,  # dw_total_time
                    dw_objval,
                    dw_rmpgap,
                    dw_improve,
                    dw_mip_objval,
                    set_mipgap,
                    mip_gurobi_time,
                    mip_objval,
                    lp_gurobi_time,
                    lp_objval,
                    timer_dw,
                    timer_mip,
                    timer_lp,
                    true_objval,
                ]
            )

    # Save solutions for future reference. Place them in a folder
    print(f"\n\nDW-PowNet: ==== Completed {session_name} ====")
    print(f'{"Total time to complete:":<20} {datetime.now()- timer_script}')


if __name__ == "__main__":
    #### Define parameters ####
    countries = ["laos", "cambodia", "thailand"]
    T_simulate = "24"
    rmpgap = 10  # in percent
    dw_improves = [1.0, 0.5, 0.1]  # in percent

    relax_subproblem = False

    exp_pairs = [
        (model_name, dw_improve)
        for model_name in countries
        for dw_improve in dw_improves
    ]

    for model_name, dw_improve in exp_pairs:
        run_dw_experiment(
            model_name=model_name,
            T_simulate=T_simulate,
            set_rmpgap=rmpgap,
            set_dwimprove=dw_improve,
            relax_subproblems=relax_subproblem,
        )
