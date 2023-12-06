# Solves PowNet
import csv
from datetime import datetime
import os

import gurobipy as gp

from pownet.folder_sys import get_temp_dir, get_output_dir
from pypolp.dw.dw import DantzigWolfe, Record
from pypolp.tools.parser import parse_mps_with_orders, parse_mps, get_dataframe_orders
from pypolp.tools.functions import check_is_binary



MODEL_NAME = 'cambodia'
SAVE_SOLUTIONS = True
RECOVER_INT_FROM_DW = True

terminate_criterion = '_0d0001' # 0d0001 = 0.0001

############################
start_time_script = datetime.now()
CTIME = start_time_script.strftime("%Y%m%d_%H%M")

print(f'\n==== Begin collecting statistics for {MODEL_NAME} ====')

# Create a folder to save the outputs
save_folder = f'{CTIME}_{MODEL_NAME}_{terminate_criterion}'
save_folder = os.path.join(get_temp_dir(), save_folder)
if not os.path.exists(save_folder):
    os.makedirs(save_folder)

# Need to extract row/column orders to parse the DW structure
instance_folder = os.path.join(get_output_dir(), f'{MODEL_NAME}_instances')
path_dec = os.path.join(instance_folder, f'{MODEL_NAME}.dec')
path_mps = os.path.join(instance_folder, f'{MODEL_NAME}_0.mps')

(_, A_df, _, _, col_df) = parse_mps(path_mps)

row_order, col_order = get_dataframe_orders(path_dec, A_df, col_df)
del A_df
del col_df

# Collect statistics to compare computational performance
FIELDS = [
    'master_itercount',
    'master_time',
    'master_mip_time', # Time to optimize the last interation of master as integer
    'subp_itercount',
    'subp_time',
    'dw_itercount',
    'dw_time',
    'dw_mip_time',
    'dw_objval',
    'dw_mip_objval',
    'mip_gurobi_time',
    'mip_objval',
    'lp_gurobi_time',
    'lp_objval',
    'is_int', # Check if the lp solution is integer
    # Wall clock is the total time to build, solve, extract solution
    'wall_clock_dw',
    'wall_clock_mip_gurobi',
    'wall_clock_lp_gurobi'
    ]

# Create a csv file with only headers. We will append to this csv later.
csv_name = os.path.join(save_folder, f'{MODEL_NAME}_dw_stats.csv')
with open(csv_name, 'w', newline='', encoding='utf-8') as csvfile:  
    # creating a csv writer object  
    csvwriter = csv.writer(csvfile)  
    # writing the fields  
    csvwriter.writerow(FIELDS)

# The number of MPS files is the total number of instances.
# Note that we have one DEC file, so we need to subtract 1
num_instances = len(os.listdir(instance_folder)) - 1
# Days are labeled from k = 0 to k = 364
for k in range(num_instances):
    print(f'\n\n=== Solving Day {k} ===')
    path_mps = os.path.join(instance_folder, f'{MODEL_NAME}_{k}.mps')


    #----- Solve with Dantzig-Wolfe
    wall_clock_dw = datetime.now()
    dw_problem = parse_mps_with_orders(path_mps, row_order, col_order)
    record = Record()
    record.fit(dw_problem)
    
    dw_instance = DantzigWolfe()
    
    dw_instance.fit(dw_problem, record)
    dw_instance.solve(record)
    
    master_time, subp_time = dw_instance.get_stats('runtime')
    master_itercount, subp_itercount = dw_instance.get_stats('itercount')
    
    dw_objval, dw_solution = dw_instance.get_solution(record)
    dw_itercount = dw_instance.dw_iter
    
    wall_clock_dw = (datetime.now() - wall_clock_dw).total_seconds()
    dw_time = master_time + subp_time
    
    #----- Solve with Dantzig-Wolfe but recover integer solution
    # This step takes a very long time and is not possible large instances
    if RECOVER_INT_FROM_DW:
        dw_mip_objval, dw_solution_mip = dw_instance.get_solution(
            record, 
            recover_integer = True
            )
        master_mip_time = dw_instance.master_problem.model.runtime
        dw_mip_time = dw_time  + master_mip_time
    else:
        dw_mip_objval = None
        dw_solution_mip = None
        dw_mip_time = None

    
    #----- Solve with Gurobi as MIP
    print('\n')
    wall_clock_mip_gurobi = datetime.now()
    gp_model = gp.read(path_mps)
    gp_model.setParam('outputflag', 0)
    gp_model.optimize()
    
    mip_gurobi_time = gp_model.runtime
    mip_objval = gp_model.objval

    wall_clock_mip_gurobi =  (datetime.now() - wall_clock_mip_gurobi).total_seconds()


    #----- Solve with Gurobi as LP
    print('\n')
    wall_clock_lp_gurobi = datetime.now()
    
    gp_model = gp_model.relax()
    gp_model.setParam('LPWarmStart', 0)
    gp_model.optimize()

    lp_gurobi_time = gp_model.runtime
    lp_objval = gp_model.objval

    wall_clock_lp_gurobi = (datetime.now() - wall_clock_lp_gurobi).total_seconds()

    # Check if the LP is integer solution
    is_int, non_binary_vars = check_is_binary(
        model = gp_model,
        target_varnames = ['status', 'start', 'shut'],
        return_non_binary = True
        )
    
    
    #----- Saving intermediate results
    with open(csv_name, 'a', newline='', encoding='utf-8') as csvfile:  
        # creating a csv writer object  
        csvwriter = csv.writer(csvfile)  
        # writing the data rows
        csvwriter.writerow(
            [
                master_itercount,
                master_time,
                master_mip_time,
                subp_itercount,
                subp_time,
                dw_itercount,
                dw_time,
                dw_mip_time,
                dw_objval,
                dw_mip_objval,
                mip_gurobi_time,
                mip_objval,
                lp_gurobi_time,
                lp_objval,
                is_int,
                wall_clock_dw,
                wall_clock_mip_gurobi,
                wall_clock_lp_gurobi
                ]
            ) 

    # When the gap between MIP and LP is smaller than 1.5%, 
    # then save the non-binary variables
    mip_lp_gap = abs(mip_objval - lp_objval)/(mip_objval+.01)
    if mip_lp_gap <= 0.015 and SAVE_SOLUTIONS:
        fname = f'nonbin_{MODEL_NAME}_{k}.csv'
        print(f'Saving {fname}...')
        non_binary_vars.to_csv(os.path.join(save_folder, fname))

# Save solutions for future reference. Place them in a folder
print(f'\n\n==== Completed collecting compute statistics for {MODEL_NAME} ====')
print(f'Results saved to {save_folder}')
print(f'{"Total time to complete:":<20} {datetime.now()- start_time_script}')
