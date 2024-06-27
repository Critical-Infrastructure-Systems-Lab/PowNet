# Run experiments with Gurobi across
# values of simulation horizon and timelimits
import csv
from datetime import datetime
import os

import gurobipy as gp
import pandas as pd

from pypolp.functions import count_mps_files

# Not interested in getting Gurobi Outputs
gp.setParam("OutputFlag", False)


def run_experiment(
    model_name: str,
    T_simulate: int,
) -> None:
    # Define variables for naming the session
    ctime = datetime.now().strftime("%Y%m%d_%H%M")
    session_name = f"{ctime}_LPgurobi_{model_name}_{T_simulate}"

    # We will store the statistics of all sessions
    # in a folder called 'gurobi_stats'
    gurobi_folder = os.path.join("..", "temp", "lp_values")

    if not os.path.exists(gurobi_folder):
        os.mkdir(os.path.join(gurobi_folder))

    print(f"\n\nStarting session {session_name}...")

    # Start the timer
    start_time = datetime.now()

    # Fields are headers in of our statistics csv file
    FIELDS = [
        "model_name",
        "T_simulate",
        "lp_objval",
        "lp_opt_time",
        "wall_clock_lp",
    ]

    csv_name = os.path.join(gurobi_folder, f"{session_name}.csv")
    with open(csv_name, "w", newline="", encoding="utf-8") as csvfile:
        # creating a csv writer object
        csvwriter = csv.writer(csvfile)
        # writing the fields
        csvwriter.writerow(FIELDS)

    # Iterate over all instances
    instance_folder = os.path.join("..", "temp", f"{model_name}_{T_simulate}_instances")

    # Count the number of files ending with .mps
    # Days are labeled from k = 0 to k = 364 (max)
    num_instances = count_mps_files(instance_folder)
    for k in range(num_instances):
        # ----- Solve with Gurobi
        wall_clock_lp = datetime.now()

        path_mps = os.path.join(instance_folder, f"{model_name}_{k}.mps")
        lp_model = gp.read(path_mps)
        lp_model.setParam("outputflag", 0)

        # Relax the model
        lp_model = lp_model.relax()
        lp_model.optimize()

        lp_opt_time = lp_model.runtime
        wall_clock_lp = (datetime.now() - wall_clock_lp).total_seconds()

        # ----- Saving intermediate results
        with open(csv_name, "a", newline="", encoding="utf-8") as csvfile:
            # creating a csv writer object
            csvwriter = csv.writer(csvfile)
            csvwriter.writerow(
                [
                    model_name,
                    T_simulate,
                    lp_model.objval,
                    lp_opt_time,
                    wall_clock_lp,
                ]
            )

    print(f"\n\nCompleted {session_name}...")
    print(f"Total time taken = {datetime.now() - start_time}")


if __name__ == "__main__":

    model_name = "laos_100re"

    run_experiment(
        model_name,
        T_simulate=24,
    )

    print(f"\n\nCompleted {model_name}...")
