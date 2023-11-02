# Solves PowNet
from datetime import datetime
import os

import gurobipy as gp
import pandas as pd

from pypolp.dw.dw import DantzigWolfe, Record
from pypolp.tools.parser import parse_mps_with_orders, parse_mps, get_dataframe_orders



MODEL_NAME = 'cambodia'


CTIME = c_time = datetime.now().strftime("%Y%m%d_%H%M")
PDIR = os.path.dirname(os.getcwd())
instance_folder = os.path.join(PDIR, 'temp', f'{MODEL_NAME}_instances')
path_dec = os.path.join(instance_folder, f'{MODEL_NAME}.dec')


path_mps = os.path.join(instance_folder, f'{MODEL_NAME}_0.mps')
(
    _, A_df, _, _, col_df
    ) = parse_mps(path_mps)

row_order, col_order = get_dataframe_orders(path_dec, A_df, col_df)
del A_df
del col_df

master_times = []
master_itercounts = []

subp_times = []
subp_itercounts = []

gurobi_times = []

# The number of MPS files is the total number of instances.
# Note that we have one DEC file, so we need to subtract 1
num_instances = len(os.listdir(instance_folder)) - 1
for k in range(num_instances):
    print(f'\n\n=== Solving Day {k} ===')
    path_mps = os.path.join(instance_folder, f'{MODEL_NAME}_{k}.mps')

    dw_problem = parse_mps_with_orders(path_mps, row_order, col_order)
    record = Record()
    record.fit(dw_problem)
        
    dw_instance = DantzigWolfe()
    dw_instance.fit(dw_problem, record)
    dw_instance.solve(record)
    
    master_time, subp_time = dw_instance.get_stats('runtime')
    master_itercount, subp_itercount = dw_instance.get_stats('itercount')
    
    master_times.append(master_time)
    subp_times.append(subp_time)
    
    master_itercounts.append(master_itercount)
    subp_itercounts.append(subp_itercount)
    
    # Solve with Gurobi as the benchmark
    print('\n')
    gp_model = gp.read(path_mps)
    gp_model.setParam('outputflag', 0)
    gp_model.optimize()
    gurobi_times.append(gp_model.runtime)
    

# Create a dataframe and 
dw_stats = pd.DataFrame({
    'master_time': master_times,
    'master_iter': master_itercounts,
    'subp_time': subp_times,
    'subp_iter': subp_itercounts,
    'gurobi_time': gurobi_times
    })

dw_stats.to_csv(
    os.path.join(PDIR, 'temp', f'{CTIME}_{MODEL_NAME}_dw_stats.csv'),
    index = False
    )
