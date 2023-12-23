import os
import re

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
    calc_percent_change,
    get_total_daily_load,
    get_total_daily_renewable,
    get_total_daily_from_output,
)


MODEL_NAME = "thailand"
DWSTOP = 0.0001


naming_map = {
    'dw_mip_gap': 'DW-MIP Gap (%)',
    'mip_objval': 'MIP Obj.val ($)',
    'dw_mip_objval': 'DW-MIP Obj.val ($)',
    'dw_mip_time': 'DW-MIP opt.time (s)',
    'mip_gurobi_time':'Gurobi opt.time (s)',
    'excess_renewable': '(Total Renewables - Total load) in MW',
    'total_on': 'Online hours of thermal units',
    }

def plot_scatter(df, model_name: str, xname: str, yname: str):
    fig, ax = plt.subplots(dpi=350)
    ax.scatter(x=df[xname], y=df[yname])
    ax.set_xlabel(naming_map[xname])
    ax.set_ylabel(naming_map[yname])
    
    title_name = f'Country: {model_name.title()}'
    ax.set_title(title_name)
    plt.show()
    

# %%=================== Read the file with the most stringent termination criterion
dw_stats = read_dw_stats()
dw_stats = dw_stats[
    (dw_stats["model_name"] == MODEL_NAME)
    & (dw_stats["dw_stop"] == DWSTOP)
    & (dw_stats["relaxed_subp"] == False)
    ]
dw_stats = dw_stats[dw_stats["model_name"] == MODEL_NAME]

dw_stats = dw_stats.reset_index(drop=True)


#%% Is there a relationship between shortfall/curtailment/r_sys/import and excess renewables?

output_vars = ['s_pos', 's_neg'] #
dw_stats['mva_vars'] = get_total_daily_from_output(
    variables=output_vars,
    model_name=MODEL_NAME,
)

dw_stats['total_on'] = get_total_daily_from_output(
    variables=['status'],
    model_name=MODEL_NAME,
)

# plot_scatter(dw_stats, model_name=MODEL_NAME, xname='mva_vars', yname='excess_renewable')
# plot_scatter(dw_stats, model_name=MODEL_NAME, xname='total_on', yname='excess_renewable')


# plot_scatter(dw_stats, model_name=MODEL_NAME, xname='mva_vars', yname='dw_mip_time')
# plot_scatter(dw_stats, model_name=MODEL_NAME, xname='mva_vars', yname='dw_mip_gap')

plot_scatter(dw_stats, model_name=MODEL_NAME, xname='excess_renewable', yname='dw_mip_time')
plot_scatter(dw_stats, model_name=MODEL_NAME, xname='total_on', yname='dw_mip_time')
plot_scatter(dw_stats, model_name=MODEL_NAME, xname='mip_objval', yname='dw_mip_time')



plot_scatter(dw_stats, model_name=MODEL_NAME, xname='total_on', yname='dw_mip_gap')
plot_scatter(dw_stats, model_name=MODEL_NAME, xname='excess_renewable', yname='dw_mip_gap')
plot_scatter(dw_stats, model_name=MODEL_NAME, xname='mip_objval', yname='dw_mip_gap')


# %% What are the fraction of times?
dw_time_cols = ["master_time", "master_mip_time", "subp_time", "dw_overhead_time"]
frac_time = np.divide(
    dw_stats[dw_time_cols].values,
    dw_stats[dw_time_cols].sum(axis=1).values.reshape(-1, 1),
)
frac_time = pd.DataFrame(frac_time, columns=dw_time_cols)

frac_time_dict = frac_time.mean(axis=0).to_dict()

fig, ax = plt.subplots(figsize=(6, 5))
ax.pie(
    frac_time_dict.values(),
    labels=frac_time_dict.keys(),
    autopct="%1.0f%%",
)
ax.set_title(f"Breakdown of runtime: {MODEL_NAME}-{DWSTOP}", fontweight="bold")
ax.set_xticks([])
ax.set_yticks([])
plt.show()

# %% Plot the optimality gap
context = 'mva_vars'
# Compare the optimality gaps. Highlight there are periods where DW works well
optgap_columns = ["dwmip_mip_gap", "dw_mip_gap"]
optgap_column_labels = ["DW (MIP)", "DW"]
colors = ["#1b9e77", "#d95f02", "#7570b3", "#e7298a"]

fig, ax = plt.subplots(figsize=(8, 5))

for col, lab, color in zip(optgap_columns, optgap_column_labels, colors):
    ax.plot(
        dw_stats[col],
        # color = color,
        alpha=0.9,
        linewidth=1,
        label=lab,
    )
