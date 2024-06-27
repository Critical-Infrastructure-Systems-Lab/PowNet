"""
This script runs solve MIP with Gurobi with given MIPGaps from the Dantzig-Wolfe experiment.
"""

# %% Imports
import csv
import datetime
import os

import gurobipy as gp
import pandas as pd

from pownet.folder_sys import get_temp_dir, get_output_dir


MODEL_NAME = "laos"

gp.setParam("OutputFlag", 0)

# %%

df = pd.read_csv(
    os.path.join(get_temp_dir(), f"{MODEL_NAME}_dw_stats.csv"),
    usecols=["model_name", "T_simulate", "set_mipgap"],
)
# The dataframe is made up of running instances of 365 days.
assert len(df) % 365 == 0, "The set of instances is not a multiple of 365."
df["day"] = df.index % 365


# %% Prepare a csv file to save the results
# Collect statistics to compare computational performance
FIELDS = [
    "model_name",
    "T_simulate",
    "set_mipgap",
    "mip_gurobi_time",
    "mip_objval",
    "lp_gurobi_time",
    "lp_objval",
    "wall_clock_mip_gurobi",
    "wall_clock_lp_gurobi",
]

# Create a csv file with only headers. We will append to this csv later.
csv_name = os.path.join(get_temp_dir(), f"{MODEL_NAME}_dwstats_mip.csv")
with open(csv_name, "w", newline="", encoding="utf-8") as csvfile:
    # creating a csv writer object
    csvwriter = csv.writer(csvfile)
    # writing the fields
    csvwriter.writerow(FIELDS)


# %% Solve MIP
for row in df.itertuples():
    model_name = row.model_name
    T_simulate = row.T_simulate
    k = row.day
    set_mipgap = row.set_mipgap

    # Identify the mps path
    mps_path = os.path.join(
        get_output_dir(),
        f"{MODEL_NAME}_24_instances",
        f"{MODEL_NAME}_{k}.mps",
    )

    # Solve the MIP
    timer_mip = datetime.datetime.now()
    mip_model = gp.read(mps_path)
    # DON'T FORGET TO SET THE MIPGAP
    mip_model.setParam("MIPGap", set_mipgap)
    mip_model.optimize()

    mip_objval = mip_model.objval
    mip_gurobi_time = mip_model.runtime
    timer_mip = (datetime.datetime.now() - timer_mip).total_seconds()

    # ----- Solve as LP with Gurobi
    timer_lp = datetime.datetime.now()

    lp_model = mip_model.relax()
    lp_model.optimize()
    lp_objval = lp_model.objval
    lp_gurobi_time = lp_model.runtime

    timer_lp = (datetime.datetime.now() - timer_lp).total_seconds()

    with open(csv_name, "a", newline="", encoding="utf-8") as csvfile:
        # creating a csv writer object
        csvwriter = csv.writer(csvfile)
        # writing the data rows
        csvwriter.writerow(
            [
                model_name,
                T_simulate,
                set_mipgap,
                mip_gurobi_time,
                mip_objval,
                lp_gurobi_time,
                lp_objval,
                timer_mip,
                timer_lp,
            ]
        )
