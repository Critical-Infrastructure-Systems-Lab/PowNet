# %%
import os
import re

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import seaborn as sns

from pownet.folder_sys import get_temp_dir
from functions import calc_percent_change

plt.rc("font", size=14)
plt.rc("axes", titlesize=12)

# --- Load the data
# Specify the folder where the figures are stored
figure_folder = os.path.join(get_temp_dir(), "figures_rounding")
if not os.path.exists(figure_folder):
    os.makedirs(figure_folder)

# Input folder
input_folder = "new_rounding_stats"

# Define naming conventions
name_map = {
    "fast": "Fast rounding",
    "slow": "Slow rounding",
    "round_gap": "Optimality gap (%)",
    "round_threshold": "Rounding threshold",
    "opt_xspeed": "xSpeed-up (Opt.time)",
    "wall_clock_xspeed": "xSpeed-up (Wall clock)",
    "round_strategy": "Rounding strategy",
}

# %% Read statistics from files and compile into a single dataframe
files = os.listdir(os.path.join(get_temp_dir(), input_folder))

# Read the files and compile into a single dataframe
compiled_df = pd.DataFrame()
capture_pat = r".*_rounding_(\w+)_(\d+)_(\w+)_(\w+)_(.+).csv"
for file in files:
    # The filename contains information about the model and rounding strategy
    match = re.search(capture_pat, file)
    round_strategy = match.group(3)
    round_threshold = match.group(5)

    # Read the file
    subset = pd.read_csv(os.path.join(get_temp_dir(), "new_rounding_stats", file))

    # Add information to the dataframe
    subset["round_strategy"] = round_strategy
    subset["round_threshold"] = float(round_threshold)

    # Process new features based on existing features
    subset["round_gap"] = calc_percent_change(
        subset["rounding_objval"], subset["true_objval"]
    )
    subset["mip_gap"] = calc_percent_change(subset["mip_objval"], subset["true_objval"])
    subset["opt_xspeed"] = subset["mip_opt_time"] / subset["rounding_opt_time"]
    subset["wall_clock_xspeed"] = (
        subset["wall_clock_mip"] / subset["wall_clock_rounding"]
    )
    subset["fraction_runtime"] = (
        subset["rounding_opt_time"] / subset["wall_clock_rounding"]
    )

    # Append the new df to the master_df
    compiled_df = pd.concat([compiled_df, subset], axis=0)

# Order compiled_df by model_name and direction for standardized plotting
# compiled_df['direction'] = pd.Categorical(compiled_df['direction'])
compiled_df = compiled_df.sort_values(
    by=["model_name", "round_strategy", "round_threshold"]
)


# %% INFEASIBILITY
# Calculate fractions of feasible/infeasible solutions
cols2subset = ["model_name", "T_simulate", "round_strategy", "round_threshold"]
infeasibility_df = (
    compiled_df.groupby(cols2subset)["rounding_is_feasible"].mean().to_frame()
)
infeasibility_df["feasible"] = 1 - infeasibility_df["rounding_is_feasible"]
infeasibility_df.columns = ["True", "False"]
infeasibility_df = infeasibility_df.reset_index()

strategies = ["slow", "fast"]
model_T_pairs = [
    (model_name, T_simulate)
    for model_name in [
        "laos",
        "cambodia",
        "thailand",
    ]
    for T_simulate in [24, 48, 72]
]

thresholds = [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]

subset_infeasible = infeasibility_df[
    infeasibility_df["round_threshold"].isin(thresholds)
]


# Save the dataframe
subset_infeasible.to_csv("infeasibility.csv")


# Find the lowest feasibility rate for cambodia, and laos
min_infeasible = subset_infeasible.groupby(["model_name", "round_strategy"])[
    "True"
].min()
max_infeasible = subset_infeasible.groupby(["model_name", "round_strategy"])[
    "True"
].max()


