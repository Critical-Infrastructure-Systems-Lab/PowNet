"""
This script processes the Dantzig-Wolfe data and generates a .csv file.
"""

# %% Imports
import re
import os

import numpy as np
import pandas as pd

from pownet.folder_sys import get_temp_dir
from functions import calc_percent_change


dw_folder = os.path.join(get_temp_dir(), "dw_stats")

# %% Extract data from the .csv files
filesets = [
    file
    for file in os.listdir(dw_folder)
    if ("csv" in file)
    and not ("dw_experiment_outputs" in file)
    and not ("dw_stats.csv" in file)
    and not ("100re" in file)
]

# Load outputs from older dw experiments.
# These outputs are missing: dw_rmpgap and dw_improve
file = "dw_stats.csv"
dw_stats = pd.read_csv(os.path.join(dw_folder, file))

# Load newer dw stats
for file in filesets:
    df = pd.read_csv(os.path.join(dw_folder, file))
    dw_stats = pd.concat([dw_stats, df], axis=0)

# Recalculate columns for the newer stats: 'dw_gap', 'log10_dw_total_time'
dw_stats["dw_gap"] = calc_percent_change(
    dw_stats["true_objval"], dw_stats["dw_mip_objval"]
)
dw_stats["log10_dw_total_time"] = np.log10(dw_stats["dw_total_time"])

# %% Save to a .csv file. We can append this file to results from other experiments.
output_file = os.path.join(get_temp_dir(), "dw_stats", "dw_experiment_outputs.csv")
dw_stats.to_csv(output_file, index=False)

# %%
