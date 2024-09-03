# %%
import os

import matplotlib.pyplot as plt

from pypolp.parser import parse_mps_dec
from pownet.folder_utils import get_output_dir


MODEL_NAME = "RegionAB"
SAVE_FIGURE = True

# %% Reorder the A matrix according to the .dec file
pdir = os.path.dirname(os.getcwd())
path_mps = os.path.join(
    get_output_dir(), f"{MODEL_NAME}_24_instances", f"{MODEL_NAME}_0.mps"
)
path_dec = os.path.join(
    get_output_dir(), f"{MODEL_NAME}_24_instances", f"{MODEL_NAME}.dec"
)

dw_problem = parse_mps_dec(path_mps, path_dec)

(c_df, A_df, b_df, ineq_df, col_df) = dw_problem.get_dataframes()

row_indices = dw_problem.row_indices
col_indices = dw_problem.col_indices


# %% Sort the constraints in order according to the .DEC file
fig, ax = plt.subplots(figsize=(7, 7))
ax.spy(
    A_df,
    markersize=1,
    color="black",  # tab:blue
    alpha=0.85,
    aspect="auto",
)

# Draw boundary lines of each subproblem
line_color = "tab:red"
line_color_master = "tab:orange"
linewidth = 2
linestyle = "solid"
for i in range(len(row_indices) - 1):
    ax.hlines(
        y=row_indices[i].start,
        xmin=col_indices[i].start,
        xmax=col_indices[i].end,
        color=line_color,
        linewidth=linewidth,
        linestyle=linestyle,
    )
    ax.hlines(
        y=row_indices[i].end,
        xmin=col_indices[i].start,
        xmax=col_indices[i].end,
        color=line_color,
        linewidth=linewidth,
        linestyle=linestyle,
    )
    ax.vlines(
        x=col_indices[i].start,
        ymin=row_indices[i].start,
        ymax=row_indices[i].end,
        color=line_color,
        linewidth=linewidth,
        linestyle=linestyle,
    )
    ax.vlines(
        x=col_indices[i].end,
        ymin=row_indices[i].start,
        ymax=row_indices[i].end,
        color=line_color,
        linewidth=linewidth,
        linestyle=linestyle,
    )

# Draw a box around the master problem
ax.hlines(
    y=row_indices[0].start,
    xmin=0,
    xmax=len(A_df.columns) - 1,
    color=line_color_master,
    linewidth=linewidth,
    linestyle=linestyle,
)
ax.hlines(
    y=1,
    xmin=0,
    xmax=A_df.shape[1] - 1,
    color=line_color_master,
    linewidth=linewidth,
    linestyle=linestyle,
)
ax.vlines(
    x=0,
    ymin=0,
    ymax=row_indices[0].start,
    color=line_color_master,
    linewidth=linewidth,
    linestyle=linestyle,
)
ax.vlines(
    x=len(A_df.columns) - 1,
    ymin=0,
    ymax=row_indices[0].start,
    color=line_color_master,
    linewidth=linewidth,
    linestyle=linestyle,
)

# x-ticks should be on the top
ax.xaxis.tick_top()
ax.set_xlabel("Variable ID")
ax.xaxis.set_label_position("top")
ax.set_ylabel("Constraint ID")


"""
# Create a hover tool
import mplcursors
cursor = mplcursors.cursor(ax, hover=True)

@cursor.connect("add")
def on_add(sel):
    constr_name = "Constraint: " + str(A_df.index[int(sel.target[1])])
    var_name = "Variable: " + str(A_df.columns[int(sel.target[0])])
    tt = constr_name + "\n" + var_name
    sel.annotation.get_bbox_patch().set(fc="white")
    sel.annotation.set(text=tt, fontsize=13, ha="left")
"""


if SAVE_FIGURE:
    fig.savefig(
        os.path.join(get_output_dir(), f"structure_{MODEL_NAME}.png"),
        dpi=350,
        bbox_inches="tight",
    )

plt.show()

# %%
