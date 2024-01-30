import os

import matplotlib.pyplot as plt
import mplcursors

from pypolp.parser import parse_mps_dec
from pownet.folder_sys import get_output_dir


MODEL_NAME = "cambodia"
SAVE_FIGURE = True

# Get the A matrix as a dataframe

pdir = os.path.dirname(os.getcwd())
path_mps = os.path.join(
    get_output_dir(), f"{MODEL_NAME}_instances", f"{MODEL_NAME}_0.mps"
)
path_dec = os.path.join(
    get_output_dir(), f"{MODEL_NAME}_instances", f"{MODEL_NAME}.dec"
)

dw_problem = parse_mps_dec(path_mps, path_dec)

(c_df, A_df, b_df, ineq_df, col_df) = dw_problem.get_dataframes()

subp_indices = dw_problem.row_indices
col_indices = dw_problem.col_indices

# Sort the constraints in order according to the .DEC file
fig, ax = plt.subplots(figsize=(7, 7))
ax.spy(A_df, markersize=1)
ax.set_xlabel("Variable ID")
ax.set_ylabel("Constraint ID")

# Create a hover tool
cursor = mplcursors.cursor(ax, hover=True)


@cursor.connect("add")
def on_add(sel):
    constr_name = "Constraint: " + str(A_df.index[int(sel.target[1])])
    var_name = "Variable: " + str(A_df.columns[int(sel.target[0])])
    tt = constr_name + "\n" + var_name
    sel.annotation.get_bbox_patch().set(fc="white")
    sel.annotation.set(text=tt, fontsize=13, ha="left")


if SAVE_FIGURE:
    fig.savefig(
        os.path.join(get_output_dir(), f"structure_{MODEL_NAME}.png"),
        dpi=350,
        bbox_inches="tight",
    )

plt.show()