# %% VISUALIZE INFEASIBILITY
# Plot the fraction of infeasibility as a dot for the fast and slow strategies with seaborn
# Subset to rounding thresholds of [0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
xlabels = [f"{t:.2f}" for t in thresholds]

g = sns.FacetGrid(
    subset_infeasible,
    col="T_simulate",
    row="model_name",
    row_order=["laos", "cambodia", "thailand"],
    hue="round_strategy",
)

g.map(
    sns.pointplot,
    "round_threshold",
    "True",
    # alpha=0.45,
    order=thresholds,
    hue_order=strategies,
)

# g.add_legend(title="Rounding strategy")
g.set_axis_labels(name_map["round_threshold"], "Fraction of feasible instances")

# Format the figure
ax_id = 0
for ax in g.axes.flatten():
    country = ax.get_title().split("|")[0].strip()
    country = country.split("=")[1].strip()

    T_simulate = ax.get_title().split("|")[1].strip()
    T_simulate = T_simulate.split("=")[1].strip()

    ax.set_title(f"{country.title()} over {T_simulate}-hour")

    ax.set_xlabel("")
    ax.set_ylabel("")
    # Selectively add xlabel and ylabel
    if ax_id == 3:
        ax.set_ylabel("Fraction of feasible instances")
    if ax_id == 7:
        ax.set_xlabel(name_map["round_threshold"])
    ax_id += 1

    # Rotate xticks to 90 degrees
    xticks = [float(t.get_text()) for t in ax.get_xticklabels()]
    ax.xaxis.set_major_locator(mticker.FixedLocator(ax.get_xticks()))
    ax.set_xticklabels(xlabels, rotation=90)

# Capitalize the legend of the figure
handles, labels = g.axes.flatten()[0].get_legend_handles_labels()
labels = [label.title() for label in labels]
g.figure.legend(
    handles,
    labels,
    title="Rounding strategy",
    loc="outside lower right",
    bbox_to_anchor=(1, -0.1),
    # bbox_transform=g.figure.transFigure,
    ncol=2,
)

# Savefigure
g.figure.savefig(
    os.path.join(figure_folder, "rounding_infeasibility.png"),
    dpi=350,
    bbox_inches="tight",
)


plt.show()

# %% PLOT OPTIMALITY GAP AS LINE PLOT
feasible_df = compiled_df[compiled_df["rounding_is_feasible"]].reset_index()
feasible_df = feasible_df[feasible_df["round_threshold"].isin(thresholds)]

# Subset to only instances when objval_rounding and objval_mip deviates less than 5%
feasible_df["rounding_objval"] = feasible_df["rounding_objval"].round(0)
feasible_df["mip_objval"] = feasible_df["mip_objval"].round(0)
feasible_df["diff_objval"] = feasible_df["rounding_objval"] - feasible_df["mip_objval"]
feasible_df["diff_objval"] = feasible_df["diff_objval"].abs()
feasible_df["diff_objval"] = feasible_df["diff_objval"] / (
    feasible_df["true_objval"] + 1
)
feasible_df["diff_objval"] = feasible_df["diff_objval"] * 100


# %%
g_optgap = sns.FacetGrid(
    feasible_df,
    col="T_simulate",
    row="model_name",
    row_order=["laos", "cambodia", "thailand"],
    hue="round_strategy",
)

g_optgap.map(
    sns.lineplot,
    "round_threshold",
    "round_gap",
    hue_order=strategies,
)


ax_id = 0
for ax in g_optgap.axes.flatten():
    country = ax.get_title().split("|")[0].strip()
    country = country.split("=")[1].strip()

    T_simulate = ax.get_title().split("|")[1].strip()
    T_simulate = T_simulate.split("=")[1].strip()

    ax.set_title(f"{country.title()} over {T_simulate}-hour")
    ax.set_xlabel("")
    ax.set_ylabel("")

    ax.set_ylim(0, 10)

    # Selectively add xlabel and ylabel
    if ax_id == 3:
        ax.set_ylabel(name_map["round_gap"])
    if ax_id == 7:
        ax.set_xlabel(name_map["round_threshold"])
    ax_id += 1

