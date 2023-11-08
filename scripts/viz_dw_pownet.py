import os

from matplotlib.colors import LinearSegmentedColormap

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


PDIR = os.path.dirname(os.getcwd())
TEMPDIR = os.path.join(PDIR, 'temp')
FILENAME = '20231108_1357_cambodia_dw_stats'



#=================== Plotting

dw_times = pd.read_csv(
    os.path.join(TEMPDIR, f'{FILENAME}.csv'), 
    header = 0, 
    usecols = ['master_time', 'subp_time'])
dw_times.columns = ['Master time', 'Subproblem time']

dw_itercounts = pd.read_csv(
    f'..//temp//{FILENAME}.csv', 
    header = 0, 
    usecols = ['master_iter', 'subp_iter'])
dw_itercounts.columns = ['Master itercount', 'Subproblem itercount']

gp_times_lp = pd.read_csv(
    f'..//temp//{FILENAME}.csv', 
    header = 0, 
    usecols = ['gurobi_time_lp'])

gp_times_mip = pd.read_csv(
    f'..//temp//{FILENAME}.csv', 
    header = 0, 
    usecols = ['gurobi_time_mip'])

instances_as_lp = pd.read_csv(
    f'..//temp//{FILENAME}.csv', 
    header = 0, 
    usecols = ['int_solution'])



# Compare optimization time
fig, ax = plt.subplots()
# dw_times.plot.bar(stacked=True, ax=ax)
dw_times.plot.area(stacked=True, linewidth=0, ax=ax)
ax.plot(gp_times_lp, linewidth=2, color='black', label='LP Gurobi time')
ax.plot(gp_times_mip, linewidth=2, color='red', linestyle='dotted', label='MIP Gurobi time')
ax.legend()
ax.set(xlabel='Day', ylabel='Time (s)')
# plt.savefig(
#     os.path.join(TEMPDIR, f'{FILENAME}_time.png'),
#     dpi = 350,
#     bbox_inches = 'tight'
#     )
plt.show()



# Compare itercount
fig, ax = plt.subplots()
# dw_itercounts.plot.bar(stacked=True, ax=ax)
dw_itercounts.plot.area(stacked=True, linewidth=0, ax=ax)
ax.set(xlabel='Day', ylabel='Itercount')
# plt.savefig(
#     os.path.join(TEMPDIR, f'{FILENAME}_itercount.png'),
#     dpi = 350,
#     bbox_inches = 'tight'
#     )
plt.show()


# Visualize when an instance is solved as LP

colors = ["black", "lightgrey"] 
cmap = LinearSegmentedColormap.from_list('Custom', colors, len(colors))

plt.tight_layout()
fig, ax = plt.subplots()
sns.heatmap(
    instances_as_lp,
    cmap=cmap,
    ax=ax
    )
plt.ylabel('Day')
ax.get_xaxis().set_visible(False)

# Set the colorbar labels
colorbar = ax.collections[0].colorbar
colorbar.set_ticks([0.25, 0.75])
colorbar.set_ticklabels(['False', 'True'])


# Fraction of days solved as LP
print('\nFraction as LP:', round(sum(instances_as_lp)/ 365, 0))

