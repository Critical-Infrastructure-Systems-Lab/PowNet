# Solves PowNet
from datetime import datetime
import os

import gurobipy as gp
import pandas as pd

from pypolp.dw.dw import DantzigWolfe, Record
from pypolp.tools.parser import parse_mps_with_orders, parse_mps, get_dataframe_orders
from pypolp.tools.functions import check_is_binary


MODEL_NAME = 'laos'


CTIME = c_time = datetime.now().strftime("%Y%m%d_%H%M")
PDIR = os.path.dirname(os.getcwd())
instance_folder = os.path.join(PDIR, 'outputs', f'{MODEL_NAME}_instances')
path_dec = os.path.join(instance_folder, f'{MODEL_NAME}.dec')


path_mps = os.path.join(instance_folder, f'{MODEL_NAME}_0.mps')
(
    _, A_df, _, _, col_df
    ) = parse_mps(path_mps)

row_order, col_order = get_dataframe_orders(path_dec, A_df, col_df)
del A_df
del col_df

master_times = []
master_mip_times = []
master_itercounts = []

subp_times = []
subp_itercounts = []

lp_gurobi_times = []
mip_gurobi_times = []

dw_objvals = []
dw_mip_objvals = []
lp_objvals = []
mip_objvals = []

lp_is_int_solution = []

# The number of MPS files is the total number of instances.
# Note that we have one DEC file, so we need to subtract 1
num_instances = len(os.listdir(instance_folder)) - 1
for k in range(num_instances):
    print(f'\n\n=== Solving Day {k} ===')
    path_mps = os.path.join(instance_folder, f'{MODEL_NAME}_{k}.mps')


    # Solve with Dantzig-Wolfe
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
    
    dw_objval, dw_solution = dw_instance.get_solution(record)
    dw_objvals.append(dw_objval)
    
    
    # Solve with Gurobi as MIP
    print('\n')
    gp_model = gp.read(path_mps)
    gp_model.setParam('outputflag', 0)
    gp_model.optimize()
    
    mip_gurobi_times.append(gp_model.runtime)
    
    mip_objval = gp_model.objval
    mip_objvals.append(mip_objval)
    
    
    # Solve with Gurobi as LP
    gp_model = gp_model.relax()
    gp_model.setParam('LPWarmStart', 0)
    gp_model.optimize()
    
    lp_gurobi_times.append(gp_model.runtime)
    
    lp_objval = gp_model.objval
    lp_objvals.append(lp_objval)
    
    # Check if the LP is integer solution
    lp_is_int_solution.append(
        check_is_binary(
            model = gp_model, 
            target_varnames = ['status', 'start', 'shut']
            )
        )
    
    # If the last iteration 
    dw_mip_objval, dw_solution_mip = dw_instance.get_solution(
        record, 
        recover_integer = True
        )
    dw_mip_objvals.append(dw_mip_objval)
    master_mip_times.append(dw_instance.master_problem.model.runtime)
    
    

# Create a dataframe and 
dw_times = [x+y for x,y in zip(master_times, subp_times)]
dw_stats = pd.DataFrame({
    'master_times': master_times,
    'master_mip_times': master_mip_times,
    'master_iters': master_itercounts,
    'subp_times': subp_times,
    'subp_iters': subp_itercounts,
    'dw_times': dw_times,
    'lp_gurobi_times': lp_gurobi_times,
    'mip_gurobi_times': mip_gurobi_times,
    'mip_objvals': mip_objvals,
    'dw_mip_objvals': dw_mip_objvals,
    'dw_objvals': dw_objvals,
    'lp_objvals': lp_objvals,
    'int_solution': lp_is_int_solution
    })

dw_stats.to_csv(
    os.path.join(PDIR, 'temp', f'{CTIME}_{MODEL_NAME}_dw_stats.csv'),
    index = False
    )