# Capitalize the legend of the figure
handles, labels = g_optgap.axes.flatten()[0].get_legend_handles_labels()
labels = [label.title() for label in labels]
g_optgap.figure.legend(
    handles,
    labels,
    title="Rounding strategy",
    loc="outside lower right",
    bbox_to_anchor=(1, -0.07),
    # bbox_transform=g.figure.transFigure,
    ncol=2,
)

# Save figure
g_optgap.figure.savefig(
    os.path.join(figure_folder, "rounding_optimality_gap.png"),
    dpi=350,
    bbox_inches="tight",
)

plt.show()


# %% LINEPLOT SPEEDUP (OPT.TIME)
# If the optimality gap deviates too much, the speedup is not meaningful
subset_feasible_df = feasible_df[feasible_df["diff_objval"] <= 0.5].copy()
subset_feasible_df["rounding_k"] = subset_feasible_df["rounding_k"].astype(int)

# Print statistics
subset_feasible_df.groupby(["model_name", "T_simulate", "round_strategy"]).agg(
    {"opt_xspeed": ["mean", "std", "min", "max", "count"]}
).round(2)


g_speedup = sns.FacetGrid(
    subset_feasible_df,
    col="T_simulate",
    row="model_name",
    row_order=["laos", "cambodia", "thailand"],
    hue="round_strategy",
)

g_speedup.map(
    sns.lineplot,
    "round_threshold",
    "opt_xspeed",
    hue_order=strategies,
)

ax_id = 0
for ax in g_speedup.axes.flatten():
    country = ax.get_title().split("|")[0].strip()
    country = country.split("=")[1].strip()

    T_simulate = ax.get_title().split("|")[1].strip()
    T_simulate = T_simulate.split("=")[1].strip()

    ax.set_title(f"{country.title()} over {T_simulate}-hour")
    ax.set_xlabel("")
    ax.set_ylabel("")

    ax.set_ylim(0, 12)

    ax.axhline(1, ls="--", color="k", label="1.0x")

    # Selectively add xlabel and ylabel
    if ax_id == 3:
        ax.set_ylabel(name_map["opt_xspeed"])
    if ax_id == 7:
        ax.set_xlabel(name_map["round_threshold"])
    ax_id += 1

# Capitalize the legend of the figure
handles, labels = g_speedup.axes.flatten()[0].get_legend_handles_labels()
labels = [label.title() for label in labels]
g_speedup.figure.legend(
    handles,
    labels,
    title="Rounding strategy",
    loc="outside lower right",
    bbox_to_anchor=(1, -0.07),
    # bbox
    ncol=3,
)

# Save figure
g_speedup.figure.savefig(
    os.path.join(figure_folder, "rounding_speedup_opttime.png"),
    dpi=350,
    bbox_inches="tight",
)

plt.show()


# %% LINEPLOT SPEEDUP (WALL CLOCK)

# Print statistics
subset_feasible_df.groupby(["model_name", "T_simulate", "round_strategy"]).agg(
    {"wall_clock_xspeed": ["mean", "std", "min", "max", "count"]}
).round(2)

g_speedup_wall = sns.FacetGrid(
    subset_feasible_df,
    col="T_simulate",
    row="model_name",
    row_order=["laos", "cambodia", "thailand"],
    hue="round_strategy",
)

g_speedup_wall.map(
    sns.lineplot,
    "round_threshold",
    "wall_clock_xspeed",
    hue_order=strategies,
)

