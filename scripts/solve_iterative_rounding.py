# Solves PowNet
import csv
from datetime import datetime
import os

import gurobipy as gp
import pandas as pd

from pownet.folder_sys import get_temp_dir, get_output_dir
from pypolp.functions import check_is_binary_from_model



# Gurobi MIPGAP
MIPGAP = 0.001
gp.setParam('OutputFlag', False)



def round_up_status(
        variable: gp.Var,
        threshold: float,
        verbose: bool
        ) -> None:
    if (variable.X >= threshold) and (variable.X != 1):
        variable.lb = 1
        variable.ub = 1
        if verbose:
            print(f'Iterative rounding: R-UP {variable.varname} from {variable.X}')


def round_down_status(
        variable: gp.Var,
        threshold: float,
        verbose: bool
        ) -> None:
    if (variable.X < threshold) and (variable.X != 0):
        variable.lb = 0
        variable.ub = 0
        if verbose:
            print(f'Iterative rounding: R-DOWN {variable.varname} from {variable.X}')


def round_static(
        model: gp.Model,
        non_binary_var_df: pd.DataFrame,
        direction: str,
        threshold: float,
        verbose: bool
        ) -> None:
    for varname in non_binary_var_df.name:
        variable = model.getVarByName(varname)
        if direction == 'up':
            round_up_status(variable=variable, threshold=threshold, verbose=verbose)
        elif direction == 'down':
            round_down_status(variable=variable, threshold=threshold, verbose=verbose)
        elif direction == 'both':
            round_up_status(variable=variable, threshold=threshold, verbose=verbose)
            round_down_status(variable=variable, threshold=threshold, verbose=verbose)
        else:
            raise ValueError(f'Unknown rounding direction: {direction}')
            
        
def round_adaptive(
        model: gp.Model,
        non_binary_var_df: pd.DataFrame,
        threshold: float,
        verbose: bool
        ) -> None:
    ''' Round up only the largest status variables when they are larger than
    the threshold.
    '''
    # Find the largest variable
    max_value = non_binary_var_df['value'].max()
    max_varnames = non_binary_var_df.loc[non_binary_var_df['value'] == max_value, 'name']
    for max_varname in max_varnames:
        max_var = model.getVarByName(max_varname)
        round_up_status(
            variable = max_var,
            threshold = threshold,
            verbose = verbose
            )



def run_experiment(
        model_name: str,
        max_k: int,
        round_direction: str,
        round_threshold: float,
        verbose: bool,
        save_solution: bool = False
        ) -> None:
    
    # Define variables for naming the session
    ctime = datetime.now().strftime("%Y%m%d_%H%M")
    session_name = f'{ctime}_rounding_{model_name}_{round_direction}_{round_threshold}_{max_k}'
    
    # We will store the statistics of all sessions 
    # in a folder called 'rounding_stats'
    rounding_folder = os.path.join(get_temp_dir(), 'rounding_stats')
    if not os.path.exists(rounding_folder):
        os.mkdir(os.path.join(rounding_folder))
        
    print(f'\n\nStarting session {session_name}...')
    
    # Start the timer
    start_time = datetime.now()

    # Fields are headers in of our statistics csv file
    FIELDS = [
        'rounding_k',
        'rounding_objval',
        'rounding_opt_time',
        'wall_clock_rounding',
        'rounding_is_feasible',
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
    
    # Iterate over all instances
    instance_folder = os.path.join(get_output_dir(), f'{model_name}_instances')
    num_instances = len(os.listdir(instance_folder)) - 1
    # Days are labeled from k = 0 to k = 364
    for k in range(num_instances):
        #----- Solve with Gurobi as LP and recover int by rounding
        if verbose:
            print(f'\n\nIterative rounding: === Solving Day {k} ===')
        path_mps = os.path.join(instance_folder, f'{model_name}_{k}.mps')
        wall_clock_rounding_start = datetime.now()
        gp_model = gp.read(path_mps)
        gp_model = gp_model.relax()
    
        rounding_opt_time = 0
        is_int = False
        kk = 0
        # We will keep track of the non-binary variables from the previous iteration
        current_non_binary_variables = set()
        
        while (not is_int) and (kk <= max_k):
            if verbose:
                print(f'\nIterative rounding: Iteration: {kk}')
            # Solve the model and record the time
            gp_model.optimize()
            rounding_opt_time += gp_model.runtime
            kk += 1
    
            # The tight formulation of thermal units should recover start/shut as int
            # when rounding up the status variables. Hence, we only deal with
            # status variables here.
            rounding_is_int, non_binary_var_df = check_is_binary_from_model(
            model = gp_model,
            target_varnames = ['status'],
            return_non_binary = True
            )
            
            # Fixing model variables can cause infeasibility
            if gp_model.status == 2:
                rounding_objval = gp_model.objval
                rounding_is_feasible = True
            elif gp_model.status == 3: 
                # Here, model is not optimal
                rounding_objval = None
                rounding_is_feasible = False
                break
            
            # If there is no improvement from rounding, then stop
            non_binary_variables = set(non_binary_var_df['name'])
            if current_non_binary_variables == non_binary_variables:
                break
            else:
                current_non_binary_variables = non_binary_variables
    
            # Round the non-binary variables based on the direction
            if round_direction == 'adaptive':
                round_adaptive(
                    model = gp_model,
                    non_binary_var_df = non_binary_var_df,
                    threshold = round_threshold,
                    verbose = verbose
                    )
            else:
                round_static(
                    model = gp_model,
                    non_binary_var_df = non_binary_var_df,
                    direction = round_direction,
                    threshold = round_threshold,
                    verbose = verbose
                    )
        wall_clock_rounding_start = (datetime.now() - wall_clock_rounding_start).total_seconds()
                
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
                    kk, # rounding_k
                    rounding_objval, # rounding_objval
                    rounding_opt_time, # rounding_opt_time
                    wall_clock_rounding_start, # wall_clock_rounding
                    rounding_is_feasible, # rounding_is_feasible
                    rounding_is_int, # rounding_is_int
                    mip_model.objval, # mip_objval
                    mip_opt_time, # mip_opt_time
                    wall_clock_mip, # wall_lock_mip
                    ]
                )
        
    print(f'\n\nCompleted {session_name}...')
    print(f'Total time taken = {datetime.now() - start_time}')

    if save_solution:
        solution = pd.DataFrame(
            {
                'name': gp_model.getAttr('varname'),
                'value': gp_model.getAttr('X')
                }
            )
        solution['vartype'] = solution['name'].str.split('[', expand=True)[0]
        solution.to_csv(os.path.join(rounding_folder, f'{session_name}_X.csv'))


if __name__ == '__main__':
    
    model_name = 'laos'
    max_k = 100
    thresholds = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    verbose = True
    
    static_rounds = list(
        zip(['both']*len(thresholds), thresholds)
        )
    static_rounds.extend(
        list(
            zip(['up']*len(thresholds), thresholds)
            )
        )
    
    adaptive_rounds = list(
        zip(['adaptive']*len(thresholds), thresholds)
        )
    
    for direction, threshold in static_rounds:
        run_experiment(
                model_name = model_name,
                max_k = max_k,
                round_direction = direction,
                round_threshold = threshold,
                verbose = verbose
                )
    
    for direction, threshold in adaptive_rounds:
        run_experiment(
                model_name = model_name,
                max_k = max_k,
                round_direction = direction,
                round_threshold = threshold,
                verbose = verbose
                )
        
        