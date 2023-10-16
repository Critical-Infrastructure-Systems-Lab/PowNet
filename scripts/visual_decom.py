import os

import matplotlib.pyplot as plt
import mplcursors

from pypolp.tools.parser import parse_mps_dec




MODEL_NAME = 'laos_by_units'

# Get the A matrix as a dataframe

pdir = os.path.dirname(os.getcwd())
path_mps = os.path.join(pdir, 'temp', 'decom_files', f'{MODEL_NAME}.mps')
path_dec = os.path.join(pdir, 'temp', 'decom_files', f'{MODEL_NAME}.dec')
    
dw_problem = parse_mps_dec(path_mps, path_dec)

(
 c_df, A_df, b_df, ineq_df, col_df
 ) = dw_problem.get_dataframes()

subp_indices = dw_problem.row_indices
col_indices = dw_problem.col_indices

# Sort the constraints in order according to the .DEC file
fig, ax = plt.subplots(figsize=(7,7))
ax.spy(A_df, markersize=1)
ax.set_xlabel('Variable ID')
ax.set_ylabel('Constraint ID')

# Create a hover tool
cursor = mplcursors.cursor(ax, hover=True)
@cursor.connect("add")
def on_add(sel):
    constr_name = 'Constraint: ' + str(A_df.index[int(sel.target[1])])
    var_name = 'Variable: ' + str(A_df.columns[int(sel.target[0])])
    tt = constr_name + '\n' + var_name
    sel.annotation.get_bbox_patch().set(fc="white")
    sel.annotation.set(text=tt, fontsize=13, ha='left')

plt.savefig(
    os.path.join(pdir, 'temp', f'{MODEL_NAME}_structure.png'), dpi=350, bbox_inches='tight')
plt.show()