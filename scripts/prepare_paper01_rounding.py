""" 
Prepare plots for Paper 1 (First section and DW results)

Evaluate the heuristic rounding strategies based on
1) Solution quality - feasibility, MIP gap
2) Computational time - time to solve the MIP
"""
# %% Import packages
import itertools
import os
import re

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from pownet.folder_sys import get_temp_dir
from functions import calc_percent_change

# Specify the folder where the figures are stored
figure_folder = os.path.join(get_temp_dir(), "figures_paper01")
if not os.path.exists(figure_folder):
    os.makedirs(figure_folder)


# %% Read statistics from files and compile into a single dataframe
files = os.listdir(os.path.join(get_temp_dir(), "rounding_stats"))
# files_both = [f for f in files if ("both" in f) and ("False" in f)]
# files_up = [f for f in files if ("up" in f) and ("False" in f)]
# files_adaptive = [f for f in files if "True" in f]

# Read the files and compile into a single dataframe
compiled_df = pd.DataFrame()
capture_pat = r".*_rounding_(\w+)_(\w+)_(.+)_(\d+).csv"
for file in files:
    # The filename contains information about the model and rounding strategy
    match = re.search(capture_pat, file)
    model_name = match.group(1)
    direction = match.group(2)
    threshold = match.group(3)
    max_k = match.group(4)

    # Read the file
    subset = pd.read_csv(os.path.join(get_temp_dir(), "rounding_stats", file))
    # Add information about the model and rounding strategy to the dataframe
    subset["model_name"] = model_name
    subset["direction"] = direction
    subset["threshold"] = float(threshold)
    subset["max_k"] = int(max_k)
    # Process new features based on existing features
    subset["is_valid"] = subset["rounding_is_feasible"] & subset["rounding_is_int"]
    subset["lp_mip_gap"] = calc_percent_change(
        subset["rounding_objval"], subset["mip_objval"]
    )
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
compiled_df = compiled_df.sort_values(by=["model_name", "direction", "threshold"])

# Filter to max_k = 30
compiled_df = compiled_df[compiled_df["max_k"] == 30]

# %% Analyze feasibility metric
# Valid fractions
cols = ["model_name", "direction", "threshold", "is_valid"]
# Feasibility metric: the number of times the solution is feasible and is integer
valid_fraction = (
    compiled_df[cols]
    .groupby(["model_name", "direction", "threshold"], observed=False)["is_valid"]
    .mean()
    .reset_index()
)

# Create maps to use for naming when plotting
ordered_titles = [
    "Cambodia | Adaptive",
    "Cambodia | Up and down",
    "Cambodia | Up only",
    "Laos | Adaptive",
    "Laos | Up and down",
    "Laos | Up only",
    "Thailand | Adaptive",
    "Thailand | Up and down",
    "Thailand | Up only",
]

direction_map = {"both": "Up and down", "up": "Up only", "adaptive": "Adaptive"}

# %% Plot fractions of feasible solutions
# Create a grid of subplots for each unique value in the 'direction' column
g = sns.FacetGrid(valid_fraction, col="direction", row="model_name")
g = g.map(sns.lineplot, "threshold", "is_valid", "direction", linewidth=2.5)
# g.set_titles(col_template="{col_name}", row_template="{row_name}")
g.set_axis_labels("Rounding threshold", "Fraction feasible")

for idx, ax in enumerate(g.axes.flatten()):
    ax.axhline(1, ls="--", color="k", label=["1.0x"])
    ax.set_title(ordered_titles[idx])
plt.show()


# %% Process the causes of infeasibility
infeasi_count_df = compiled_df.copy()
infeasi_count_df["infeasibility_reason"] = None
infeasi_count_df.loc[
    ~infeasi_count_df["rounding_is_int"], "infeasibility_reason"
] = "Infeasible - not rounded"
infeasi_count_df.loc[
    ~infeasi_count_df["rounding_is_feasible"], "infeasibility_reason"
] = "Infeasible - out of bound"
infeasi_count_df.loc[
    ~infeasi_count_df["rounding_is_int"] & ~infeasi_count_df["rounding_is_feasible"],
    "infeasibility_reason",
] = "Both infeasibilities"
infeasi_count_df.loc[
    infeasi_count_df["rounding_is_int"] & infeasi_count_df["rounding_is_feasible"],
    "infeasibility_reason",
] = "Feasible"

infeasi_count_df = (
    infeasi_count_df.groupby(
        ["model_name", "direction", "threshold", "infeasibility_reason"], observed=False
    )["infeasibility_reason"]
    .count()
    .reset_index(name="count")
)

# Convert from long to wide format to do plotting
infeasi_count_df = pd.pivot(
    infeasi_count_df,
    index=["model_name", "direction", "threshold"],
    columns="infeasibility_reason",
    values="count",
)
infeasi_count_df = infeasi_count_df.reset_index()
["model_name", "direction", "threshold"]

