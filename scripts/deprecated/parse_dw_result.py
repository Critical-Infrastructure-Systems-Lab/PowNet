from collections import defaultdict
import os
import re

import matplotlib.pyplot as plt
import pandas as pd



LOGFILE = 'dw_log.log'

dir_wk = os.path.dirname(os.getcwd())
with open(os.path.join(dir_wk, 'temp', LOGFILE)) as f:
    lines = f.readlines()
    
    
iternum = 1

pattern_iter = r'.*ITER\s(?P<ii>\d+)'
pattern_B = r'B\((?P<j>\d+),(?P<i>\d+)\)'
pattern_phase = r'Entering\sPhase\s(?P<phase_1_iter>\d+)'

record = defaultdict(list)

# Extract the contributing subproblems at each iteration
for line in lines:
    
    match_iter = re.match(pattern_iter, line)
    match_B = re.search(pattern_B, line)
    match_phase = re.search(pattern_phase, line)
    
    if match_iter is not None:
        ii = int(match_iter.group('ii'))
    
    if match_B is not None:
        j = int(match_B.group('j'))
        i = int(match_B.group('i'))
        # Keys are the subproblem ids
        record[j].append(i)

    if match_phase is not None:
        phase_1_iter = ii

# Convert the result to a dataframe
ii_range = range(ii + 1)
subp_id_max = max(record.keys())
subp_id_range = range(subp_id_max + 1)

df = pd.DataFrame(0, index=ii_range, columns=subp_id_range)
for subp_id in record.keys():
    for row_id in record[subp_id]:
        df.loc[row_id, subp_id] = 1
        

# Plot the result
fig, ax = plt.subplots(figsize=(13,50), dpi=350)
ax.spy(df.values, markersize=1)
ax.hlines(phase_1_iter, 0, subp_id_max, colors='r')
ax.set_xlabel('Subproblem ID')
ax.xaxis.set_label_position('top')
ax.set_ylabel('Iteration')
plt.show()

# Count the number of data points belonging to each subproblem
count_dict = {} # total
count_dict_1 = {} # Phase 1
count_dict_2 = {} # Phase 2

for subp_id in subp_id_range:
    count_dict[subp_id] = len(record[subp_id])
    count_dict_1[subp_id] = sum(k < phase_1_iter for k in record[subp_id])
    count_dict_2[subp_id] = sum(k >= phase_1_iter for k in record[subp_id])

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
