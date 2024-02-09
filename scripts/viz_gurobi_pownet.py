import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from pownet.folder_sys import get_temp_dir


# Assume that all the PowNet Dantzig-Wolfe stats are in dw_stats folder.
folder_name = os.path.join(get_temp_dir(), "gurobi_stats")
filesets = [file for file in os.listdir(folder_name) if ("csv" in file)]

gurobi_stats = pd.DataFrame()
for file in filesets:
    temp_df = pd.read_csv(os.path.join(folder_name, file), header=0)
    gurobi_stats = pd.concat([gurobi_stats, temp_df], axis=0)
gurobi_stats = gurobi_stats.reset_index(drop=False, names="step")

# Convert from fraction to percentage
gurobi_stats["mip_opt_gap"] = gurobi_stats["mip_opt_gap"] * 100
gurobi_stats.loc[gurobi_stats["mip_opt_gap"] > 100, "mip_opt_gap"] = 100

# Create lineplots for each T_simulate
T_simulate = 24
subset_with_T = gurobi_stats[gurobi_stats["T_simulate"] == T_simulate]

g = sns.catplot(
    data=subset_with_T,
    y="mip_opt_gap",
    col="gp_timelimit",
    col_wrap=3,
    kind="box",
    # log_scale=True,
    sharey=False,
    margin_titles=True,
)

# Create lineplots for each gp_timelimit
g_facet = sns.FacetGrid(subset_with_T, col="T_simulate", margin_titles=True)
g_facet.map(sns.lineplot, "step", "mip_opt_gap")