sub_cols = [
    "Feasible",
    "Infeasible - not rounded",
    "Infeasible - out of bound",
    "Both infeasibilities",
]
infeasi_count_df[sub_cols] /= 365

cols_2_plot = ["threshold"] + sub_cols


# %% Plot the fraction of causes of infeasibility
fig, axes = plt.subplots(
    nrows=3,
    ncols=3,
    figsize=(8, 8),
    layout="constrained",
    sharex=True,
    sharey=True,
)
pairs = itertools.product(
    infeasi_count_df.model_name.unique(), infeasi_count_df.direction.unique()
)
for (country, direction), ax in zip(pairs, axes.flatten()):
    subset = infeasi_count_df.loc[
        (infeasi_count_df["model_name"] == country)
        & (infeasi_count_df["direction"] == direction)
    ]
    subset = subset[cols_2_plot]
    subset = subset.set_index("threshold")
    if len(subset) > 0:
        subset.plot.bar(stacked=True, legend=False, ax=ax)
        ax.set_ylabel("Fraction of solutions")
        ax.set_xlabel("Rounding threshold")
        ax.set_title(f"{country.title()} | {direction_map[direction]}")

handles, labels = ax.get_legend_handles_labels()
fig.legend(handles, labels, loc="outside upper center", ncol=4)
fig.savefig(os.path.join(figure_folder, "fraction_causes_infeasibility.png"), dpi=350)
plt.show()


# %% Plot MIP gap vs. rounding threshold

# Filter to only feasible solutions
gap_df = compiled_df[compiled_df.is_valid].reset_index()

# Create a grid of subplots for each unique value in the 'direction' column
g = sns.FacetGrid(gap_df, col="direction", row="model_name")
g = g.map(sns.lineplot, "threshold", "lp_mip_gap", "model_name", linewidth=2.5)

g.set_titles(col_template="{col_name}", row_template="{row_name}")
g.set_axis_labels("Rounding threshold", "MIP Gap (%)")
g.set(ylim=(0, 5))

for ax in g.axes.flatten():
    country = ax.get_title().split("|")[0].strip()
    direction = ax.get_title().split("|")[1].strip()
    ax.set_title(f"{country.title()} | {direction_map[direction]}")

g.figure.savefig(os.path.join(figure_folder, "mipgap_vs_thresholds.png"), dpi=350)
plt.show()


# %% Plot the opt.time speed-up
cols = ["model_name", "direction", "threshold", "opt_xspeed", "wall_clock_xspeed"]
speed_df = compiled_df.loc[compiled_df.is_valid, cols].reset_index(drop=True)

# opt_time speed-up
g = sns.FacetGrid(speed_df, col="direction", row="model_name")
g = g.map(sns.lineplot, "threshold", "opt_xspeed", "model_name", linewidth=2.5)

g.set_titles(col_template="{col_name}", row_template="{row_name}")
g.set_axis_labels("Rounding threshold", "x(Opt.time)")
# Add horizontal lines at breakeven point of 1.0x
for ax in g.axes.flatten():
    ax.axhline(1, ls="--", color="k", label=["1.0x"])
    country = ax.get_title().split("|")[0].strip()
    direction = ax.get_title().split("|")[1].strip()
    ax.set_title(f"{country.title()} | {direction_map[direction]}")

g.figure.savefig(os.path.join(figure_folder, "xopttime_vs_thresholds.png"), dpi=350)
plt.show()

# %% Plot the wallclock speed-up
# Wall clock speed-up
g = sns.FacetGrid(speed_df, col="direction", row="model_name")
g = g.map(sns.lineplot, "threshold", "wall_clock_xspeed", "model_name", linewidth=2.5)

g.set_titles(col_template="{col_name}", row_template="{row_name}")
g.set_axis_labels("Rounding threshold", "x(Wallclock)")
for ax in g.axes.flatten():
    ax.axhline(1, ls="--", color="k", label=["1.0x"])
    country = ax.get_title().split("|")[0].strip()
    direction = ax.get_title().split("|")[1].strip()
    ax.set_title(f"{country.title()} | {direction_map[direction]}")
plt.show()


# %% Create statistics
groupby_cols = ["model_name", "direction", "threshold"]
# Mean speed-up
x_opt_time = compiled_df.groupby(groupby_cols)["opt_xspeed"].mean()
x_wallclock = compiled_df.groupby(groupby_cols)["wall_clock_xspeed"].mean()

# Mean MIPGap
mean_mipgap = compiled_df.groupby(groupby_cols)["lp_mip_gap"].mean()

# Print the average feasibility
mean_feasibility = compiled_df.groupby(groupby_cols)["is_valid"].mean()


# %% Plot histogram of k
compiled_df.groupby(["model_name", "direction"])["rounding_k"].hist(
    alpha=0.4, legend=["both", "up", "adaptive"]
)
