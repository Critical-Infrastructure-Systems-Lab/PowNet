import os

import pandas as pd
import matplotlib.pyplot as plt
import mplcursors

from pydopt.preprocessing.functions import parse_instance




MODEL_NAME = 'power_system'

# Get the A matrix as a dataframe

pdir = os.path.dirname(os.getcwd())
path_mps = os.path.join(pdir, 'temp', 'decom_files', f'{MODEL_NAME}.mps')
path_dec = os.path.join(pdir, 'temp', 'decom_files', f'{MODEL_NAME}.dec')
    
(
 c_df, A_df, b_df, ineq_df,
 col_df, subp_indices, col_indices
 ) = parse_instance(path_mps, path_dec)

# Sort the constraints in order according to the .DEC file
fig, ax = plt.subplots(figsize=(4,7))
ax.spy(A_df, markersize=5)
ax.set_xlabel('Variable ID')
ax.set_ylabel('Constraint ID')

# Create a hover tool
cursor = mplcursors.cursor(ax, hover=True)
@cursor.connect("add")
def on_add(sel):
    constr_name = 'Constraint: ' + str(A_df.index[sel.target[1]])
    var_name = 'Variable: ' + str(A_df.columns[sel.target[0]])
    tt = constr_name + '\n' + var_name
    sel.annotation.get_bbox_patch().set(fc="white")
    sel.annotation.set(text=tt, fontsize=13, ha='left')
    
plt.show()