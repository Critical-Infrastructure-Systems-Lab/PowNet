""" This script visualizes results from then new Dantzig-Wolfe experiments.
We want to show the followings: Solution quality and optimization time.
Dantzig-Wolfe always generate a feasible solution in this case.
"""

# %% Imports and naming conventions
import os
import re

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
    "dw_gap": "Optimality gap (%)",
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
folder_name = os.path.join(get_temp_dir(), "dw_stats")
stats = pd.read_csv(os.path.join(folder_name, "dw_experiment_outputs.csv"))

stats["dw_gen_col_time"] = stats["master_time"] + stats["subp_time"]

# Capitalize country names
stats["model_name"] = stats["model_name"].str.capitalize()

# %% Plot the sample space of solution quality
print("\nSample space of DW OPTGap")
g = sns.FacetGrid(stats, row="set_rmpgap", col="set_dwimprove", margin_titles=True)
g.map(
    sns.barplot,
    "model_name",
    "dw_gap",
    order=["Laos", "Cambodia", "Thailand"],
    linewidth=2.5,
)


# %% Compare Opt.time
print("\nSample space of DW opt.time")
g = sns.FacetGrid(stats, row="set_rmpgap", col="set_dwimprove", margin_titles=True)
g.map(
    sns.boxplot,
    "model_name",
    "log10_dw_total_time",
    order=["Laos", "Cambodia", "Thailand"],
)


# %% Print stats
stats_grouped = stats.groupby(["model_name", "set_rmpgap", "set_dwimprove"]).mean()

print("Mean dw_total_time")
print(stats_grouped["dw_total_time"])

print("Mean DW GAP(%)")
print(stats_grouped["dw_gap"])


# %% Plot time series of the best case of DW against MIP Gurobi
best_dw_thailand = stats[
    (stats["model_name"] == "Thailand")
    & (stats["set_rmpgap"] == 50)
    & (stats["set_dwimprove"] == 50)
]
best_dw_thailand = best_dw_thailand.reset_index(drop=True)

# Something weird happen at the 108th day with 100 and 100


def plot_log_time_series(df):
    fig, ax = plt.subplots()
    ax.semilogy(
        df["mip_gurobi_time"],
        label="MIP",
        alpha=1,
        linewidth=2,
    )
    ax.semilogy(
        df["dw_gen_col_time"],
        label="DW: Generating schedules",
        alpha=0.5,
        linewidth=1,
    )
    ax.semilogy(
        df["master_mip_time"],
        label="DW: Selecting schedules",
        alpha=1,
        linewidth=2,
    )
    ax.set_xlabel("Day")
    ax.set_ylabel("Optimization time (s)")
    ax.set_title("Thailand over 24-hr horizon")
    plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", borderaxespad=0.0)
    plt.show()


plot_log_time_series(best_dw_thailand)


# %% Show the effects of parameterization for dw_improve 50% and dw_rmpgap at 50%
sel_rmpgap = 50
param_subset = stats[
    (stats["set_rmpgap"] == sel_rmpgap) & (stats["set_dwimprove"] >= 50)
]
g = sns.FacetGrid(
    param_subset, row="set_rmpgap", col="set_dwimprove", margin_titles=True
)
g.map(
    sns.boxplot,
    "model_name",
    "dw_gap",
    order=["Laos", "Cambodia", "Thailand"],
    linewidth=2.5,
)
re_pat = r"""\=\s(\d+.\d+)"""
for ax in g.axes.flatten():
    # Get the numerical value from the title
    dw_improve = ax.get_title()
    dw_improve = re.findall(re_pat, dw_improve)[0]
    ax.set_title(f"Increm. improve: {dw_improve} %")

    plt.setp(ax.texts, text=f"RMPGap {sel_rmpgap} (%)")

    ax.set_xlabel("")
    ax.set_ylabel("Optimality gap (%)")


# %% Find the solution quality based on set_rmpgap = 10 and set_dwimprove = 10 for all countries
# Need to update this plot once we have gotten additional data points
# param_subset = param_subset[param_subset["set_dwimprove"] == 10]
cols2group = ["model_name", "T_simulate", "set_rmpgap", "set_dwimprove"]
param_subset.groupby(cols2group).mean()["dw_gap"]
print(param_subset.groupby(cols2group).mean()["dw_gap"])


# %% Plot the speed-up
param_subset.loc[:, "xSpeedup"] = (
    param_subset["mip_gurobi_time"] / param_subset["dw_total_time"]
)
g = sns.FacetGrid(
    param_subset,
    row="set_rmpgap",
    col="set_dwimprove",
    margin_titles=True,
)
g.map(
    sns.barplot,
    "model_name",
    "xSpeedup",
    linewidth=2.5,
    label="xSpeedup",
    order=["Laos", "Cambodia", "Thailand"],
)
for ax in g.axes.flatten():
    ax.axhline(1, ls="--", color="k", label=["1.0x"])
    ax.set_xlabel("")
    ax.set_ylabel("x(Optimization time)")

    # Get the numerical value from the title
    dw_improve = ax.get_title()
    dw_improve = re.findall(re_pat, dw_improve)[0]
    ax.set_title(f"Increm. improve: {dw_improve} %")

    plt.setp(ax.texts, text=f"RMPGap {sel_rmpgap} (%)")


# %% Plot the time comparison for laos
laos100 = pd.read_csv(
    os.path.join(
        get_temp_dir(), "dw_stats", "laos_100re_24_0.0001_0.0001_False_dwstats.csv"
    )
)
laos100["dw_gen_col_time"] = laos100["master_time"] + laos100["subp_time"]

# Indicate if the master_time is quicker than mip_gurobi_time
laos100["is_master_quicker"] = laos100["mip_gurobi_time"] > laos100["master_time"]


fig, ax = plt.subplots()
ax.semilogy(
    laos100["mip_gurobi_time"],
    label="MIP",
    alpha=1,
    linewidth=2,
)
ax.semilogy(
    laos100["dw_gen_col_time"],
    label="DW: Generating schedules",
    alpha=0.5,
    linewidth=0.5,
)
ax.semilogy(
    laos100["master_mip_time"],
    label="DW: Selecting schedules",
    alpha=1,
    linewidth=2,
)

ax.set_xlabel("Day")
ax.set_ylabel("Optimization time (s)")
ax.set_title("Laos (without spinning reserve)\n over 24-hr horizon")

# Highlight that area when the master_time is quicker than gurobi_mip_time
for idx, row in laos100.iterrows():
    if row["is_master_quicker"]:
        ax.axvspan(
            idx - 0.5,
            idx + 0.5,
            alpha=0.5,
            color="yellow",
            label="",
        )
plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", borderaxespad=0.0)
plt.show()


# %%
