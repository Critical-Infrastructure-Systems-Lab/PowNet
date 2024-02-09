"""
Run experments with Dantzig-Wolfe decomposition for the PowNet model
The script will collect statistics for each day and save them in a csv file
"""

import csv
from datetime import datetime
import os

import gurobipy as gp

from pownet.folder_sys import get_temp_dir, get_output_dir, count_mps_files
from pypolp.dw.dw import DantzigWolfe, DWRecord
from pypolp.parser import parse_mps_with_orders, parse_mps, get_dataframe_orders
from pypolp.functions import check_is_binary_from_df


#### Define parameters ####
MODEL_NAME = "thailand"
T = "72"
RECOVER_INT_FROM_DW = True
DWOPTGAP = 10  # 0.0001
RELAX_SUBPROBLEMS = False

###########################

# Start time
start_time_script = datetime.now()
CTIME = start_time_script.strftime("%Y%m%d_%H%M")

print(f"\nDW-PowNet: ==== Begin collecting statistics for {MODEL_NAME} ====")
print(f"Relax subproblems: {RELAX_SUBPROBLEMS}")

# Define the session name and create a folder to save the outputs
session_name = f"{CTIME}_{MODEL_NAME}_{T}_{DWOPTGAP}_{RELAX_SUBPROBLEMS}"
session_name = os.path.join(get_temp_dir(), session_name)
if not os.path.exists(session_name):
    os.makedirs(session_name)

# Need to extract row/column orders to parse the DW structure
instance_folder = os.path.join(get_output_dir(), f"{MODEL_NAME}_{T}_instances")
path_dec = os.path.join(instance_folder, f"{MODEL_NAME}.dec")
path_mps = os.path.join(instance_folder, f"{MODEL_NAME}_0.mps")
(_, A_df, _, _, col_df) = parse_mps(path_mps)
row_order, col_order = get_dataframe_orders(path_dec, A_df, col_df)
del A_df
del col_df

# Collect statistics to compare computational performance
FIELDS = [
    "master_itercount",
    "master_time",
    "master_mip_time",  # Time to optimize the last interation of master as integer
    "subp_itercount",
    "subp_time",
    "dw_itercount",
    "dw_time",
    "dw_mip_time",
    "dw_objval",
    "dw_mip_objval",
    "mip_gurobi_time",
    "mip_objval",
    "lp_gurobi_time",
    "lp_objval",
    "is_int",  # Check if the lp solution is integer
    # Wall clock is the total time to build, solve, extract solution
    "wall_clock_dw",
    "wall_clock_mip_gurobi",
    "wall_clock_lp_gurobi",
]

# Create a csv file with only headers. We will append to this csv later.
csv_name = os.path.join(get_temp_dir(), f"{session_name}_dwstats.csv")
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
    path_mps = os.path.join(instance_folder, f"{MODEL_NAME}_{k}.mps")

    # ----- Solve with Dantzig-Wolfe
    wall_clock_dw = datetime.now()
    dw_problem = parse_mps_with_orders(path_mps, row_order, col_order)
    record = DWRecord()
    record.fit(dw_problem)

    dw_instance = DantzigWolfe(dw_optgap=DWOPTGAP, relax_subproblems=RELAX_SUBPROBLEMS)

    dw_instance.fit(dw_problem, record)
    dw_instance.solve(record)

    master_time, subp_time = dw_instance.get_stats("runtime")
    master_itercount, subp_itercount = dw_instance.get_stats("itercount")

    dw_objval, dw_solution = dw_instance.get_solution(record)
    dw_itercount = dw_instance.dw_iter

    wall_clock_dw = (datetime.now() - wall_clock_dw).total_seconds()
    dw_time = master_time + subp_time

    # ----- Solve with Dantzig-Wolfe but recover integer solution
    if RECOVER_INT_FROM_DW:
        dw_mip_objval, dw_solution_mip = dw_instance.get_solution(
            record, recover_integer=True
        )
        master_mip_time = dw_instance.master_problem.model.runtime
        dw_mip_time = dw_time + master_mip_time

        # Check if the solution is integer
        dw_solution_mip = dw_solution_mip.reset_index(names="name")
        dw_is_int, dw_non_binary_vars = check_is_binary_from_df(
            df=dw_solution_mip,
            target_varnames=["status", "start", "shut"],
            return_non_binary=False,
        )

        # Verify subproblems produce integer solutions
        if not dw_is_int:
            fname = f"dw_nonbin_{MODEL_NAME}_{k}.csv"
            print(f"DW-PowNet: Saving {fname}...")
            dw_non_binary_vars.to_csv(os.path.join(session_name, fname), index=False)
            raise ValueError

    else:
        dw_mip_objval = None
        dw_solution_mip = None
        dw_mip_time = None

    # ----- Saving intermediate results
    with open(csv_name, "a", newline="", encoding="utf-8") as csvfile:
        # creating a csv writer object
        csvwriter = csv.writer(csvfile)
        # writing the data rows
        csvwriter.writerow(
            [
                master_itercount,
                master_time,
                master_mip_time,
                subp_itercount,
                subp_time,
                dw_itercount,
                dw_time,
                dw_mip_time,
                dw_objval,
                dw_mip_objval,
                wall_clock_dw,
            ]
        )

# Save solutions for future reference. Place them in a folder
print(
    f"\n\nDW-PowNet: ==== Completed collecting compute statistics for {MODEL_NAME} ===="
)
print(f"Results for {session_name}")
print(f'{"Total time to complete:":<20} {datetime.now()- start_time_script}')
