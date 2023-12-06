# Solves PowNet
from datetime import datetime
import copy
import math
import os
import pickle as pkl
import time

import pandas as pd
import matplotlib.pyplot as plt

from pypolp.dw.dw import DantzigWolfe, Record
from pypolp.optim import GurobipyOptimizer
from pypolp.tools.parser import parse_mps_dec


MODEL_NAME = 'laos'
PARSE_INSTANCE = True # Save the instance after
SAVE_FIGURE = True
SAVE_RESULT = False
DW_FUELPLOT = False
DW_BOXPLOTS = False


# Get out of decomposition and src
c_time = datetime.now().strftime("%Y%m%d_%H%M")
PDIR = os.path.dirname(os.getcwd())

instance_folder = os.path.join(PDIR, 'outputs', f'{MODEL_NAME}_instances')
path_dec = os.path.join(instance_folder, f'{MODEL_NAME}.dec')
path_mps = os.path.join(instance_folder, f'{MODEL_NAME}_0.mps')



#%% Parse the instance
t_start_parse = time.time()
fn = os.path.join(PDIR, 'temp', 'decom_files', f'{MODEL_NAME}.p')
if PARSE_INSTANCE:
    dw_problem = parse_mps_dec(path_mps, path_dec)
    # with open(fn, 'wb') as f:
    #     pkl.dump(dw_problem, f)
else:
    with open(fn, 'rb') as f:
        dw_problem = pkl.load(f)
t_end_parse = time.time()

# The current DW implementation only supports LP
dw_problem_lp = copy.deepcopy(dw_problem)
# Relax the integrality constraints
dw_problem_lp.var_info.type = 'C'

opt_problem = dw_problem.get_opt_problem()
opt_problem_lp = dw_problem_lp.get_opt_problem()


#%% Solving with DW
t_start_dw = time.time()

record = Record()
record.fit(dw_problem)
    
dw_instance = DantzigWolfe()
dw_instance.fit(dw_problem, record)
dw_instance.solve(record)

dw_objval, dw_solution = dw_instance.get_solution(record)

t_end_dw = time.time()


#%% Solving with DW as MIP

dw_objval_mip, dw_solution_mip = dw_instance.get_solution(record, recover_integer=True)


#%% Solve the LP
print('\n=== Benchmark: Solve as LP ===\n')
t_start_lp = time.time()

base_opt = GurobipyOptimizer.create(opt_problem_lp, to_log=True)
_ = base_opt.optimize()

lp_objval = base_opt.objval
lp_solution = base_opt.get_X()
lp_solution = lp_solution.set_index('variable')

t_end_lp = time.time()



#%% Solving as MIP
print('\n=== Benchmark: Solve as MIP ===\n')

t_start_mip = time.time()

base_opt_mip = GurobipyOptimizer.create(opt_problem, to_log=True)
_ = base_opt_mip.optimize()

mip_objval = base_opt_mip.objval
mip_solution = base_opt_mip.get_X()
mip_solution = base_opt_mip.get_X().set_index('variable')

t_end_mip = time.time()


#%%

# Compare the solution of DW to that of Gurobi
if SAVE_RESULT:
    dw_solution.columns = ['DW']
    lp_solution.columns = ['LP']
    mip_solution.columns = ['MIP']
    
    solutions = dw_solution.join(lp_solution, how='left')
    solutions = solutions.join(mip_solution, how='left')
     
    solutions.to_csv(
        os.path.join(
            PDIR, 'temp', 'decom_results', 
            f'{c_time}_{MODEL_NAME}_solutions.csv'))


#%% Visualize DW results
if DW_FUELPLOT:
    xmax = len(record.primal_objvals)
    fig, ax = plt.subplots() #figsize=(10,10))
    ax.plot(record.primal_objvals, linewidth=2, label='Dantzig-Wolfe')
    ax.plot(record.dual_bounds, linewidth=2, label='DW Bound')
    ax.hlines(
        y = lp_objval, 
        color='r', 
        xmin=0, xmax=xmax, 
        linewidth = 2,
        linestyle = (0, (1, 1)),
        label = 'Gurobi')
    
    # Formating section
    ax.set(xlabel='Iteration', ylabel='Objective value')
    ax.set_xticks(ticks=range(xmax), minor=True)
    ax.grid()
    plt.legend()
    # plt.legend(['Dantzig-Wolfe', 'Normal Opt'])
    plt.savefig(
        os.path.join(
            PDIR, 'temp', 'decom_results',
            f'{c_time}_{MODEL_NAME}_dw.png'),
        dpi=350)



