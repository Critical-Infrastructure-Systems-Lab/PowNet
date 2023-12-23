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
    'dwmip_mip_gap': 'DW-MIP Gap (%)',
    'mip_objval': 'MIP Obj.val ($)',
    'dw_mip_objval': 'DW-MIP Obj.val ($)',
    'dw_mip_time': 'DW-MIP opt.time (s)',
    'mip_gurobi_time':'Gurobi opt.time (s)',
    'excess_renewable': '(Total renewables - Total load) in MW',
    'total_on': 'Online hours of thermal units',
    'dw_stop': '% Difference: primal/dual objective values'
    }
colors = ["#1b9e77", "#d95f02", "#7570b3", "#e7298a"]

def plot_scatter(df, model_name: str, xname: str, yname: str):
    fig, ax = plt.subplots(dpi=350)
    ax.scatter(x=df[xname], y=df[yname])
    ax.set_xlabel(naming_map[xname])
    ax.set_ylabel(naming_map[yname])
    
    title_name = f'Country: {model_name.title()}'
    ax.set_title(title_name)
    plt.show()


def plot_against_excess_renewable(factor: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(
        dw_stats[factor],
        alpha=0.9,
        linewidth=1,
        label=naming_map[factor]
    )
    ax.set_xlabel("Day")
    ax.set_ylabel(naming_map[factor])
    
    # Plot contextual information
    ax2 = ax.twinx()
    ax2.plot(
        dw_stats['excess_renewable'],
        linewidth=1.5,
        linestyle="dotted",
        color="black",
        label=naming_map['excess_renewable']
    )
    ax2.set_ylabel(naming_map['excess_renewable'])
    
    fig.legend()
    plt.show()


def plot_exit_conditions(df: pd.DataFrame, model_name: str, factor: str) -> None:
    fig, ax = plt.subplots()
    sns.boxplot(
        data=df[df['model_name'] == model_name],
        x="dw_stop",
        y=factor, 
        log_scale = True,
        ax=ax,
        )
    ax.set_ylabel(naming_map[factor])
    ax.set_xlabel(naming_map['dw_stop'])
    
    title_name = f'Country: {model_name.title()}'
    ax.set_title(f'Country: {title_name}')
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

plot_scatter(dw_stats, model_name=MODEL_NAME, xname='mip_objval', yname='dwmip_mip_gap')
plot_scatter(dw_stats, model_name=MODEL_NAME, xname='excess_renewable', yname='dwmip_mip_gap')
plot_scatter(dw_stats, model_name=MODEL_NAME, xname='total_on', yname='dwmip_mip_gap')

plot_scatter(dw_stats, model_name=MODEL_NAME, xname='mip_objval', yname='dw_mip_time')
plot_scatter(dw_stats, model_name=MODEL_NAME, xname='excess_renewable', yname='dw_mip_time')
plot_scatter(dw_stats, model_name=MODEL_NAME, xname='total_on', yname='dw_mip_time')



# %% Plot the daily performance
plot_against_excess_renewable('dwmip_mip_gap')
plot_against_excess_renewable('dw_mip_time')



# %% Boxplot of DWMIP-MIP OPT GAP
dw_criteria_stats = read_dw_stats()
for country in ['laos', 'cambodia', 'thailand']:
    plot_exit_conditions(df=dw_criteria_stats, model_name=country, factor='dwmip_mip_gap')
    plot_exit_conditions(df=dw_criteria_stats, model_name=country, factor='dw_mip_time')


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
