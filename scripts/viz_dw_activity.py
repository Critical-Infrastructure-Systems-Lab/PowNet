''' This script parses the Dantzig-Wolfe log to perform analysis. Also, creates the activity plot.
'''
from collections import defaultdict
import math
import os
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


##--------- Read Log file
LOGFILE = 'log_20231002_3blocks.log'

MODE = 'DEBUG'

dir_wk = os.path.dirname(os.getcwd())
with open(os.path.join(dir_wk, 'temp', LOGFILE)) as f:
    lines = f.readlines()
    

##--------- Initialization
iternum = 1

pattern_iter = r'.*ITER\s(?P<ii>\d+)'
pattern_B = r'B\((?P<j>\d+),(?P<i>\d+)\)'
pattern_phase = r'Entering\sPhase\s(?P<phase_1_iter>\d+)'

pattern_master = r'Solving master'
pattern_subp_id = r'Solving Subp:\s+(?P<subp_id>\d+)' # match
pattern_opt_stats = r'Solved in (?P<n_iter>\d+) iterations and (?P<solve_time>.*) seconds \((?P<work_units>\d+)\.'
pattern_optval = r'Optimal objective  (?P<objval>.*)'

activity_record = defaultdict(list)

simplex_record = defaultdict(list)
time_record = defaultdict(list)
work_unit_record = defaultdict(list)
optval_record = defaultdict(list)

##--------- Extract the text
# Extract the contributing subproblems at each iteration
section = 'subproblem' # either 'master' or 'subproblem'
subp_id = False

for line in lines:
    
    match_iter = re.search(pattern_iter, line)
    match_B = re.search(pattern_B, line)
    match_phase = re.search(pattern_phase, line)
    
    match_master = re.search(pattern_master, line)
    match_subp_id = re.search(pattern_subp_id, line)
    match_opt_stats = re.search(pattern_opt_stats, line)
    match_optval = re.search(pattern_optval, line)
    
    if match_iter is not None:
        ii = int(match_iter.group('ii'))
    
    if match_B is not None:
        j = int(match_B.group('j'))
        i = int(match_B.group('i'))
        # Keys are the subproblem ids
        # The indexing of subproblem starts at zero
        activity_record[j+1].append(i)

    if match_phase is not None:
        phase_1_iter = ii
    
    # Determine which section it is
    if match_subp_id is not None:
        subp_id = int(match_subp_id.group('subp_id')) + 1
        section = 'subproblem'
    
    if (match_opt_stats is not None) and (section == 'subproblem'):
        simplex_record[subp_id].append(
            int(match_opt_stats.group('n_iter')))
        
        time_record[subp_id].append(
            float(match_opt_stats.group('solve_time')))
        
        work_unit_record[subp_id].append(
            int(match_opt_stats.group('work_units')))

    if (match_optval is not None) and (section == 'subproblem'):
        optval_record[subp_id].append(
            float(match_optval.group('objval')))
    

    # Extract the master problem info
    if match_master is not None:
        section = 'master'
    
    if (match_opt_stats is not None) and (section == 'master'):
        simplex_record['master'].append(
            int(match_opt_stats.group('n_iter')))
        
        time_record['master'].append(
            float(match_opt_stats.group('solve_time')))
        
        work_unit_record['master'].append(
            int(match_opt_stats.group('work_units')))

    if (match_optval is not None) and (section == 'master'):
        optval_record['master'].append(
            float(match_optval.group('objval')))



##--------- Convert the result to a dataframe
ii_range = range(ii + 1) # number of dw iterations. Indexing starts at zero
subp_id_max = max(activity_record.keys())
subp_id_range = range(1, subp_id_max)

# Optimization stats
# Rows are # of dw iterations. Columnss are subp_id
simplex_df = pd.DataFrame.from_dict(simplex_record, orient='index').T
# simplex_df = simplex_df.fillna(value=np.nan)

time_df = pd.DataFrame.from_dict(time_record, orient='index').T
# time_df = time_df.fillna(value=np.nan)

# Activity of the subproblems
activity_df = pd.DataFrame(0, index=ii_range, columns=subp_id_range)
for subp_id in activity_record.keys():
    for row_id in activity_record[subp_id]:
        activity_df.loc[row_id, subp_id] = 1
        

##--------- Plotting
# Create an activity plot
fig, ax = plt.subplots(figsize=(13,50), dpi=350)
ax.spy(
       activity_df.T, markersize=1
       )
ax.vlines(phase_1_iter, ymin=0, ymax=subp_id_max, colors='r')
ax.set_xlabel('Iteration')
ax.xaxis.set_label_position('top')
ax.set_ylabel('Subproblem ID')

labels = [item.get_text() for item in ax.get_yticklabels()]
labels[1:] = activity_df.columns
ax.set_yticklabels(labels)

plt.show()



def plot_boxplot(subset_df, ax, subplot_name, value_name):
    ax.boxplot(x = subset_df.values)
    # Numbering of subproblems start at one
    ax.set_title(subplot_name)
    ax.set_ylabel(value_name)
    
    
def get_boxplots(df, subp_id_max, value_name, fig_title):
    fig, axes = plt.subplots(
        math.ceil((subp_id_max+1)/4), 4, 
        dpi=350, 
        layout="constrained")
    for ax_id, ax in enumerate(axes.flat):
        subp_id = ax_id+1
        if subp_id <= subp_id_max:
            subset_df = df.loc[:, subp_id].dropna()
            subplot_name = f'Subp {ax_id+1}'
            plot_boxplot(subset_df, ax, subplot_name, value_name)
        elif subp_id == subp_id_max+1:
            subset_df = df.loc[:, 'master'].dropna()
            subplot_name = 'Master'
            plot_boxplot(subset_df, ax, subplot_name, value_name)
        else:
            ax.set_visible(False)
            
    fig.suptitle(fig_title, fontsize=16)
    plt.show()
            
    
if MODE == 'DEBUG':

    get_boxplots(
        df=simplex_df, 
        subp_id_max=subp_id_max, 
        value_name='Iterations',
        fig_title='Number of Simplex Iterations')

    get_boxplots(
        df=time_df, 
        subp_id_max=subp_id_max, 
        value_name='Time (s)',
        fig_title='Solve time')



##--------- Analysis
# Count the number of data points belonging to each subproblem
count_dict = {} # total
count_dict_1 = {} # Phase 1
count_dict_2 = {} # Phase 2

for subp_id in range(1, subp_id_max+1):
    count_dict[subp_id] = len(activity_record[subp_id])
    count_dict_1[subp_id] = sum(k < phase_1_iter for k in activity_record[subp_id])
    count_dict_2[subp_id] = sum(k >= phase_1_iter for k in activity_record[subp_id])

ranking = sorted(count_dict, key=count_dict.get, reverse=True)
ranking_1 = sorted(count_dict_1, key=count_dict_1.get, reverse=True)
ranking_2 = sorted(count_dict_2, key=count_dict_2.get, reverse=True)


print('\nThe top 5 active subproblems')
for k, subp_id in enumerate(ranking[:5]):
    num_pts = count_dict[subp_id]
    print(f'Subproblem #{subp_id} with {num_pts} extreme points')

print('\nThe top 5 active subproblems in Phase 1')
for k, subp_id in enumerate(ranking_1[:5]):
    num_pts = count_dict_1[subp_id]
    print(f'Subproblem #{subp_id} with {num_pts} extreme points')
    
print('\nThe top 5 active subproblems in Phase 2')
for k, subp_id in enumerate(ranking_2[:5]):
    num_pts = count_dict_2[subp_id]
    print(f'Subproblem #{subp_id} with {num_pts} extreme points')