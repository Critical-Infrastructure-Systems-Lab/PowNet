import os

import matplotlib.pyplot as plt
import pandas as pd


PDIR = os.path.dirname(os.getcwd())
TEMPDIR = os.path.join(PDIR, 'temp')
FILENAME = '20231016_1348_laos_dw_stats'



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

gp_times = pd.read_csv(
    f'..//temp//{FILENAME}.csv', 
    header = 0, 
    usecols = ['gurobi_time'])

# Plot the time
fig, ax = plt.subplots()
# dw_times.plot.bar(stacked=True, ax=ax)
dw_times.plot.area(stacked=True, linewidth=0, ax=ax)
ax.plot(gp_times, linewidth=1, color='black', label='Gurobi time')

ax.legend()
ax.set(xlabel='Day', ylabel='Time (s)')
# plt.savefig(
#     os.path.join(TEMPDIR, f'{FILENAME}_time.png'),
#     dpi = 350,
#     bbox_inches = 'tight'
#     )
plt.show()


# Plt the itercount
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