#%% Print Stats
master_time, subproblem_time = dw_instance.get_stats(mode='runtime')

print('\n===== STATS =====')
print(f'{"DW_MIP objval:":<20} {int(dw_objval_mip)}')
print(f'{"DW objval:":<20} {int(dw_objval)}')
print(f'{"LP objval:":<20} {int(lp_objval)}')
print(f'{"MIP objval:":<20} {int(mip_objval)}')

mip_dwmip_gap = round(abs((mip_objval - dw_objval_mip)/mip_objval+0.01)*100, 2)
print(f'\n{"MIP-DW_MIP gap (%):":<20} {mip_dwmip_gap}')

mip_dw_gap = round(abs((mip_objval - dw_objval)/mip_objval+0.01)*100, 2)
print(f'{"MIP-DW gap (%):":<20} {mip_dw_gap}')

mip_lp_gap = round(abs((mip_objval - lp_objval) / mip_objval+0.01)*100, 2)
print(f'{"MIP-LP gap (%):":<20} {mip_lp_gap}')

print(f'\n{"DW Structure Read Time (s):":<20} {round(t_end_parse - t_start_parse, 2)}')

print(f'\n{"Total DW Time (s):":<20} {round(t_end_dw - t_start_dw, 2)}')

print(f'{"Total LP Time (s):":<20} {round(t_end_lp - t_start_lp, 2)}')
print(f'{"Total MIP Time (s):":<20} {round(t_end_mip - t_start_mip, 2)}')

print(f'\n{"Opt time - Master Problem:":<30} {round(master_time, 5)} s')
print(f'{"Opt time - Subproblem:":<30} {round(subproblem_time, 5)} s')
print(f'{"Opt time - DW Total:":<30} {round(master_time+subproblem_time, 5)} s')
print(f'{"Opt time - LP Gurobi:":<30} {round(base_opt.runtime, 5)} s')
print(f'{"Opt time - MIP Gurobi:":<30} {round(base_opt_mip.runtime, 5)} s')


#%% Visualize the stats

dw_runtimes = dw_instance.get_runtimes_dict()
dw_itercounts = dw_instance.get_itercounts_dict()

def plot_boxplot(subset, ax, subplot_name, value_name) -> None:
    subset = pd.DataFrame(subset)
    ax.boxplot(x = subset.values)
    # Numbering of subproblems start at one
    ax.set_title(subplot_name)
    ax.set_ylabel(value_name)
    
    
def get_subplot_name(block_id: int | str) -> str:
    if type(block_id) == int:
        return f'Subp {block_id}'
    else:
        return 'Master'
    
    
def get_boxplots(stat_dict, value_name, fig_title):
    blocks = list(stat_dict.keys())
    fig, axes = plt.subplots(
        math.ceil(len(blocks)/4), 4,
        #figsize = (15, 15),
        dpi = 350, 
        layout = "constrained",
        )
    for ax_id, ax in enumerate(axes.flat):
        if ax_id < len(blocks):
            block_id = blocks[ax_id]
            subset = stat_dict[block_id]
            subplot_name = f'Block {block_id}'
            plot_boxplot(subset, ax, subplot_name, value_name)
        else:
            ax.set_visible(False)
    fig.suptitle(fig_title, fontsize=16)
    plt.savefig(
        os.path.join(
            PDIR, 'temp', 'decom_results', f'{c_time}_{MODEL_NAME}_{fig_title}.png'),
        dpi = 350
        )
    plt.show()
            
    
if DW_BOXPLOTS:
    get_boxplots(
        stat_dict = dw_runtimes, 
        value_name = 'Time (s)',
        fig_title = 'Optimization time'
        )
    get_boxplots(
        stat_dict = dw_itercounts, 
        value_name = 'Number',
        fig_title = 'Iteration count'
        )


