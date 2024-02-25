""" This script visualizes results from then new Dantzig-Wolfe experiments.
We want to show the followings: Solution quality and optimization time.
Dantzig-Wolfe always generate a feasible solution in this case.
"""

# %% Imports and naming conventions
import os

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import seaborn as sns

from pownet.folder_sys import get_temp_dir, get_output_dir

from functions import (
    read_dw_stats,
    calc_percent_change,
    get_total_daily_load,
    get_total_daily_renewable,
    get_total_daily_from_output,
)


naming_map = {
    "dw_mip_gap": "DW-MIP Gap (%)",
    "mip_objval": "MIP Obj.val ($)",
    "dw_mip_objval": "DW-MIP Obj.val ($)",
    "dw_mip_time": "DW-MIP opt.time (s)",
    "mip_gurobi_time": "Gurobi opt.time (s)",
    "excess_renewable": "(Total Renewables - Total load) in MW",
    "total_on": "Online hours of thermal units",
}


def plot_scatter(df, model_name: str, xname: str, yname: str):
    fig, ax = plt.subplots(dpi=350)
    ax.scatter(x=df[xname], y=df[yname])
    ax.set_xlabel(naming_map[xname])
    ax.set_ylabel(naming_map[yname])

    title_name = f"Country: {model_name.title()}"
    ax.set_title(title_name)
    plt.show()


# %% Load the data
# Fast DW only contains ones with rmpgap = 10. We relax the incremental improvement to get faster solution.
folder_name = os.path.join(get_temp_dir(), "new_dw_stats")
filesets = os.listdir(folder_name)

# We will compare the quicker termination criteria with the slower one
slow_dw_stats = pd.read_csv(
    os.path.join(get_temp_dir(), "dw_stats_wo_incre_improve.csv")
)
slow_dw_stats["dw_gap"] = calc_percent_change(
    slow_dw_stats["dw_mip_objval"], slow_dw_stats["true_objval"]
)

slowest_dw_stats = slow_dw_stats[slow_dw_stats["set_rmpgap"] == 0.0001].reset_index(
    drop=True
)


fast_dw_stats = pd.DataFrame()
for file in filesets:
    df = pd.read_csv(os.path.join(folder_name, file))
    fast_dw_stats = pd.concat([fast_dw_stats, df], axis=0)
del df
fast_dw_stats["dw_gap"] = calc_percent_change(
    fast_dw_stats["dw_mip_objval"], fast_dw_stats["true_objval"]
)

stats = pd.concat([fast_dw_stats, slow_dw_stats], axis=0)

# set_rmpgap is in fraction and not in percentage
stats["dw_gap"] = calc_percent_change(stats["dw_mip_objval"], stats["true_objval"])
stats["log10_dw_total_time"] = np.log10(stats["dw_total_time"])


# %% Plot the solution quality as boxplots
g = sns.FacetGrid(stats, row="set_rmpgap", col="set_dwimprove", margin_titles=True)
g.map(
    sns.barplot,
    "model_name",
    "dw_gap",
    linewidth=2.5,
)

# %% Compare Opt.time
g = sns.FacetGrid(stats, row="set_rmpgap", col="set_dwimprove", margin_titles=True)
g.map(
    sns.boxplot,
    "model_name",
    "log10_dw_total_time",
)

# %% Print stats
stats_grouped = stats.groupby(["model_name", "set_rmpgap", "set_dwimprove"]).mean()

print("Mean dw_total_time")
print(stats_grouped["dw_total_time"])

print("Mean DW GAP(%)")
print(stats_grouped["dw_gap"])


# %% Plot time series of the best case of DW against MIP Gurobi
thailand_true = pd.read_csv(
    os.path.join(get_temp_dir(), "true_values", "thailand_24.csv"), header=0
)

thailand_dw = stats[
    (stats["model_name"] == "thailand")
    & (stats["set_rmpgap"] == 10)
    & (stats["set_dwimprove"] == 10)
]

fig, ax = plt.subplots()
ax.plot(thailand_true["mip_opt_time"], label="MIP", alpha=0.5, linewidth=1)
ax.plot(thailand_dw["master_time"], label="DW Master", alpha=0.5, linewidth=1)
ax.plot(thailand_dw["subp_time"], label="DW Subproblems", alpha=0.5, linewidth=1)
ax.plot(
    thailand_dw["master_mip_time"], label="DW Discretization", alpha=0.5, linewidth=1
)
ax.set_xlabel("Day")
ax.set_ylabel("Opt.time (s)")
ax.set_title("Thailand")
plt.legend()
plt.show()

# %%
fig, ax = plt.subplots()
ax.semilogy(thailand_true["mip_opt_time"], label="MIP", alpha=0.5, linewidth=1)
ax.semilogy(thailand_dw["master_time"], label="DW Master", alpha=0.5, linewidth=1)
ax.semilogy(thailand_dw["subp_time"], label="DW Subproblems", alpha=0.5, linewidth=1)
ax.semilogy(
    thailand_dw["master_mip_time"], label="DW Discretization", alpha=0.5, linewidth=1
)
ax.set_xlabel("Day")
ax.set_ylabel("Log10 Opt.time (s)")
ax.set_title("Thailand")
plt.legend()
plt.show()

# %% Plot the speed-comparison of the fast DW
fast_dw_stats["xSpeedup"] = (
    fast_dw_stats["mip_gurobi_time"] / fast_dw_stats["dw_total_time"]
)
g = sns.FacetGrid(
    fast_dw_stats, row="set_rmpgap", col="set_dwimprove", margin_titles=True
)
g.map(
    sns.barplot,
    "model_name",
    "xSpeedup",
    linewidth=2.5,
    label="xSpeedup",
)
for ax in g.axes.flatten():
    ax.axhline(1, ls="--", color="k", label=["1.0x"])

# %%
thailand_dw["xSpeedup"] = thailand_dw["mip_gurobi_time"] / thailand_dw["dw_total_time"]

fig, ax = plt.subplots()
ax.plot(thailand_dw["xSpeedup"], linewidth=1, label=["Speed-up"])
ax.set_xlabel("Day")
ax.set_ylabel("xSpeedup")
ax.set_title("Thailand | DW speed-up")
ax.axhline(1, ls="--", color="k", label=["1.0x"])
ax.set_ylim(0, 7)

# Bar plot of Gap on the secondary axis
ax2 = ax.twinx()
ax2.bar(
    thailand_dw.index, thailand_dw["dw_gap"], alpha=0.25, color="r", label="DW Gap(%)"
)
ax2.set_ylabel("DW Gap(%)")
ax2.set_ylim(0, 100)

fig.legend()
plt.show()


# %%

sel_country = "thailand"
temp_df = stats[stats["model_name"] == sel_country]

# Drop the columns that are not needed
cols2drop = [
    "mip_gurobi_time",
    "mip_objval",
    "wall_clock_mip_gurobi",
    "lp_gurobi_time",
    "lp_objval",
    "wall_clock_lp_gurobi",
]

temp_df = temp_df.drop(columns=cols2drop)

temp_df.to_csv(os.path.join(get_temp_dir(), f"{sel_country}_dw_stats.csv"), index=False)

# %%
