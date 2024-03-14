# %%
import os
import re

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import seaborn.objects as so

from pownet.folder_sys import get_temp_dir
from functions import calc_percent_change


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
    "round_gap": "OPTGap (%)",
    "round_threshold": "Rounding threshold",
    "opt_xspeed": "x(Optimization time)",
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

# %% Plot the fraction of causes of infeasibility
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


for strategy in strategies:
    fig, axes = plt.subplots(
        nrows=3, ncols=3, figsize=(10, 10), layout="constrained", sharey=True
    )
    for ax, (model_name, T_simulate) in zip(axes.flatten(), model_T_pairs):
        subset = infeasibility_df[
            (infeasibility_df["model_name"] == model_name)
            & (infeasibility_df["T_simulate"] == T_simulate)
            & (infeasibility_df["round_strategy"] == strategy)
        ]
        subset = subset[["round_threshold", "True", "False"]].set_index(
            "round_threshold"
        )

        subset.plot.bar(stacked=True, legend=False, ax=ax)

        ax.set_ylabel("Fraction of solutions")
        ax.set_xlabel("")
        ax.set_title(f"{model_name.title()} over {T_simulate}-hour horizon")

        # Add legend
        handles, labels = ax.get_legend_handles_labels()
        fig.legend(
            handles,
            labels,
            title="Feasible Solution",
            loc="outside lower center",
            ncol=4,
        )

    fig.suptitle(f"Rounding strategy: {strategy.upper()}", fontweight="bold")

    fig.savefig(
        os.path.join(figure_folder, f"fraction_causes_infeasibility_{strategy}.png"),
        dpi=350,
    )
    plt.show()


# %% Visualize the solution quality
# Filter to only feasible solutions
feasible_df = compiled_df[compiled_df["rounding_is_feasible"]].reset_index()

# Filter to only low rounding thresholds (0, 0.01, 0.05, 0.1)
feasible_df = feasible_df[feasible_df["round_threshold"] != 0.5]


def grid_line_plot(df, x_name, y_name, strategy, sup_title, figure_name):
    subset = df[df["round_strategy"] == strategy]
    g = sns.FacetGrid(subset, col="T_simulate", row="model_name")
    g.map(
        sns.lineplot,
        x_name,
        y_name,
        linewidth=2.5,
        label="x(Opt.time)",
    )
    g.figure.suptitle(
        sup_title,
        fontweight="bold",
        y=1.05,
    )

    for ax in g.axes.flatten():
        country = ax.get_title().split("|")[0].strip()
        country = country.split("=")[1].strip()

        T_simulate = ax.get_title().split("|")[1].strip()
        T_simulate = T_simulate.split("=")[1].strip()

        ax.set_title(f"{country.title()} over {T_simulate}-hour horizon")

        ax.set_xlabel(name_map[x_name])
        ax.set_ylabel(name_map[y_name])

        ax.set_ylim(0, 5)

    g.figure.savefig(os.path.join(figure_folder, figure_name), dpi=350)
    plt.show()


for strategy in strategies:
    grid_line_plot(
        df=feasible_df,
        x_name="round_threshold",
        y_name="round_gap",
        strategy=strategy,
        sup_title=f"Rounding strategy: {strategy.upper()}",
        figure_name=f"rounding_quality_{strategy}.png",
    )


# %% Visualize the opt.time speed-up
# opt_time speed-up
g = sns.FacetGrid(feasible_df, col="round_strategy", row="model_name")
g = g.map(sns.lineplot, "round_threshold", "opt_xspeed", "model_name", linewidth=2.5)

g.set_titles(col_template="{col_name}", row_template="{row_name}")
g.set_axis_labels("Rounding threshold", "x(Opt.time)")
# Add horizontal lines at breakeven point of 1.0x
for ax in g.axes.flatten():
    ax.axhline(1, ls="--", color="k", label=["1.0x"])
    country = ax.get_title().split("|")[0].strip()
    strategy = ax.get_title().split("|")[1].strip()
    ax.set_title(f"{country.title()} | {name_map[strategy]}")

# g.figure.savefig(os.path.join(figure_folder, "xopttime_vs_thresholds.png"), dpi=350)
plt.show()


# %% Visualize the opt.time speed-up
# opt_time speed-up

for strategy in strategies:
    subset = feasible_df[feasible_df["round_strategy"] == strategy]
    g = sns.FacetGrid(subset, col="T_simulate", row="model_name")
    g.map(
        sns.lineplot,
        "round_threshold",
        "opt_xspeed",
        linewidth=2.5,
        label="x(Opt.time)",
    )
    # g.figure.suptitle(f"Speed-up of {strategy} rounding", fontweight="bold", y=1.05)
    g.figure.suptitle(
        f"Rounding strategy: {strategy.upper()}", fontweight="bold", y=1.05
    )

    for ax in g.axes.flatten():
        country = ax.get_title().split("|")[0].strip()
        country = country.split("=")[1].strip()

        T_simulate = ax.get_title().split("|")[1].strip()
        T_simulate = T_simulate.split("=")[1].strip()

        ax.set_title(f"{country.title()} over {T_simulate}-hour horizon")

        ax.set_xlabel(name_map["round_threshold"])
        ax.set_ylabel(name_map["opt_xspeed"])
        ax.set_ylim(0, 12)

        ax.axhline(1, ls="--", color="k", label=["1.0x"])

        g.figure.savefig(
            os.path.join(figure_folder, f"rounding_speedup_{strategy}.png"), dpi=350
        )

# g.figure.savefig(os.path.join(figure_folder, "xopttime_vs_thresholds.png"), dpi=350)
plt.show()

# %%
