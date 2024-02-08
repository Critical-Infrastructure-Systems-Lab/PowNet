"""

Prepare plots for Paper 1

"""

# %%
import os

from matplotlib.colors import LinearSegmentedColormap
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from pownet.folder_sys import get_temp_dir, get_output_dir
from pownet.core.input import SystemInput
from pownet.core.output import OutputProcessor, Visualizer

from functions import (
    read_dw_stats,
    get_total_daily_from_output,
)

title_map = {
    "model_name = laos": "Country: Laos",
    "model_name = cambodia": "Country: Cambodia",
    "model_name = thailand": "Country: Thailand",
}
feature_map = {
    "dwmip_mip_gap": "DW-MIP Gap (%)",
    "mip_objval": "MIP Obj.val ($)",
    "dw_mip_objval": "DW-MIP Obj.val ($)",
    "dw_mip_time": "DW-MIP opt.time (s)",
    "mip_gurobi_time": "Gurobi opt.time (s)",
    "excess_renewable": "(Total renewables - Total load) in MW",
    "total_on": "Online hours of thermal units",
    "dw_stop": "% Difference: primal/dual objective values",
}

model_names = ["laos", "cambodia", "thailand"]

# We will save figures into temp/figures_paper01
figure_folder = os.path.join(get_temp_dir(), "figures_paper01")
if not os.path.exists(figure_folder):
    os.makedirs(figure_folder)


# %% Plot the structure of the A matrix for three countries
model_names = ["laos", "cambodia", "thailand"]
fig, axes = plt.subplots(ncols=3)
path_mps = os.path.join(
    get_output_dir(), f"{MODEL_NAME}_instances", f"{MODEL_NAME}_0.mps"
)
path_dec = os.path.join(
    get_output_dir(), f"{MODEL_NAME}_instances", f"{MODEL_NAME}.dec"
)

dw_problem = parse_mps_dec(path_mps, path_dec)

(c_df, A_df, b_df, ineq_df, col_df) = dw_problem.get_dataframes()

for model_name, ax in zip(model_names, axes.flatten()):
    ax.spy(A_df, markersize=1)
    ax.set_xlabel("Variable ID")
    ax.set_ylabel("Constraint ID")
plt.tight_layout()
fig.savefig(os.path.join(figure_folder, "structures.png"), dpi=350)


# %% Read the DW results
DWSTOP = 0.0001
dw_stats = read_dw_stats()
dw_stats = dw_stats[dw_stats["relaxed_subp"] == False]

dw_stats_dwstop = dw_stats[dw_stats["dw_stop"] == DWSTOP].copy()
for country in countries:
    dw_stats_dwstop.loc[dw_stats_dwstop["model_name"] == country, "total_on"] = (
        get_total_daily_from_output(
            variables=["status"],
            model_name=country,
        ).values
    )

dw_stats_dwstop = dw_stats_dwstop.reset_index(drop=True)

# %% Scatter plot: DW-MIP Gap vs. MIP Obj.val
g = sns.relplot(
    data=dw_stats_dwstop,
    x="mip_objval",
    y="dwmip_mip_gap",
    col="model_name",
    facet_kws={"sharey": False, "sharex": False},
)
g.set_axis_labels("MIP Obj.val ($)", "DW-MIP Gap (%)")
for ax in g.axes.flatten():
    ax.set_title(title_map[ax.get_title()])

g.figure.savefig(os.path.join(figure_folder, "scatter_mip_objval_gap.png"), dpi=350)

# %% Scatter plot: DW-MIP Gap vs. Excess renewables
g = sns.relplot(
    data=dw_stats_dwstop,
    x="excess_renewable",
    y="dwmip_mip_gap",
    col="model_name",
    facet_kws={"sharey": False, "sharex": False},
)
g.set_axis_labels("(Total renewables - Total load) in MW", "DW-MIP Gap (%)")
for ax in g.axes.flatten():
    ax.set_title(title_map[ax.get_title()])

g.figure.savefig(os.path.join(figure_folder, "scatter_excess_renew_gap.png"), dpi=350)

# %% Scatter plot: DW-MIP Gap vs. online hours
g = sns.relplot(
    data=dw_stats_dwstop,
    x="total_on",
    y="dwmip_mip_gap",
    col="model_name",
    facet_kws={"sharey": False, "sharex": False},
)
g.set_axis_labels("Online hours of thermal units", "DW-MIP Gap (%)")
for ax in g.axes.flatten():
    ax.set_title(title_map[ax.get_title()])

g.figure.savefig(os.path.join(figure_folder, "scatter_thermal_hours_gap.png"), dpi=350)

# %% Scatter plot: Opt.time vs. MIP Obj.val
g = sns.relplot(
    data=dw_stats_dwstop,
    x="mip_objval",
    y="dw_mip_time",
    col="model_name",
    facet_kws={"sharey": False, "sharex": False},
)
g.set_axis_labels("MIP Obj.val ($)", "DW-MIP opt.time (s)")
for ax in g.axes.flatten():
    ax.set_title(title_map[ax.get_title()])

g.figure.savefig(os.path.join(figure_folder, "scatter_mip_objval_time.png"), dpi=350)

# %% Scatter plot: Opt.time vs. Excess renewables
g = sns.relplot(
    data=dw_stats_dwstop,
    x="excess_renewable",
    y="dw_mip_time",
    col="model_name",
    facet_kws={"sharey": False, "sharex": False},
)
g.set_axis_labels("(Total renewables - Total load) in MW", "DW-MIP opt.time (s)")
for ax in g.axes.flatten():
    ax.set_title(title_map[ax.get_title()])

g.figure.savefig(os.path.join(figure_folder, "scatter_excess_renew_time.png"), dpi=350)


# %% Scatter plot: Opt.time vs. online hours
g = sns.relplot(
    data=dw_stats_dwstop,
    x="total_on",
    y="dw_mip_time",
    col="model_name",
    facet_kws={"sharey": False, "sharex": False},
)
g.set_axis_labels("Online hours of thermal units", "DW-MIP opt.time (s)")
for ax in g.axes.flatten():
    ax.set_title(title_map[ax.get_title()])

g.figure.savefig(os.path.join(figure_folder, "scatter_thermal_hours_time.png"), dpi=350)

# %% Boxplots: DW-MIP Gap vs. Exit condition
g = sns.catplot(
    data=dw_stats,
    x="dw_stop",
    y="dwmip_mip_gap",
    col="model_name",
    kind="box",
    margin_titles=True,
    sharex=True,
    sharey=False,
)
g.set_axis_labels(feature_map["dw_stop"], feature_map["dwmip_mip_gap"])

# %% Boxplots: Opt.time vs. Exit condition
g = sns.catplot(
    data=dw_stats,
    x="dw_stop",
    y="dw_mip_time",
    col="model_name",
    kind="box",
    margin_titles=True,
    sharex=True,
    sharey=False,
    log_scale=True,
)

# %%
