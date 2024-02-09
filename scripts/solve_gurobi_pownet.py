# Run experiments with Gurobi across
# values of simulation horizon and timelimits
import csv
from datetime import datetime
import os

import gurobipy as gp
import pandas as pd

from pownet.folder_sys import get_temp_dir, get_output_dir


# Not interested in getting Gurobi Outputs
gp.setParam("OutputFlag", False)


def run_experiment(
    model_name: str,
    T_simulate: int,
    gp_timelimit: int,
) -> None:
    # Define variables for naming the session
    ctime = datetime.now().strftime("%Y%m%d_%H%M")
    session_name = f"{ctime}_gurobi_{model_name}_{T_simulate}_{gp_timelimit}"

    # We will store the statistics of all sessions
    # in a folder called 'gurobi_stats'
    gurobi_folder = os.path.join(get_temp_dir(), "gurobi_stats")
    if not os.path.exists(gurobi_folder):
        os.mkdir(os.path.join(gurobi_folder))

    print(f"\n\nStarting session {session_name}...")

    # Start the timer
    start_time = datetime.now()

    # Fields are headers in of our statistics csv file
    FIELDS = [
        "model_name",
        "T_simulate",
        "gp_timelimit",
        "mip_objval",
        "mip_opt_time",
        "mip_opt_gap",  # Note that this is in fraction (|zp| - |zd|) / |zp|
        "wall_clock_mip",
    ]

    csv_name = os.path.join(gurobi_folder, f"{session_name}.csv")
    with open(csv_name, "w", newline="", encoding="utf-8") as csvfile:
        # creating a csv writer object
        csvwriter = csv.writer(csvfile)
        # writing the fields
        csvwriter.writerow(FIELDS)

    # Iterate over all instances
    instance_folder = os.path.join(
        get_output_dir(), f"{model_name}_{T_simulate}_instances"
    )

    # Count the number of files ending with .mps
    # Days are labeled from k = 0 to k = 364 (max)
    num_instances = 0
    for file in os.listdir(instance_folder):
        if file.endswith(".mps"):
            num_instances += 1
    for k in range(num_instances):
        # ----- Solve with Gurobi
        wall_clock_mip = datetime.now()

        path_mps = os.path.join(instance_folder, f"{model_name}_{k}.mps")
        mip_model = gp.read(path_mps)
        mip_model.setParam("outputflag", 0)
        mip_model.setParam("TimeLimit", gp_timelimit)
        mip_model.optimize()

        mip_opt_time = mip_model.runtime
        mip_opt_gap = mip_model.MIPGap
        wall_clock_mip = (datetime.now() - wall_clock_mip).total_seconds()

        # ----- Saving intermediate results
        with open(csv_name, "a", newline="", encoding="utf-8") as csvfile:
            # creating a csv writer object
            csvwriter = csv.writer(csvfile)
            csvwriter.writerow(
                [
                    model_name,
                    T_simulate,
                    gp_timelimit,
                    mip_model.objval,
                    mip_opt_time,
                    mip_opt_gap,  # This is in fraction (|zp| - |zd|) / (1e-10 + |zp|)
                    wall_clock_mip,
                ]
            )

    print(f"\n\nCompleted {session_name}...")
    print(f"Total time taken = {datetime.now() - start_time}")


if __name__ == "__main__":
    model_name = "thailand"
    T_simulates = [24, 48, 72]  # in hours
    # gp_timelimits = [5, 10, 20, 40, 60]  # in seconds
    gp_timelimits = [1, 2, 3, 4, 6, 7, 8, 9, 15, 25, 30, 50, 60]

    pairs = [(x, y) for x in T_simulates for y in gp_timelimits]

    for T_simulate, gp_timelimit in pairs:
        run_experiment(
            model_name,
            T_simulate=T_simulate,
            gp_timelimit=gp_timelimit,
        )
