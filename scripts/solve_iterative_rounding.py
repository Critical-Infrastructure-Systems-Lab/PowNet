# Solves PowNet
import csv
from datetime import datetime
import os

import gurobipy as gp
import pandas as pd

from pownet.folder_sys import get_temp_dir, get_output_dir
from pypolp.functions import check_is_binary_from_model



SAVE_SOLUTIONS = True

'''
    MODEL_NAME = 'laos'
    MAX_K = 10
    ROUND_THRESHOLD = 0.3 # Try [0.3, 0.5] or None
    ADAPTIVE = False
    VERBOSE = True
    # We found that round down by itself does not work well.
    # Both is alright if doing static rounding
    ROUND_DIRECTION = 'both' # up, down, both
    
    # When doing adaptive rounding, we only round up and not both directions
'''

#################


# Gurobi MIPGAP
MIPGAP = 0.001
gp.setParam('OutputFlag', False)



def round_up_status(
        status_variable: gp.Var,
        threshold: float,
        verbose: bool
        ) -> None:
    if (status_variable.X >= threshold) and (status_variable.X != 1):
        status_variable.lb = 1
        status_variable.ub = 1
        if verbose:
            print(
                f'Iterative rounding: R-UP {status_variable.varname} from {status_variable.X}'
                )


def round_down_status(
        status_variable: gp.Var,
        threshold: float,
        verbose: bool
        ) -> None:
    if (status_variable.X < threshold) and (status_variable.X != 0):
        status_variable.lb = 0
        status_variable.ub = 0
        if verbose:
            print(
                f'Iterative rounding: R-DOWN {status_variable.varname} from {status_variable.X}')


def round_static(
        variables: list[gp.Var],
        direction: str,
        threshold: float,
        verbose: bool
        ) -> None:
    for variable in variables:
        if direction == 'up':
            round_up_status(status_variable=variable, threshold=threshold, verbose=verbose)
        elif direction == 'down':
            round_down_status(status_variable=variable, threshold=threshold, verbose=verbose)
        elif direction == 'both':
            round_up_status(status_variable=variable, threshold=threshold, verbose=verbose)
            round_down_status(status_variable=variable, threshold=threshold, verbose=verbose)
        else:
            raise ValueError(f'Unknown rounding direction: {direction}')
            
        
def round_adaptive(
        model: gp.Model,
        non_binary_df: pd.DataFrame,
        threshold: float,
        verbose: bool
        ) -> None:
    ''' Round up only the largest status variables when they are larger than
    the threshold.
    '''
    # Find the largest variable
    max_value = non_binary_df['value'].max()
    max_varnames = non_binary_df.loc[non_binary_df['value'] == max_value, 'name']
    for max_varname in max_varnames:
        max_var = model.getVarByName(max_varname)
        round_up_status(
            status_variable = max_var,
            threshold = threshold,
            verbose = verbose
            )
        
        