ax.set_xlabel("Day")
ax.set_ylabel("MIP GAP (%)")


# Plot contextual information
ax2 = ax.twinx()
ax2.plot(
    dw_stats[context], linewidth=1, linestyle="dotted", color="black", label=context
)
ax2.set_ylabel(context)

fig.legend()
plt.show()


# %% Plot the computation time
opt_time_columns = ["dw_mip_time", "mip_gurobi_time", "lp_gurobi_time"]
opt_time_column_labels = ["DW (MIP)", "Gurobi-MIP", "Gurobi-LP"]
colors = ["#1b9e77", "#d95f02", "#7570b3", "#e7298a"]

fig, ax = plt.subplots(figsize=(8, 5))

for col, lab, color in zip(opt_time_columns, opt_time_column_labels, colors):
    ax.plot(
        dw_stats[col],
        # color = color,
        alpha=0.9,
        linewidth=1,
        label=lab,
    )
ax.set_xlabel("Day")
ax.set_ylabel("Optimization time (s)")


# Plot the fraction of dispatch from thermal units
ax2 = ax.twinx()
ax2.plot(
    dw_stats[context], linewidth=1, linestyle="dotted", color="black", label=context
)
ax2.set_ylabel(context)

fig.legend()
plt.show()


# %% What happens during those periods? Plot against share of hydro

T = 24
node_variables = pd.read_csv(
    os.path.join(get_output_dir(), f"{MODEL_NAME}_node_variables.csv")
)

system_input = SystemInput(T=T, formulation="kirchhoff", model_name=MODEL_NAME)

output_processor = OutputProcessor()
output_processor.load(
    df=node_variables, system_input=system_input, model_name=MODEL_NAME
)

visualizer = Visualizer(model_name=MODEL_NAME, ctime=output_processor.ctime)
visualizer.plot_fuelmix_area(
    dispatch=output_processor.get_daily_dispatch(),
    demand=output_processor.get_daily_demand(),
    to_save=False,
)


# %% Plot fuel mix during specific periods

# idx_start, idx_end = 133, 136
# visualizer.plot_fuelmix_area(
#     dispatch=output_processor.get_daily_dispatch().iloc[idx_start:idx_end],
#     demand=output_processor.get_daily_demand().iloc[idx_start:idx_end],
#     to_save=False,
# )


# %% Create a master dataframe of stats across dw_gap values
dw_criteria_stats = pd.DataFrame()

dwgap_pattern = r"\d+_\d+_\w+_([0-9].*)_False_dwstats.csv"
folder_name = os.path.join(get_temp_dir(), "dw_stats")
filesets = [file for file in os.listdir(folder_name) if ("csv" in file) & ('False' in file)]

for file in filesets:
    subset = pd.read_csv(os.path.join(folder_name, file))
    subset["dwmip_mip_gap"] = calc_percent_change(
        subset["dw_mip_objval"], subset["mip_objval"]
    )
    # Add the criterion label
    dw_gap = re.match(dwgap_pattern, file).group(1)
    subset["dw_gap"] = dw_gap
    subset["dw_gap"] = subset["dw_gap"].astype("category")
    dw_criteria_stats = pd.concat([dw_criteria_stats, subset], axis=0)


# %% Boxplot of DWMIP-MIP OPT GAP
fig, ax = plt.subplots()
sns.boxplot(x="dw_gap", y="dwmip_mip_gap", data=dw_criteria_stats, ax=ax)
ax.set_ylabel("DW-MIP vs MIP Obj.Val Gap (%)")
ax.set_xlabel("Pct. Difference: primal/dual objective values")
plt.show()


# %% Boxplot of Optimization time (s)
fig, ax = plt.subplots()
sns.boxplot(x="dw_gap", y="dw_time", data=dw_criteria_stats, ax=ax)
ax.set_ylabel("Optimization time (s)")
ax.set_xlabel("Pct. Difference: primal/dual objective values")
plt.show()


# %% Analysis
print(f'{"Total DWMIP opt_time:":<40} {dw_stats.dw_mip_time.sum().round(2)} s')
print(f'{"Total MIP Gurobi opt_time:":<40} {dw_stats.mip_gurobi_time.sum().round(2)} s')
print(f'{"Total LP Gurobi opt_time:":<40} {dw_stats.lp_gurobi_time.sum().round(2)} s')

# Can DW be quicker than MIP?
dw_quicker_mip = [
    (dw_time < mip_time)
    for dw_time, mip_time in zip(dw_stats.dw_mip_time, dw_stats.mip_gurobi_time)
]
print(f"# instances DW is quicker than MIP Gurobi: {sum(dw_quicker_mip)}")
