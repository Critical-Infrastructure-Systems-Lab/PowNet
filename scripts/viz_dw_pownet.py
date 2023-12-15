import os

from matplotlib.colors import LinearSegmentedColormap
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from pownet.folder_sys import get_temp_dir, get_output_dir
from pownet.core.input import SystemInput
from pownet.core.output import Visualizer

from functions import calc_percent_change, get_total_load, get_total_renewable





#=================== Read the file with the most stringent termination criterion

FILENAME = '20231212_1506_laos_0.0001_False_dwstats.csv'

folder_name = os.path.join(get_temp_dir(), 'dw_stats')
dw_stats = pd.read_csv(os.path.join(folder_name, FILENAME))

# Contextual info that affects runtime
dw_stats['total_load'] = get_total_load(model_name='laos')
# dw_stats['total_load'] = dw_stats['total_load'] / dw_stats['total_load'].max()

dw_stats['total_renewable'] = get_total_renewable(model_name='laos')
# dw_stats['total_renewable'] = dw_stats['total_renewable'] / dw_stats['total_renewable'].max()

dw_stats['excess_renewable'] = dw_stats['total_renewable'] - dw_stats['total_load']


# Ratio of opt time: DW-MIP to Gurobi-MIP
dw_stats['dwmip_mip_opt_time'] = dw_stats['dw_mip_time']/dw_stats['mip_gurobi_time']

# Optgap: DW-MIP to Gurobi-MIP
dw_stats['dwmip_mip_gap'] = calc_percent_change(
    dw_stats['dw_mip_objval'], dw_stats['mip_objval'])

# Optgap: DW-LP to Gurobi-MIP
dw_stats['dw_mip_gap'] = calc_percent_change(
    dw_stats['dw_objval'], dw_stats['mip_objval'])

# Optgap: Gurobi-LP to Gurobi-MIP
dw_stats['lp_mip_gap'] = calc_percent_change(
    dw_stats['lp_objval'], dw_stats['mip_objval'])



#%% Plot the optimality gap

# Compare the optimality gaps. Highlight there are periods where DW works well
optgap_columns = ['dwmip_mip_gap', 'dw_mip_gap']
optgap_column_labels = ['DW (MIP)', 'DW']
colors = ['#1b9e77', '#d95f02', '#7570b3', '#e7298a']

fig, ax = plt.subplots(figsize=(8, 5))

for col, lab, color in zip(optgap_columns, optgap_column_labels, colors):
    ax.plot(
        dw_stats[col],
        color = color,
        alpha = 0.9,
        linewidth = 3,
        label = lab
        )
ax.set_xlabel('Day')
ax.set_ylabel('MIP GAP (%)')


# Plot contextual information
ax2 = ax.twinx()
ax2.plot(
        dw_stats['excess_renewable'],
        linewidth = 1,
        linestyle = 'dotted',
        color = 'black',
        label = 'Excess renewables'
        )
ax2.set_ylabel('Power (MW)')

fig.legend()
plt.show()



#%% Plot the computation time
opt_time_columns = ['dw_mip_time', 'mip_gurobi_time', 'lp_gurobi_time']
opt_time_column_labels = ['DW (MIP)', 'Gurobi-MIP', 'Gurobi-LP']
colors = ['#1b9e77', '#d95f02', '#7570b3', '#e7298a']

fig, ax = plt.subplots(figsize=(8, 5))

for col, lab, color in zip(opt_time_columns, opt_time_column_labels, colors):
    ax.plot(
        dw_stats[col],
        color = color,
        alpha = 0.9,
        linewidth = 3,
        label = lab
        )
ax.set_xlabel('Day')
ax.set_ylabel('Optimization time (s)')


# Plot the fraction of dispatch from thermal units
ax2 = ax.twinx()
ax2.plot(
        dw_stats['excess_renewable'],
        linewidth = 1,
        linestyle = 'dotted',
        color = 'black',
        label = 'Excess renewables'
        )
ax2.set_ylabel('Power (MW)')

fig.legend()
plt.show()



#%% What happens during those periods? Plot against share of hydro
MODEL_NAME = 'laos'
T = 24

node_variables = pd.read_csv(
    os.path.join(get_output_dir(), '20231212_1327_laos_node_variables.csv')
    )

system_input = SystemInput(
    T = T,
    formulation = 'kirchhoff',
    model_name = MODEL_NAME
    )

visualizer = Visualizer()
visualizer.load(
    df = node_variables, 
    system_input = system_input, 
    model_name = MODEL_NAME
    )
visualizer.plot_area_fuelmix()


#%% Analysis
print(f'\n\nStats for {FILENAME}')
print('\nFraction as LP:', round(instances_as_lp.sum()*100/365, 0)[0], ' %')
print(f'Total DW time: {dw_times.sum().round(3)[0]} s')
print(f'Total LP Gurobi time: {gp_times_lp.sum().round(3)[0]} s')
print(f'Total MIP Gurobi time: {gp_times_mip.sum().round(3)[0]} s')

# Can DW be quicker than MIP?
dw_times_total = dw_times.sum(axis=1)
dw_quicker_mip = [(dw_time < mip_time)[0] for dw_time, mip_time in zip(dw_times_total.values, gp_times_mip.values)]
print(f'# instances DW is quicker than MIP Gurobi: {sum(dw_quicker_mip)}')


# What about LP gurobi vs MIP Gurobi?
lp_quicker_mip = [(lp_time < mip_time)[0] for lp_time, mip_time in zip(gp_times_lp.values, gp_times_mip.values)]
print(f'# instances LP Gurobi is quicker than MIP Gurobi: {sum(lp_quicker_mip)}')
