""" This script visualizes results from then new Dantzig-Wolfe experiments.
We want to show the followings: Solution quality and optimization time.
Dantzig-Wolfe always generate a feasible solution in this case.
"""

# %% Imports and naming conventions
import os
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from pownet.folder_utils import get_temp_dir

naming_map = {
    "dw_gap": "Optimality gap (%)",
    "mip_objval": "MIP Obj.val ($)",
    "dw_mip_objval": "CGH-MIP Obj.val ($)",
    "dw_mip_time": "CGH-MIP opt.time (s)",
    "dw_itercount": "CGH Iterations",
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


figure_folder = os.path.join(get_temp_dir(), "figures_dw")

# %% Load the data
folder_name = os.path.join(get_temp_dir(), "dw_stats")
stats = pd.read_csv(os.path.join(folder_name, "dw_experiment_outputs.csv"))

stats["dw_gen_col_time"] = stats["master_time"] + stats["subp_time"]

# Capitalize country names
stats["model_name"] = stats["model_name"].str.capitalize()

# Calculate speed-up of optim.time
stats["xSpeedup"] = stats["mip_gurobi_time"] / stats["dw_total_time"]

# Calculate-speed-up of wallclock
stats["x_wallclock"] = stats["wall_clock_mip_gurobi"] / stats["wall_clock_dw"]


# %% SAMPLE SPACE: OPTIMALITY GAP
print("\nSample space of DW OPTGap")
g = sns.FacetGrid(stats, row="set_rmpgap", col="set_dwimprove", margin_titles=True)
g.map(
    sns.barplot,
    "model_name",
    "dw_gap",
    order=["Laos", "Cambodia", "Thailand"],
    linewidth=2.5,
)
plt.show()


# %% SAMPLE SPACE: RUNTIME

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


# %% TIMESERIES OF OPT.TIME
def plot_log_time_series(df, country):
    fig, ax = plt.subplots()
    ax.semilogy(
        df["master_mip_time"],
        label="CGH: Selecting schedules",
        # alpha=0.75,
        linewidth=1.25,
    )
    ax.semilogy(
        df["dw_gen_col_time"],
        label="CGH: Generating schedules",
        # alpha=0.5,
        linewidth=1.25,
    )
    ax.semilogy(
        df["mip_gurobi_time"],
        label="Benchmark solver (Gurobi)",
        # alpha=0.75,
        linewidth=1.25,
        color="black",
    )
    ax.set_xlabel("Day")
    ax.set_ylabel("Optimization time (s)")
    ax.set_title(f"{country} over 24-hr horizon")
    plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", borderaxespad=0.0)

    country = df["model_name"].iloc[0]
    fig.savefig(
        os.path.join(figure_folder, f"dw_time_{country}.png"),
        dpi=350,
        bbox_inches="tight",
    )

    plt.show()


best_dw_thailand = stats[
    (stats["model_name"] == "Thailand")
    & (stats["set_rmpgap"] == 50)
    & (stats["set_dwimprove"] == 50)
]
best_dw_thailand = best_dw_thailand.reset_index(drop=True)
plot_log_time_series(best_dw_thailand, country="Thailand")

best_dw_laos = stats[
    (stats["model_name"] == "Laos")
    & (stats["set_rmpgap"] == 50)
    & (stats["set_dwimprove"] == 50)
]
best_dw_laos = best_dw_laos.reset_index(drop=True)
plot_log_time_series(best_dw_laos, country="Laos")


# %% Select RMPGAP
sel_rmpgap = 50  # [1.e+01, 1.e-04, 1.e-02, 1.e+00, 5.e+01]
param_subset = stats[
    (stats["set_rmpgap"] == sel_rmpgap) & (stats["set_dwimprove"] >= 50)
]

param_subset2 = stats[(stats["set_rmpgap"] == 0.0001) & (stats["set_dwimprove"] >= 50)]


# %% OPTIMALITY GAP - BOXPLOT
g = sns.FacetGrid(
    param_subset, col="set_dwimprove", margin_titles=True, height=3, col_wrap=3
)
g.map(
    sns.boxplot,
    "model_name",
    "dw_gap",
    order=["Laos", "Cambodia", "Thailand"],
    linewidth=1.5,
)
re_pat = r"""\=\s(\d+.\d+)"""
for ax in g.axes.flatten():
    # Get the numerical value from the title
    dw_improve = ax.get_title()
    dw_improve = re.findall(re_pat, dw_improve)[0]
    ax.set_title(f"Obj.Improve: {dw_improve} %")

    plt.setp(ax.texts, text=f"RMPGap {sel_rmpgap} (%)")

    ax.set_xlabel("")
    ax.set_ylabel("Optimality gap (%)")

g.figure.savefig(
    os.path.join(figure_folder, "dw_gap_rmpgap50.png"), dpi=350, bbox_inches="tight"
)

plt.show()


# %% BARPLOT SPEED-UP - OPT.TIME

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

alpha = 0.6

fig, ax = plt.subplots()
ax.semilogy(
    laos100["master_mip_time"],
    label="CGH: Selecting schedule",
    linewidth=1.25,
    alpha=alpha,
)
ax.semilogy(
    laos100["dw_gen_col_time"],
    label="CGH: Generating schedules",
    linewidth=1.25,
    alpha=alpha,
)
ax.semilogy(
    laos100["mip_gurobi_time"],
    label="Benchmark solver (Gurobi)",
    linewidth=1.25,
    color="black",
    linestyle="dashed",
    # alpha=alpha,
)

ax.set_xlabel("Day")
ax.set_ylabel("Optimization time (s)")
ax.set_title("Laos (without spinning reserve)\n over 24-hr horizon")


# Overlay with solid line when the master problem is quicker
subset_df = laos100.copy()
subset_df.loc[~subset_df["is_master_quicker"], "master_mip_time"] = np.nan
ax.semilogy(
    subset_df["master_mip_time"],
    label="CGH: Selecting schedule",
    linewidth=2.5,
    c="tab:blue",
)

"""# Highlight that area when the master_time is quicker than gurobi_mip_time
for idx, row in laos100.iterrows():
    if row["is_master_quicker"]:
        ax.axvspan(
            idx - 0.5,
            idx + 0.5,
            alpha=0.1,
            color="green",
            label="",
        )
"""
plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", borderaxespad=0.0)
fig.savefig(
    os.path.join(figure_folder, f"dw_time_laos_100.png"), dpi=350, bbox_inches="tight"
)
plt.show()


# %% SPEED-UP - OPTIMIZATION - LinePlot
name_map = {
    "set_dwimprove": "Obj.improve (%)",
    "x_wallclock": "xSpeed-up (Wallclock)",
    "xSpeedup": "xSpeed-up (Opt.time)",
    "dw_gap": "Optimality gap (%)",
}
"""
def plot_line(df, x_name, y_name, ymax, set_rmpgap, horizontal_line=True):

    g = sns.FacetGrid(df, col="model_name", sharey=True, height=3)
    g.map(
        sns.lineplot,
        x_name,
        y_name,
        linewidth=2.5,
    )
    g.figure.suptitle(
        f"Discrete Dantzig-Wolfe w/ duality gap {set_rmpgap}%",
        fontweight="bold",
        y=1.03,
    )

    ax_id = 0
    for ax in g.axes.flatten():
        country = ax.get_title().split("|")[0].strip()
        country = country.split("=")[1].strip()

        ax.set_title(f"{country.title()} over 24-hour")
        ax.set_xlabel("")
        ax.set_ylabel("")
        # The figure is 3x3. Only the bottom row should have x-axis labels
        # Only the left column should have y-axis labels
        if ax_id == 0:
            ax.set_ylabel(name_map[y_name])
        if ax_id == 1:
            ax.set_xlabel(name_map[x_name])
        ax_id += 1

        ax.set_ylim(0, ymax)

        if horizontal_line:
            ax.axhline(1, ls="--", color="k", label=["1.0x"])

        g.figure.savefig(
            os.path.join(figure_folder, f"dw_{y_name}_{set_rmpgap}.png"),
            dpi=350,
            bbox_inches="tight",
        )
    plt.show()


plot_line(
    param_subset,
    x_name="set_dwimprove",
    y_name="x_wallclock",
    ymax=2,
    set_rmpgap=sel_rmpgap,
)

y_name = "xSpeedup"
plot_line(
    param_subset,
    x_name="set_dwimprove",
    y_name="xSpeedup",
    ymax=2,
    set_rmpgap=sel_rmpgap,
)

plot_line(
    param_subset,
    "set_dwimprove",
    "dw_gap",
    ymax=25,
    set_rmpgap=sel_rmpgap,
    horizontal_line=False,
)
plot_line(
    param_subset2,
    "set_dwimprove",
    "x_wallclock",
    ymax=2,
    set_rmpgap=0.0001,
)

plot_line(
    param_subset2,
    "set_dwimprove",
    "xSpeedup",
    ymax=2,
    set_rmpgap=0.0001,
)

plot_line(
    param_subset2,
    "set_dwimprove",
    "dw_gap",
    ymax=25,
    set_rmpgap=0.0001,
    horizontal_line=False,
)

"""

# %% LINEPLOT - OPTIMALITY GAP

sel_rmpgaps = [0.0001, 50]

subset = stats.loc[
    (stats["set_dwimprove"] >= 50) & (stats["set_rmpgap"].isin(sel_rmpgaps))
]

g = sns.FacetGrid(
    subset,
    hue="set_rmpgap",
    col="model_name",
    sharey=True,
)
g.map(sns.lineplot, "set_dwimprove", "dw_gap", linewidth=2.5, alpha=0.5)

ax_id = 0
for ax in g.axes.flatten():
    country = ax.get_title().split("|")[0].strip()
    country = country.split("=")[1].strip()
    ax.set_title(f"{country.title()} over 24-hour")

    ax.set_ylim(0, 25)

    # Format labels
    ax.set_xlabel("")
    ax.set_ylabel("")
    if ax_id == 0:
        ax.set_ylabel("Optimality gap (%)")
    if ax_id == 1:
        ax.set_xlabel("Obj.improve (%)")
    ax_id += 1


# Format legend
g.add_legend(title="Dual Gap (%)")

g.figure.savefig(
    os.path.join(figure_folder, f"dw_gap.png"),
    dpi=350,
    bbox_inches="tight",
)

plt.show()


# %% LINEPLOT - SPEED-UP (OPT.TIME)

g = sns.FacetGrid(
    subset,
    hue="set_rmpgap",
    col="model_name",
    sharey=True,
)

g.map(sns.lineplot, "set_dwimprove", "xSpeedup", linewidth=2.5, alpha=0.5)

ax_id = 0
for ax in g.axes.flatten():
    # Horizontal line at 1.0x
    ax.axhline(1, ls="--", color="k", label="1.0x")

    country = ax.get_title().split("|")[0].strip()
    country = country.split("=")[1].strip()
    ax.set_title(f"{country.title()} over 24-hour")

    ax.set_ylim(0, 1.5)

    # Format labels
    ax.set_xlabel("")
    ax.set_ylabel("")
    if ax_id == 0:
        ax.set_ylabel("xSpeed-up (Opt.time)")
    if ax_id == 1:
        ax.set_xlabel("Incremental improve (%)")
    ax_id += 1


# Format legend
handles, labels = ax.get_legend_handles_labels()
g.figure.legend(
    handles,
    labels,
    title="Dual Gap (%)",
    loc="outside lower right",
    bbox_to_anchor=(1, -0.15),
    # bbox
    ncol=3,
)

g.figure.savefig(
    os.path.join(figure_folder, f"dw_speedup_opttime.png"),
    dpi=350,
    bbox_inches="tight",
)

# %% LINEPLOT - SPEED-UP (WALLCLOCK)

g = sns.FacetGrid(
    subset,
    hue="set_rmpgap",
    col="model_name",
    sharey=True,
)

g.map(sns.lineplot, "set_dwimprove", "x_wallclock", linewidth=2.5, alpha=0.5)

ax_id = 0
for ax in g.axes.flatten():
    # Horizontal line at 1.0x
    ax.axhline(1, ls="--", color="k", label="1.0x")

    country = ax.get_title().split("|")[0].strip()
    country = country.split("=")[1].strip()
    ax.set_title(f"{country.title()} over 24-hour")

    ax.set_ylim(0, 1.5)

    # Format labels
    ax.set_xlabel("")
    ax.set_ylabel("")
    if ax_id == 0:
        ax.set_ylabel("xSpeed-up (Wall clock)")
    if ax_id == 1:
        ax.set_xlabel("Incremental improve (%)")
    ax_id += 1


# Format legend
handles, labels = ax.get_legend_handles_labels()
g.figure.legend(
    handles,
    labels,
    title="Dual Gap (%)",
    loc="outside lower right",
    bbox_to_anchor=(1, -0.15),
    # bbox
    ncol=3,
)

g.figure.savefig(
    os.path.join(figure_folder, f"dw_speedup_wallclock.png"),
    dpi=350,
    bbox_inches="tight",
)

# %% Plot heatmap of dw_itercount as a fuction of set_rmpgap and set_dwimprove using the stats dataframe

# Heatmap of dw_itercount
subset = (
    stats[["model_name", "set_rmpgap", "set_dwimprove", "dw_itercount"]]
    .groupby(["model_name", "set_rmpgap", "set_dwimprove"])
    .mean()
    .reset_index()
)

# Pivot the dataframe
country = "Cambodia"
heatmap_df = subset[subset["model_name"] == country]
heatmap_df = heatmap_df.pivot_table(
    index="set_rmpgap", columns=["set_dwimprove"], values="dw_itercount"
)


# %% Scatter plot to show whether the number of iterations is
# correlated with the optimality gap

g = sns.FacetGrid(
    stats,
    col="model_name",
    sharey=False,
    height=3,
    aspect=1.5,
    col_order=["Laos", "Cambodia", "Thailand"],
)

g.map(
    sns.scatterplot,
    "dw_itercount",
    "dw_gap",
    alpha=0.15,
)

# Rename the axes
ax_id = 0
for ax in g.axes.flatten():
    country = ax.get_title().split("|")[0].strip()
    country = country.split("=")[1].strip()
    ax.set_title(f"{country.title()} over 24-hour")
    ax.set_xlabel("CGH Iterations")
    ax.set_ylabel("Optimality gap (%)")
    ax_id += 1
plt.show()

# Save figure
g.figure.savefig(
    os.path.join(figure_folder, f"dw_itercount_gap.png"),
    dpi=350,
    bbox_inches="tight",
)


# %% Compare dw_gap, dw_itercount, and dw_total_time between two cases:
# Case 1: set_rmpgap = 0.0001 and set_dwimprove = 0.0
# Case 2: set_rmpgap = 50 and set_dwimprove = 100

case1 = stats[(stats["set_rmpgap"] == 0.0001) & (stats["set_dwimprove"] == 0.0)].copy()
# "Dual gap = 0.0001% | Incremental improve = 0.0%"
case1["case"] = "Late stopping"
case2 = stats[(stats["set_rmpgap"] == 50) & (stats["set_dwimprove"] == 100)].copy()
"Dual gap = 50% | Incremental improve = 100%"
case2["case"] = "Early stopping"

# Concatenate the two cases
cases = pd.concat([case1, case2])


# %% Plot boxplot of two cases for each country - optimality gap
g = sns.FacetGrid(
    cases,
    col="model_name",
    sharey=False,
    height=3,
    aspect=1.5,
    col_order=["Laos", "Cambodia", "Thailand"],
)

g.map(
    sns.boxplot,
    "case",
    "dw_gap",
    # linewidth=2.5,
    order=["Late stopping", "Early stopping"],
    width=0.5,
    fill=False,
)

# Rename the axes
ax_id = 0
for ax in g.axes.flatten():
    country = ax.get_title().split("|")[0].strip()
    country = country.split("=")[1].strip()
    ax.set_title(f"{country.title()} over 24-hour")
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax_id += 1

    if ax_id == 1:
        ax.set_ylabel("Optimality gap (%)")

# Save the figure
g.figure.savefig(
    os.path.join(figure_folder, f"dw_gap_cases.png"),
    dpi=350,
    bbox_inches="tight",
)

# %% Speed-up of optimization time

subset_cases = cases.copy()
# Filter to only include instances where the deviation is less than 1%
subset_cases["obj_deviation"] = (
    subset_cases["dw_mip_objval"] - subset_cases["mip_objval"]
) / (subset_cases["true_objval"] + 1)
subset_cases["obj_deviation"] = subset_cases["obj_deviation"] * 100

# Filter to only include instances where the deviation is less than 0.5%
subset_cases = subset_cases[subset_cases["obj_deviation"] <= 0.5]

g = sns.FacetGrid(
    subset_cases,
    col="model_name",
    sharey=False,
    height=3,
    aspect=1.5,
    col_order=["Laos", "Cambodia", "Thailand"],
)

g.map(
    sns.boxplot,
    "case",
    "xSpeedup",
    # linewidth=2.5,
    order=["Late stopping", "Early stopping"],
    width=0.5,
    fill=False,
)

# Rename the axes
ax_id = 0
for ax in g.axes.flatten():
    country = ax.get_title().split("|")[0].strip()
    country = country.split("=")[1].strip()
    ax.set_title(f"{country.title()} over 24-hour")
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax_id += 1

    if ax_id == 1:
        ax.set_ylabel("xSpeed-up (Opt.time)")

# Save the figure
g.figure.savefig(
    os.path.join(figure_folder, f"dw_speedup_cases.png"),
    dpi=350,
    bbox_inches="tight",
)


# %% Print statistics to support the box plots:
# min, 25th percentile, mean, median, 75th percentile, max
print("\nOptimality gap:")
print(subset_cases.groupby(["model_name", "case"]).describe()["dw_gap"].round(2))

print("\nSpeed-up of optimization time:")
print(subset_cases.groupby(["model_name", "case"]).describe()["xSpeedup"].round(2))

# Save the two cases to a csv file
subset_cases.groupby(["model_name", "case"]).describe()["dw_gap"].round(2).to_csv(
    os.path.join(figure_folder, "dw_stats_optgap.csv")
)

subset_cases.groupby(["model_name", "case"]).describe()["xSpeedup"].round(2).to_csv(
    os.path.join(figure_folder, "dw_stats_speedup.csv")
)


# Minimum optimality gap from Cambodia and Thailand
print(
    subset_cases[subset_cases["model_name"] == "Cambodia"]
    .groupby("case")
    .min()["dw_gap"]
    .round(1)
)

stats[stats["model_name"] == "Thailand"]["dw_gap"].min()

# %% Boxplot optimality gap of case 1
g = sns.boxplot(
    x="model_name",
    y="dw_gap",
    data=case1,
    order=["Laos", "Cambodia", "Thailand"],
)
