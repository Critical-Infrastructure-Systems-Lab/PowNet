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

# Create combinations of model_name and T_simulate
T_simulates = [24, 48, 72]
model_names = ["laos", "cambodia", "thailand"]
T_model_pairs = [(T, model) for T in T_simulates for model in model_names]

sns.set_theme(font_scale=2.5)
for T_simulate, model_name in T_model_pairs:
    # Calculate the number of feasible solutions

    subset_with_T_model = gurobi_stats[
        (gurobi_stats["T_simulate"] == T_simulate)
        & (gurobi_stats["model_name"] == model_name)
    ]
    g = sns.catplot(
        data=subset_with_T_model,
        y="mip_opt_gap",
        col="gp_timelimit",
        col_wrap=5,
        kind="box",
        # log_scale=True,
        sharey=False,
        margin_titles=True,
    )
    g.figure.suptitle(
        f"OPTGap: ({model_name}, {T_simulate})", y=1.03, fontsize="x-large"
    )

    plt.show()
