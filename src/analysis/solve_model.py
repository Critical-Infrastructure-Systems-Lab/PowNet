# Solves PowNet
import time
import os
import pickle as pkl

import pandas as pd
import matplotlib.pyplot as plt

from pydopt.preprocessing.functions import parse_instance
from pydopt.components.dw import dw_opt

# from pydopt.components.base_opt import gurobipyOptimizer as baseOpt
from pydopt.components.base_opt import pyomoOptimizer as baseOpt


MODEL_NAME = 'dummy'
MAXITER = 150
DW_TOL = 1e-5
PARSE_INSTANCE = True # Save the instance after parsing



if not os.path.exists('./results'):
    os.makedirs('./results')

cdir = os.getcwd()

path_mps = os.path.join(cdir, 'decom_files', f'{MODEL_NAME}.mps')
path_dec = os.path.join(cdir, 'decom_files', f'{MODEL_NAME}.dec')


#%% Parse the instance
st_parse = time.time()

fn = os.path.join(cdir, 'decom_files', f'{MODEL_NAME}.p')

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

# Format the type
col_df_o = col_df.copy()
col_df_o.loc[col_df_o.type == 'Continuous', 'type'] = 'C'
col_df_o.loc[col_df_o.type == 'Integer', 'type'] = 'I'

# Relax the integrality constraints
col_df.type = 'C'

et_parse = time.time()



#%% DW section
st_dw = time.time()

dw_obj, dw_x, master = dw_opt(
    c_df, A_df, b_df, ineq_df, col_df, subp_indices, col_indices, MAXITER, DW_TOL)

et_dw = time.time()

dw_z = dw_obj[-1]



#%% Normal opt section

st_n = time.time()

vanillaOpt = baseOpt.create_model(c_df, A_df, b_df, ineq_df, col_df, debug=False)
opt_soln = vanillaOpt.optimize()

true_z = opt_soln.objval
true_x = pd.DataFrame(opt_soln.X, index=A_df.columns)

et_n = time.time()




#%% Normal opt without relaxation
st_n_o = time.time()

vanillaOpt_o = baseOpt.create_model(c_df, A_df, b_df, ineq_df, col_df_o, debug=False)
opt_soln_o = vanillaOpt_o.optimize()

true_z_o = opt_soln_o.objval
true_x_o = pd.DataFrame(opt_soln_o.X, index=A_df.columns)

et_n_o = time.time()




#%%

# Compare the solution of DW to that of Gurobi
dw_x.columns = ['value_dw']
true_x.columns = ['value_true']
true_x_o.columns = ['value_original']

solutions = dw_x.join(true_x, how='left')
solutions = solutions.join(true_x_o, how='left')

solutions.to_csv(f'./results/{MODEL_NAME}_{MAXITER}_solutions.csv')



#%% 
fuel_vars = ['mwh', 'hydro', 'hydro_import']

# Info on the fuel type of each power plant
df = solutions.reset_index().copy()

# Load the DW solutions
# solutions = pd.read_csv('.\laos\compare_solutions.csv', header=0)
df.columns = ['varname', 'value_dw', 'value_true', 'value_original']

pattern_1 = r'(\w+)\((\w+)_(\d+)'
df[['vartype', 'name', 'hour']] = df.varname.str.extract(pattern_1)
df = df.drop('varname', axis=1)
df = df.astype({'hour':int})

# Subset only to VARS
df = df[df['vartype'].isin(fuel_vars)]
# Match with fueltype
df = df.merge(powerplants, how='left', on='name')


df = df[['value_dw', 'value_true', 'value_original','hour', 'typ']].groupby(['typ', 'hour']).sum()
df = df.reset_index()
df = df.pivot(columns=['hour'], index=['typ']).T



#%% Visualize DW results
xmax = len(dw_obj)

fig, ax = plt.subplots() #figsize=(10,10))
ax.plot(dw_obj, linewidth=2)
ax.hlines(
    y = true_z, 
    color='r', 
    xmin=0, xmax=xmax, 
    linewidth = 2,
    linestyle = (0, (1, 1)))

# Formating section
ax.set(xlabel='iteration', ylabel='LP objective value')
ax.set_xticks(ticks=range(xmax), minor=True)
ax.grid()
plt.legend(['Dantzig-Wolfe', 'Normal Opt'])
plt.savefig(f'./results/{MODEL_NAME}_{MAXITER}_dw.png', dpi=350)



#%% Print Stats
print('\n===== STATS =====')
print('Original objval: ', int(true_z_o))
print('Relaxed objval:  ', int(true_z))
print('DW objval*:      ', int(dw_z))
print(
      'Optimality gap (%): ',
      round(abs((true_z - dw_z) / max([true_z, dw_z]))*100, 2)
      )

print('DW Time (s):', round(et_dw - st_dw, 3))
print('Normal Time (s):', round(et_n - st_n, 3))
print('Normal Time as MIP (s):', round(et_n_o - st_n_o, 3))
print('Parse Time (s)', round(et_parse - st_parse, 3))


#%% Visualize the fuel mix

fig, ax = plt.subplots(figsize=(10,7))
df.plot.area(ax=ax)
ax.set_ylabel('Energy (mwh)')
ax.legend(bbox_to_anchor=(1.2, 0.55))
ax.tick_params(axis='x', labelrotation = 45)
plt.savefig(f'./results/{MODEL_NAME}_{MAXITER}_fuelmix.png', dpi=350)



