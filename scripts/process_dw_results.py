"""
This script processes the Dantzig-Wolfe data and generates a .csv file.
"""

# %% Imports
import re
import os

import pandas as pd
import numpy as np

from pownet.folder_sys import get_temp_dir
from solve_new_rounding_pownet import calculate_set_mipgap


dw_folder = os.path.join(get_temp_dir(), "dw_stats")
true_objval_folder = os.path.join(get_temp_dir(), "true_values")

# %% Extract data from the .csv files
filesets = [file for file in os.listdir(dw_folder) if ("csv" in file)]
dw_stats = pd.DataFrame()
dwgap_pattern = r"\d+_\d+_(\w+)_([0-9].*)_False_dwstats.csv"
for file in filesets:
    df = pd.read_csv(os.path.join(dw_folder, file))
    # Extract information from filename
    model_name = re.match(dwgap_pattern, file).group(1)
    df["model_name"] = model_name
    df["set_rmpgap"] = re.match(dwgap_pattern, file).group(2)

    # Join with true objective values
    true_objval_file = os.path.join(true_objval_folder, f"{model_name}_24.csv")
    df2 = pd.read_csv(true_objval_file, header=0, usecols=["mip_objval"])
    df2.columns = ["true_objval"]
    df = pd.concat([df, df2], axis=1)
    df["set_mipgap"] = calculate_set_mipgap(df["dw_mip_objval"], df["true_objval"])

    dw_stats = pd.concat([dw_stats, df], axis=0)

# Save memory and declutter the variable space
del df


# %% Process the data
dw_stats["T_simulate"] = 24
dw_stats["set_dwimprove"] = 0  # Disabled this termination criterion
dw_stats["dw_total_time"] = dw_stats["dw_time"] + dw_stats["dw_mip_time"]

# Drop columns
dw_stats = dw_stats.drop(["dw_mip_time", "dw_time", "is_int"], axis=1)

# Columns that we have no data
dw_stats["dw_rmpgap"] = np.nan
dw_stats["dw_improve"] = np.nan

# Void these columns because we did not set the criteria when solving them
dw_stats[["mip_gurobi_time", "mip_objval", "lp_gurobi_time", "lp_objval"]] = np.nan


# We order the new columns to match with the newer experiments.
ordered_columns = [
    "model_name",
    "T_simulate",
    "set_rmpgap",
    "set_dwimprove",
    "master_itercount",
    "master_time",
    "master_mip_time",
    "subp_itercount",
    "subp_time",
    "dw_itercount",
    "dw_total_time",
    "dw_objval",
    "dw_rmpgap",
    "dw_improve",
    "dw_mip_objval",
    "set_mipgap",
    "mip_gurobi_time",
    "mip_objval",
    "lp_gurobi_time",
    "lp_objval",
    "wall_clock_dw",
    "wall_clock_mip_gurobi",
    "wall_clock_lp_gurobi",
    "true_objval",
]
dw_stats = dw_stats[ordered_columns]

# %% Save to a .csv file. We can append this file to results from other experiments.
output_file = os.path.join(get_temp_dir(), "dw_stats_wo_incre_improve.csv")
dw_stats.to_csv(output_file, index=False)
