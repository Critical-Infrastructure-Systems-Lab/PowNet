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

from pownet.folder_sys import get_temp_dir, get_output_dir
from functions import calc_percent_change


MODEL_NAME = 'laos'



#%% Read statistics from files and compile into a single dataframe
files = os.listdir(os.path.join(get_temp_dir(), 'rounding_stats'))
files = [f for f in files if MODEL_NAME in f]
files_both = [f for f in files if ('both' in f) and ('False' in f)]
files_up = [f for f in files if ('up' in f) and ('False' in f)]
files_adaptive = [f for f in files if 'True' in f]

# Read the files and compile into a single dataframe
compiled_df = pd.DataFrame()
capture_pat = r'.*_rounding_(\w+)_(\w+)_(.+).csv'
for file in files:
    # Extract information from file name
    match = re.search(capture_pat, file)
    model_name = match.group(1)
    direction = match.group(2)
    threshold = match.group(3)
    # Append filename info to dataframe
    subset = pd.read_csv(os.path.join(get_temp_dir(), 'rounding_stats', file))
    # Extract info from filename
    subset['model_name'] = model_name
    subset['direction'] = direction
    subset['threshold'] = threshold
    # Create new features
    subset['is_valid'] = subset['rounding_is_feasible'] & subset['rounding_is_int']
    subset['lp_mip_gap'] = calc_percent_change(subset['rounding_objval'], subset['mip_objval'])
    subset['opt_xspeed'] = subset['mip_opt_time'] / subset['rounding_opt_time']
    subset['wall_lock_xspeed'] = subset['wall_clock_mip'] / subset['wall_clock_rounding']
    subset['fraction_runtime'] = subset['rounding_opt_time']/ subset['wall_clock_rounding']

    # Append the new df to the master_df   
    compiled_df = pd.concat([compiled_df, subset], axis=0)

#%% Analyze feasibility metric
# Feasibility metric: the number of times the solution is feasible and is integer
valid_fraction = compiled_df.groupby(
    ['model_name', 'direction', 'threshold']
    )['is_valid'].mean()


# Plot the valid_fraction
valid_fraction_df = valid_fraction.reset_index()

# Create a grid of subplots for each unique value in the 'direction' column
g = sns.FacetGrid(valid_fraction_df, col="direction", col_wrap=3, height=4, aspect=1.5)
g = g.map(sns.lineplot, "threshold", "is_valid", "model_name", palette="tab10", linewidth=2.5)

g.add_legend()

plt.show()


#%% Plot the MIP gap
gap_df = compiled_df.groupby(
    ['model_name', 'direction', 'threshold']
)['lp_mip_gap'].mean().reset_index()

# Create a grid of subplots for each unique value in the 'direction' column
g = sns.FacetGrid(gap_df, col="direction", col_wrap=3, height=4, aspect=1.5)
g = g.map(sns.lineplot, "threshold", "lp_mip_gap", "model_name", palette="tab10", linewidth=2.5)
g.add_legend()
plt.show()

#%% Plot the computational time
speed_df = compiled_df.groupby(
    ['model_name', 'direction', 'threshold']
)['x_speed_up'].mean().reset_index()

# Create a grid of subplots for each unique value in the 'direction' column
g = sns.FacetGrid(speed_df, col="direction", col_wrap=3, height=4, aspect=1.5)
g = g.map(sns.lineplot, "threshold", "x_speed_up", "model_name", palette="tab10", linewidth=2.5)
g.add_legend()
plt.show()

#%% Print the statistics

# Print the average speed up
print('\nAverage speed up:')
print(speed_df.groupby(['model_name', 'direction'])['x_speed_up'].mean())

# Print the average MIP gap
print('\nAverage MIP gap:')
print(gap_df.groupby(['model_name', 'direction'])['lp_mip_gap'].mean())

# Print the average feasibility
print('\nAverage feasibility:')
print(valid_fraction_df.groupby(['model_name', 'direction'])['is_valid'].mean())


#%% What causes infeasibility?

infeasibility_df = compiled_df.loc[~compiled_df['is_valid']].copy()
infeasibility_df['infeasibility_reason'] = None
infeasibility_df.loc[~infeasibility_df['rounding_is_int'], 'infeasibility_reason'] = 'Not integer'
infeasibility_df.loc[~infeasibility_df['rounding_is_feasible'], 'infeasibility_reason'] = 'Not feasible'
infeasibility_df.loc[~infeasibility_df['rounding_is_int'] & ~infeasibility_df['rounding_is_feasible'], 'infeasibility_reason'] = 'Both'

infeasibility_df = infeasibility_df.groupby(
    ['model_name', 'direction', 'threshold', 'infeasibility_reason']
)['infeasibility_reason'].count().reset_index(name='count'
)
pivot_df = infeasibility_df.pivot_table(index=['threshold', 'direction'], columns='infeasibility_reason', values='count', fill_value=0)

melt_df = pivot_df.reset_index().melt(id_vars=['threshold', 'direction'], var_name='infeasibility_reason', value_name='count')

# Create a FacetGrid
g = sns.FacetGrid(melt_df, col='direction', height=6, aspect=1)

# Map the barplot to each subplot
g.map(sns.barplot, 'threshold', 'count', 'infeasibility_reason', palette='deep', ci=None)

# Add a legend
g.add_legend()

# Show the plot
plt.show()
#%% Plot histogram of k
compiled_df.groupby(
    ['model_name', 'direction']
    )['rounding_k'].hist(legend=['both', 'up', 'adaptive'])