ax_id = 0
for ax in g_speedup_wall.axes.flatten():
    country = ax.get_title().split("|")[0].strip()
    country = country.split("=")[1].strip()

    T_simulate = ax.get_title().split("|")[1].strip()
    T_simulate = T_simulate.split("=")[1].strip()

    ax.set_title(f"{country.title()} over {T_simulate}-hour")
    ax.set_xlabel("")
    ax.set_ylabel("")

    ax.set_ylim(0, 12)

    ax.axhline(1, ls="--", color="k", label="1.0x")

    # Selectively add xlabel and ylabel
    if ax_id == 3:
        ax.set_ylabel(name_map["wall_clock_xspeed"])
    if ax_id == 7:
        ax.set_xlabel(name_map["round_threshold"])
    ax_id += 1

# Capitalize the legend of the figure
handles, labels = g_speedup_wall.axes.flatten()[0].get_legend_handles_labels()
labels = [label.title() for label in labels]
g_speedup_wall.figure.legend(
    handles,
    labels,
    title="Rounding strategy",
    loc="outside lower right",
    bbox_to_anchor=(1, -0.07),
    # bbox
    ncol=3,
)

# Save figure
g_speedup_wall.figure.savefig(
    os.path.join(figure_folder, "rounding_speedup_wallclock.png"),
    dpi=350,
    bbox_inches="tight",
)


# %% Create box plots of the number of rounding iterations, or the rounding_k column

g_rounding_k = sns.catplot(
    subset_feasible_df,
    x="round_threshold",
    y="rounding_k",
    col="T_simulate",
    row="model_name",
    row_order=["laos", "cambodia", "thailand"],
    hue="round_strategy",
    kind="box",
    sharey=False,
    height=4,
    # log_scale=True,
)

ax_id = 0
for ax in g_rounding_k.axes.flatten():
    country = ax.get_title().split("|")[0].strip()
    country = country.split("=")[1].strip()

    T_simulate = ax.get_title().split("|")[1].strip()
    T_simulate = T_simulate.split("=")[1].strip()

    ax.set_title(f"{country.title()} over {T_simulate}-hour", fontsize=15)
    ax.set_xlabel("")
    ax.set_ylabel("")

    # Selectively add xlabel and ylabel
    if ax_id == 3:
        ax.set_ylabel("Number of rounding iterations", fontsize=16)
    if ax_id == 7:
        ax.set_xlabel(name_map["round_threshold"], fontsize=16)
    ax_id += 1

    # Rotate xticks to 90 degrees
    xticks = [float(t.get_text()) for t in ax.get_xticklabels()]
    ax.xaxis.set_major_locator(mticker.FixedLocator(ax.get_xticks()))
    ax.set_xticklabels(xlabels, rotation=90)

# Capitalize the legend of the figure
handles = g_rounding_k._legend_data.values()
labels = g_rounding_k._legend_data.keys()

g_rounding_k._legend.set(visible=False)

labels = [label.title() for label in labels]
g_rounding_k.figure.legend(
    handles,
    labels,
    title="Rounding strategy",
    loc="outside lower right",
    bbox_to_anchor=(0.9, -0.05),
    # bbox_transform=g.figure.transFigure,
    ncol=2,
    fontsize="small",
)

# Save figure
g_rounding_k.figure.savefig(
    os.path.join(figure_folder, "rounding_iterations.png"),
    dpi=350,
    bbox_inches="tight",
)

plt.show()


# %% Compare solution quality between rounding and Gurobi
"""
(objval_gurobi - objval_rounding)/objval_true
"""


# Print summary statistics of diff_objval for country-T_simulate pairs
summary_diff_objval = (
    subset_feasible_df.groupby(["model_name", "T_simulate", "round_threshold"])
    .agg({"diff_objval": ["mean", "std", "min", "max", "count"]})
    .reset_index()
)

# Round to three digits
summary_diff_objval = summary_diff_objval.round(3)


# Plot the quality of the solution
g_rounding_k = sns.catplot(
    subset_feasible_df,
    x="round_threshold",
    y="diff_objval",
    col="T_simulate",
    row="model_name",
    row_order=["laos", "cambodia", "thailand"],
    hue="round_strategy",
    kind="box",
    sharey=False,
    height=4,
)
plt.ylim(-100, 100)

