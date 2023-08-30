# Solves PowNet
import time
from datetime import datetime
import os
import pickle as pkl

import pandas as pd
import matplotlib.pyplot as plt

from pydopt.preprocessing.functions import parse_instance
from pydopt.core.dw import dw_opt

from pydopt.core.optim import gurobipyOptimizer as baseOpt
# from pydopt.core.pyo_optim import pyomoOptimizer as baseOpt


MODEL_NAME = 'dummy_trade'
MAXITER = 400
DW_TOL = 1e-5
PARSE_INSTANCE = True # Save the instance after parsing


# Get out of decomposition and src
pdir = os.path.dirname(os.getcwd())

path_mps = os.path.join(
    pdir, 'temp', 'decom_files', f'{MODEL_NAME}.mps')

path_dec = os.path.join(
    pdir, 'temp', 'decom_files', f'{MODEL_NAME}.dec')


#%% Parse the instance
t_start_parse = time.time()

fn = os.path.join(pdir, 'temp', 'decom_files', f'{MODEL_NAME}.p')

if PARSE_INSTANCE:
    (
     c_df, A_df, b_df, ineq_df,
     col_df, subp_indices, col_indices
     ) = parse_instance(path_mps, path_dec)

    with open(fn, 'wb') as f:
        pkl.dump(
            [c_df, A_df, b_df, ineq_df, col_df, subp_indices, col_indices],
            f)
else:
    with open(fn, 'rb') as f:
        (
         c_df, A_df, b_df, ineq_df, col_df,
         subp_indices, col_indices
         ) = pkl.load(f)

# The current DW implementation only supports LP
col_df_MIP = col_df.copy()
# Relax the integrality constraints
col_df.type = 'C'

t_end_parse = time.time()



#%% Solving with DW
t_start_dw = time.time()

dw_obj, dw_x, master = dw_opt(
    c_df, A_df, b_df, ineq_df, col_df, subp_indices, col_indices, MAXITER, DW_TOL)

t_end_dw = time.time()

dw_z = dw_obj[-1]



#%% Solving as LP

t_start_lp = time.time()

vanillaOpt = baseOpt.create_model(
    c_df, A_df, b_df, ineq_df, col_df, debug=True)

soln_lp = vanillaOpt.optimize()

z_lp = soln_lp.objval
x_lp = pd.DataFrame(soln_lp.X, index=A_df.columns)

t_end_lp = time.time()




#%% Solving as MIP
t_start_mip = time.time()

vanillaOpt_o = baseOpt.create_model(
    c_df, A_df, b_df, ineq_df, col_df_MIP, debug=True)

soln_mip = vanillaOpt_o.optimize()

z_mip = soln_mip.objval
x_mip = pd.DataFrame(soln_mip.X, index=A_df.columns)

t_end_mip = time.time()




#%%

# Compare the solution of DW to that of Gurobi
dw_x.columns = ['value_dw']
x_lp.columns = ['value_true']
x_mip.columns = ['value_original']

solutions = dw_x.join(x_lp, how='left')
solutions = solutions.join(x_mip, how='left')
 
c_time = datetime.now().strftime("%Y%m%d_%H%M")
solutions.to_csv(
    os.path.join(
        pdir, 'temp', 'decom_results'
        f'{c_time}_{MODEL_NAME}_{MAXITER}_solutions.csv'))


#%% Visualize DW results
xmax = len(dw_obj)

fig, ax = plt.subplots() #figsize=(10,10))
ax.plot(dw_obj, linewidth=2)
ax.hlines(
    y = z_lp, 
    color='r', 
    xmin=0, xmax=xmax, 
    linewidth = 2,
    linestyle = (0, (1, 1)))

# Formating section
ax.set(xlabel='iteration', ylabel='LP objective value')
ax.set_xticks(ticks=range(xmax), minor=True)
ax.grid()
plt.legend(['Dantzig-Wolfe', 'Normal Opt'])
plt.savefig(
    os.path.join(
        pdir, 'temp', 'decom_results',
        f'{c_time}_{MODEL_NAME}_{MAXITER}_dw.png'),
    dpi=350)



#%% Print Stats
print('\n===== STATS =====')
print('MIP objval: ', int(z_mip))
print('LP objval:  ', int(z_lp))
print('DW objval:  ', int(dw_z))
print(
      'Optimality gap (%): ',
      round(abs((z_mip - dw_z) / z_mip)*100, 2)
      )

print('DW Time (s):   ', round(t_end_dw - t_start_dw, 2))
print('LP Time (s):   ', round(t_end_lp - t_start_lp, 2))
print('MIP Time (s):  ', round(t_end_mip - t_start_mip, 2))
print('Parse Time (s) ', round(t_end_parse - t_start_parse, 2))



#%% Visualize the fuel mix
# TODO: Complete this section