#################
def run_experiment(
        model_name: str,
        max_k: int,
        round_direction: str,
        round_threshold: float,
        adaptive: bool,
        verbose: bool
        ) -> None:
    ctime = datetime.now().strftime("%Y%m%d_%H%M")
    
    session_name = f'{ctime}_rounding_{model_name}_{round_direction}_{round_threshold}_{adaptive}'
    
    
    rounding_folder = os.path.join(get_temp_dir(), 'rounding_stats')
    if not os.path.exists(rounding_folder):
        os.mkdir(os.path.join(rounding_folder))
        
    
    print(f'\n\nCollecting stats for {session_name}...')
    start_time = datetime.now()
    
    instance_folder = os.path.join(get_output_dir(), f'{model_name}_instances')
    num_instances = len(os.listdir(instance_folder)) - 1
    
    # Record the stats
    FIELDS = [
        'iter_rounding_k',
        'iter_rounding_objval',
        'iter_rounding_opt_time',
        'wall_clock_rounding',
        'iter_rounding_feasible',
        'rounding_is_int',
        'mip_objval',
        'mip_opt_time',
        'wall_clock_mip'
        ]
    
    csv_name = os.path.join(rounding_folder, f'{session_name}.csv')
    with open(csv_name, 'w', newline='', encoding='utf-8') as csvfile:  
        # creating a csv writer object  
        csvwriter = csv.writer(csvfile)  
        # writing the fields  
        csvwriter.writerow(FIELDS)
    
    # Days are labeled from k = 0 to k = 364
    for k in range(num_instances):
        
        #----- Solve with Gurobi as LP and recover int by rounding
        print(f'\n\nIterative rounding: === Solving Day {k} ===')
        path_mps = os.path.join(instance_folder, f'{model_name}_{k}.mps')
    
        wall_clock_rounding_start = datetime.now()
        gp_model = gp.read(path_mps)
        gp_model = gp_model.relax()
        
        # gp_model.setParam('outputflag', True)
    
        opt_time_rounding = 0
        is_int = False
        kk = 0
        current_non_binary_status = None
        
        while (not is_int) and (kk <= max_k):
            gp_model.optimize()
            
            opt_time_rounding += gp_model.runtime
            kk += 1
    
            # The tight formulation of thermal units should ensure they recover start/shut as int
            is_int, non_binary_status = check_is_binary_from_model(
            model = gp_model,
            target_varnames = ['status'],
            return_non_binary = True
            )
            
            # Fixing model variables can cause infeasibility
            if gp_model.status == 2:
                iter_rounding_objval = gp_model.objval
                is_feasible = True
            elif gp_model.status == 3: 
                # Here, model is not optimal
                iter_rounding_objval = None
                is_feasible = False
                break
            
            # If there is no improvement from rounding, then stop
            if current_non_binary_status == non_binary_status.shape[0]:
                break
            else:
                current_non_binary_status = non_binary_status.shape[0]
    
            # Do round-up when status >= ROUND_THRESHOLD
            if verbose:
                print(f'\nIterative rounding: Iteration: {kk}')
            
            variables = [v for v in gp_model.getVars() if 'status' in v.varname]
            
            if adaptive:
                round_adaptive(
                    gp_model,
                    non_binary_status,
                    threshold = round_threshold,
                    verbose = verbose
                    )
            else:
                round_static(
                    variables, 
                    direction = round_direction,
                    threshold = round_threshold,
                    verbose = verbose
                    )
                        
        wall_clock_rounding_start = (datetime.now() - wall_clock_rounding_start).total_seconds()
        
        # Check that we have recovered binary solution
        solution = pd.DataFrame(
            {
                'name': gp_model.getAttr('varname'),
                'value': gp_model.getAttr('X')
                }
            )
        solution['vartype'] = solution['name'].str.split('[', expand=True)[0]
        solution = solution[solution['vartype'].isin(['status', 'start', 'shut'])]
        
        # Check that the variables are indeed binary
        non_binary = solution[(solution['value'] > 0) & (solution['value'] < 1)]
        is_int = (len(non_binary) == 0)
    
        
        #----- Solve with Gurobi as LP and recover int by rounding
        wall_clock_mip = datetime.now()
        mip_model = gp.read(path_mps)
        mip_model.setParam('outputflag', 0)
        mip_model.setParam('MIPGap', MIPGAP)
        mip_model.optimize()
        
        mip_opt_time = mip_model.runtime
        wall_clock_mip = (datetime.now() - wall_clock_mip).total_seconds()
        
    
        #----- Saving intermediate results
        with open(csv_name, 'a', newline='', encoding='utf-8') as csvfile:  
            # creating a csv writer object  
            csvwriter = csv.writer(csvfile)  
            csvwriter.writerow(
                [
                    kk, #iter_count_rounding
                    iter_rounding_objval, # iter_rounding_objval
                    opt_time_rounding, # iter_rounding_opt_time
                    wall_clock_rounding_start, # wall_clock_rounding
                    is_feasible, # iter_rounding_feasible
                    is_int, # rounding_is_int
                    mip_model.objval, # mip_objval
                    mip_opt_time, # mip_opt_time
                    wall_clock_mip, # wall_lock_mip
                    ]
                )
        
    print(f'\n\nCompleted {session_name}...')
    print(f'Total time taken = {datetime.now() - start_time}')


if __name__ == '__main__':
    
    model_name = 'laos'
    max_k = 10
    thresholds = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    
    static_rounds = list(
        zip(['both']*len(thresholds), thresholds, [False]*len(thresholds))
        )
    static_rounds.extend(
        list(
            zip(['up']*len(thresholds), thresholds, [False]*len(thresholds))
            )
        )
    
    adaptive_rounds = list(
        zip(['up']*len(thresholds), thresholds, [True]*len(thresholds))
        )
    
    for direction, threshold, adaptive in static_rounds:
        run_experiment(
                model_name = model_name,
                max_k = max_k,
                round_direction = direction,
                round_threshold = threshold,
                adaptive = False,
                verbose = True
                )
    
    for direction, threshold, adaptive in adaptive_rounds:
        run_experiment(
                model_name = model_name,
                max_k = max_k,
                round_direction = direction,
                round_threshold = threshold,
                adaptive = False,
                verbose = True
                )
        
        