ax_id = 0
for ax in g_rounding_k.axes.flatten():
    country = ax.get_title().split("|")[0].strip()
    country = country.split("=")[1].strip()

    T_simulate = ax.get_title().split("|")[1].strip()
    T_simulate = T_simulate.split("=")[1].strip()

    ax.set_title(f"{country.title()} over {T_simulate}-hour", fontsize=15)
    ax.set_xlabel("")
    ax.set_ylabel("")

    # Selectively add xlabel and ylabel
    if ax_id == 3:
        ax.set_ylabel("Deviation of Objective Values (%)", fontsize=16)
    if ax_id == 7:
        ax.set_xlabel(name_map["round_threshold"], fontsize=16)
    ax_id += 1

    # Rotate xticks to 90 degrees
    xticks = [float(t.get_text()) for t in ax.get_xticklabels()]
    ax.xaxis.set_major_locator(mticker.FixedLocator(ax.get_xticks()))
    ax.set_xticklabels(xlabels, rotation=90)

# Capitalize the legend of the figure
handles = g_rounding_k._legend_data.values()
labels = g_rounding_k._legend_data.keys()

g_rounding_k._legend.set(visible=False)

labels = [label.title() for label in labels]
g_rounding_k.figure.legend(
    handles,
    labels,
    title="Rounding strategy",
    loc="outside lower right",
    bbox_to_anchor=(0.9, -0.05),
    # bbox_transform=g.figure.transFigure,
    ncol=2,
    fontsize="small",
)

# Save figure
g_rounding_k.figure.savefig(
    os.path.join(figure_folder, "rounding_diff_objval.png"),
    dpi=350,
    bbox_inches="tight",
)

plt.show()


# %% Analysis on solution quality -- use the feasible_df without filtering diff_objval yet

slow_feasible_df = (
    feasible_df[
        (feasible_df["round_threshold"] < 0.01)
        & (feasible_df["round_strategy"] == "slow")
    ]
    .groupby(["model_name", "T_simulate", "round_strategy", "round_threshold"])
    .agg(["mean", "std", "min", "max"])["round_gap"]
)

fast_feasible_df = (
    feasible_df[
        (feasible_df["round_threshold"] < 0.01)
        & (feasible_df["round_strategy"] == "fast")
    ]
    .groupby(["model_name", "T_simulate", "round_strategy", "round_threshold"])
    .agg(["mean", "std", "min", "max"])["round_gap"]
)
# Round to three digits
slow_feasible_df = slow_feasible_df.round(3)
fast_feasible_df = fast_feasible_df.round(3)

feasible_df[(feasible_df["round_strategy"] == "fast")].groupby(
    ["model_name", "T_simulate", "round_strategy", "round_threshold"]
).agg(["mean", "std", "min", "max"])["round_gap"].to_csv("fast_rounding.csv")


infeasibility_df[
    (infeasibility_df["round_threshold"] == 0.2)
    & (infeasibility_df["round_strategy"] == "fast")
]

# %% Draw boxplots comparing two rounding strategies when the threshold is 0.0
# Subset to the threshold of 0.0
threshold = 0.0
subset_threshold = feasible_df[feasible_df["round_threshold"] == threshold].copy()

# Save the csv
subset_threshold.to_csv("rounding_threshold0.csv")

# Captialize the round_strategy column
subset_threshold["round_strategy"] = subset_threshold["round_strategy"].apply(
    lambda x: x.title()
)

g_rounding_k = sns.catplot(
    subset_threshold,
    x="round_strategy",
    y="round_gap",
    col="T_simulate",
    row="model_name",
    row_order=["laos", "cambodia", "thailand"],
    kind="box",
    sharey=False,
    height=4,
    fill=False,
)

