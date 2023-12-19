''' Evaluate the heuristic rounding strategies based on
1) Solution quality - feasibility, MIP gap
2) Computational time - time to solve the MIP
'''
#%% Import packages
import os
import re

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from pownet.folder_sys import get_temp_dir
from functions import calc_percent_change


MODEL_NAME = 'dummy_trade'



#%% Read statistics from files and compile into a single dataframe
files = os.listdir(os.path.join(get_temp_dir(), 'rounding_stats'))
# files = [f for f in files if MODEL_NAME in f]
files_both = [f for f in files if ('both' in f) and ('False' in f)]
files_up = [f for f in files if ('up' in f) and ('False' in f)]
files_adaptive = [f for f in files if 'True' in f]

# Read the files and compile into a single dataframe
compiled_df = pd.DataFrame()
capture_pat = r'.*_rounding_(\w+)_(\w+)_(.+)_(\d+).csv'
for file in files:
    # Extract information from file name
    match = re.search(capture_pat, file)
    model_name = match.group(1)
    direction = match.group(2)
    threshold = match.group(3)
    max_k = match.group(4)
    # Append filename info to dataframe
    subset = pd.read_csv(os.path.join(get_temp_dir(), 'rounding_stats', file))
    # Extract info from filename
    subset['model_name'] = model_name
    subset['direction'] = direction
    subset['threshold'] = float(threshold)
    subset['max_k'] = int(max_k)
    # Create new features
    subset['is_valid'] = subset['rounding_is_feasible'] & subset['rounding_is_int']
    subset['lp_mip_gap'] = calc_percent_change(subset['rounding_objval'], subset['mip_objval'])
    subset['opt_xspeed'] = subset['mip_opt_time'] / subset['rounding_opt_time']
    subset['wall_clock_xspeed'] = subset['wall_clock_mip'] / subset['wall_clock_rounding']
    subset['fraction_runtime'] = subset['rounding_opt_time']/ subset['wall_clock_rounding']

    # Append the new df to the master_df   
    compiled_df = pd.concat([compiled_df, subset], axis=0)

# Order compiled_df by model_name and direction for standardized plotting
# compiled_df['direction'] = pd.Categorical(compiled_df['direction'])
compiled_df = compiled_df.sort_values(by=['model_name', 'direction', 'threshold'])

# Filter to max_k = 30
compiled_df = compiled_df[compiled_df['max_k'] == 30]

#%% Analyze feasibility metric
# Valid fractions
cols = ['model_name', 'direction', 'threshold', 'is_valid']
# Feasibility metric: the number of times the solution is feasible and is integer
valid_fraction = compiled_df[cols].groupby(
    ['model_name', 'direction', 'threshold'],
    observed = False
    )['is_valid'].mean().reset_index()

# Create a grid of subplots for each unique value in the 'direction' column
g = sns.FacetGrid(valid_fraction, col = "direction", row = 'model_name')
g = g.map(
    sns.lineplot,
    'threshold', 'is_valid', 'direction',
    # order = ['both', 'up', 'adaptive'],
    linewidth = 2.5
    )

g.set_titles(col_template="{col_name}", row_template="{row_name}")
g.set_axis_labels('Rounding threshold', 'Valid fraction')
for ax in g.axes.flatten():
    ax.axhline(1, ls='--', color='k', label=['1.0x'])
plt.show()


#%% Determine reason for infeasibility
infeasi_count_df = compiled_df.loc[~compiled_df['is_valid']].copy()
infeasi_count_df['infeasibility_reason'] = None
infeasi_count_df.loc[~infeasi_count_df['rounding_is_int'], 'infeasibility_reason'] = 'Not integer'
infeasi_count_df.loc[~infeasi_count_df['rounding_is_feasible'], 'infeasibility_reason'] = 'Rounding infeasible'
infeasi_count_df.loc[~infeasi_count_df['rounding_is_int'] & ~infeasi_count_df['rounding_is_feasible'], 'infeasibility_reason'] = 'Both'
infeasi_count_df['infeasibility_reason'] = pd.Categorical(infeasi_count_df['infeasibility_reason'])

infeasi_count_df = infeasi_count_df.groupby(
    ['model_name', 'direction', 'threshold', 'infeasibility_reason'], observed = False
)['infeasibility_reason'].count().reset_index(name='count')


g = sns.FacetGrid(
    infeasi_count_df,
    col = 'direction',
    row = 'model_name',
    hue = 'infeasibility_reason'
    )
g = (
    g.map(
        sns.barplot,
        'threshold', 'count',
        order = [x/10 for x in range(1, 10)]
        ).add_legend()
        )
g.set_titles(col_template='{col_name}', row_template="{row_name}")
g.set_axis_labels('Rounding threshold', 'Infeasibility count')
plt.show()


#%% Plot the MIP gap
gap_df = compiled_df[compiled_df.is_valid].reset_index()

# Create a grid of subplots for each unique value in the 'direction' column
g = sns.FacetGrid(gap_df, col = "direction", row = 'model_name')
g = g.map(sns.lineplot, "threshold", "lp_mip_gap", "model_name", linewidth=2.5)

g.set_titles(col_template="{col_name}", row_template="{row_name}")
g.set_axis_labels('Rounding threshold', 'MIPGap (%)')
g.set(ylim=(0, 25))
plt.show()



#%% Plot the compute time gain
cols = ['model_name', 'direction', 'threshold', 'opt_xspeed', 'wall_clock_xspeed']
speed_df = compiled_df.loc[compiled_df.is_valid, cols].reset_index(drop=True)

# opt_time speed-up
g = sns.FacetGrid(speed_df, col = "direction", row = 'model_name')
g = g.map(sns.lineplot, "threshold", "opt_xspeed", "model_name", linewidth=2.5)

g.set_titles(col_template="{col_name}", row_template="{row_name}")
g.set_axis_labels('Rounding threshold', 'x(Opt.time)')
# Add horizontal lines at breakeven point of 1.0x
for ax in g.axes.flatten():
    ax.axhline(1, ls='--', color='k', label=['1.0x'])
plt.show()

# Wall clock speed-up
g = sns.FacetGrid(speed_df, col = "direction", row = 'model_name')
g = g.map(sns.lineplot, "threshold", "wall_clock_xspeed", "model_name", linewidth=2.5)

g.set_titles(col_template="{col_name}", row_template="{row_name}")
g.set_axis_labels('Rounding threshold', 'x(Wallclock)')
for ax in g.axes.flatten():
    ax.axhline(1, ls='--', color='k', label=['1.0x'])
plt.show()
plt.show()


#%% Create statistics
groupby_cols = ['model_name', 'direction', 'threshold']
# Mean speed-up
x_opt_time = compiled_df.groupby(groupby_cols)['opt_xspeed'].mean()
x_wallclock = compiled_df.groupby(groupby_cols)['wall_clock_xspeed'].mean()

# Mean MIPGap
mean_mipgap = compiled_df.groupby(groupby_cols)['lp_mip_gap'].mean()

# Print the average feasibility
mean_feasibility = compiled_df.groupby(groupby_cols)['is_valid'].mean()



#%% Plot histogram of k
compiled_df.groupby(
    ['model_name', 'direction']
    )['rounding_k'].hist(
        alpha = 0.4,
        legend=['both', 'up', 'adaptive']
        )