ax_id = 0
for ax in g_rounding_k.axes.flatten():
    country = ax.get_title().split("|")[0].strip()
    country = country.split("=")[1].strip()

    T_simulate = ax.get_title().split("|")[1].strip()
    T_simulate = T_simulate.split("=")[1].strip()

    ax.set_title(f"{country.title()} over {T_simulate}-hour", fontsize=15)
    ax.set_xlabel("")
    ax.set_ylabel("")

    # Selectively add xlabel and ylabel
    if ax_id == 3:
        ax.set_ylabel(name_map["round_gap"], fontsize=16)
    if ax_id == 7:
        ax.set_xlabel(name_map["round_strategy"], fontsize=16)
    ax_id += 1

# Save figure
g_rounding_k.figure.savefig(
    os.path.join(figure_folder, "rounding_optgap_threshold0.png"),
    dpi=350,
    bbox_inches="tight",
)

plt.show()

# %% Draw boxplot of optimization time speed-up when the rounding threshold was zero

subset_threshold_deviate = subset_threshold[
    subset_threshold["diff_objval"] <= 0.5
].copy()

g_speedup = sns.catplot(
    subset_threshold_deviate,
    x="round_strategy",
    y="opt_xspeed",
    col="T_simulate",
    row="model_name",
    row_order=["laos", "cambodia", "thailand"],
    kind="box",
    sharey=False,
    height=4,
    fill=False,
)

ax_id = 0
for ax in g_speedup.axes.flatten():
    country = ax.get_title().split("|")[0].strip()
    country = country.split("=")[1].strip()

    T_simulate = ax.get_title().split("|")[1].strip()
    T_simulate = T_simulate.split("=")[1].strip()

    ax.set_title(f"{country.title()} over {T_simulate}-hour", fontsize=15)
    ax.set_xlabel("")
    ax.set_ylabel("")

    # Selectively add xlabel and ylabel
    if ax_id == 3:
        ax.set_ylabel(name_map["opt_xspeed"], fontsize=16)
    if ax_id == 7:
        ax.set_xlabel(name_map["round_strategy"], fontsize=16)
    ax_id += 1

    # Draw a horizontal line at 1.0
    ax.axhline(1, ls="--", color="k", label="1.0x", alpha=0.5)

# Save figure
g_speedup.figure.savefig(
    os.path.join(figure_folder, "rounding_speedup_opttime_threshold0.png"),
    dpi=350,
    bbox_inches="tight",
)

plt.show()


# %% Draw boxplot of wall clock speed-up when the rounding threshold was zero
g_speedup = sns.catplot(
    subset_threshold_deviate,
    x="round_strategy",
    y="wall_clock_xspeed",
    col="T_simulate",
    row="model_name",
    row_order=["laos", "cambodia", "thailand"],
    kind="box",
    sharey=False,
    height=4,
    fill=False,
)

ax_id = 0
for ax in g_speedup.axes.flatten():
    country = ax.get_title().split("|")[0].strip()
    country = country.split("=")[1].strip()

    T_simulate = ax.get_title().split("|")[1].strip()
    T_simulate = T_simulate.split("=")[1].strip()

    ax.set_title(f"{country.title()} over {T_simulate}-hour", fontsize=15)
    ax.set_xlabel("")
    ax.set_ylabel("")

    # Selectively add xlabel and ylabel
    if ax_id == 3:
        ax.set_ylabel(name_map["wall_clock_xspeed"], fontsize=16)
    if ax_id == 7:
        ax.set_xlabel(name_map["round_strategy"], fontsize=16)
    ax_id += 1

    # Draw a horizontal line at 1.0
    ax.axhline(1, ls="--", color="k", label="1.0x", alpha=0.5)

# Save figure
g_speedup.figure.savefig(
    os.path.join(figure_folder, "rounding_speedup_wallclock_threshold0.png"),
    dpi=350,
    bbox_inches="tight",
)

plt.show()

# %%
