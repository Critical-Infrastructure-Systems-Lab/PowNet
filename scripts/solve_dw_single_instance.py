""" 
This script solves a single instance of PowNet with
Dantzig-Wolfe decomposition. The DW implementation can be
explored in detail.
"""

# %% Imports
import copy
import datetime as dt
import math
import os
import pickle as pkl

import pandas as pd
import matplotlib.pyplot as plt

from pypolp.dw.dw import DantzigWolfe
from pypolp.dw.record import DWRecord
from pypolp.optim import GurobipyOptimizer
from pypolp.parser import parse_mps_dec
from pownet.folder_sys import get_temp_dir, get_output_dir

MODEL_NAME = "laos"
PARSE_INSTANCE = True  # Save the instance after


SAVE_RESULT = False
DW_BOXPLOTS = False
SAVE_FIGURE = False

RMPGAP = 50  # in percent
DW_IMPROVE = 100  # 1.0 # in percent

# Create a timestamp to save files
c_time = dt.datetime.now().strftime("%Y%m%d_%H%M")

# Locate the mps and dec files
instance_folder = os.path.join(get_output_dir(), f"{MODEL_NAME}_24_instances")
path_dec = os.path.join(instance_folder, f"{MODEL_NAME}.dec")
path_mps = os.path.join(instance_folder, f"{MODEL_NAME}_93.mps")


# %% Parse MPS and DEC files

# Parsing the DEC file is a slow process and should be avoided if the instance
# has been parsed. We can re-use the parsed output.
timer_parse_dec = dt.datetime.now()
fn = os.path.join(get_temp_dir(), f"{MODEL_NAME}.p")
if PARSE_INSTANCE:
    dw_problem = parse_mps_dec(path_mps, path_dec)
    # with open(fn, "wb") as f:
    #     pkl.dump(dw_problem, f)
else:
    with open(fn, "rb") as f:
        dw_problem = pkl.load(f)
timer_parse_dec = (dt.datetime.now() - timer_parse_dec).total_seconds()

# Create instances to solve with Gurobi
mip_problem = dw_problem.get_opt_problem()


# %% Solving with DW
print("\n=== Running experiment: Solve MIP with DW ===\n")
timer_dw = dt.datetime.now()

# Create a record to store the results
record = DWRecord()
record.fit(dw_problem)

# Create an instance of the Dantzig-Wolfe algorithm
dw_model = DantzigWolfe(dw_improve=DW_IMPROVE, dw_rmpgap=RMPGAP)
dw_model.fit(dw_problem, record)
dw_model.solve(record)

dw_objval_lp, dw_solution_lp = dw_model.get_solution(record)

timer_dw = (dt.datetime.now() - timer_dw).total_seconds()

# Get statistics for analysis
master_time, subproblem_time = dw_model.get_stats(mode="runtime")


# Reoptimize the master problem using binary weights
timer_dw_binary = dt.datetime.now()
dw_model.reoptimize_with_binary_weights()
dw_objval_mip, dw_solution_mip = dw_model.get_solution(record)
timer_dw_binary = (dt.datetime.now() - timer_dw_binary).total_seconds()


# # Reoptimize the master problem using rounded weights
# timer_dw_binary = dt.datetime.now()
# try:
#     dw_model.reoptimize_with_rounded_weights()
#     dw_objval_mip, dw_solution_mip = dw_model.get_solution(record)
#     print("Reoptimized with rounded weights is INFEASIBLE.")
# except:
#     dw_objval_mip = None
#     dw_solution_mip = None

# timer_dw_binary = (dt.datetime.now() - timer_dw_binary).total_seconds()

# %% Solving as MIP
print("\n=== Running experiment: Solve MIP with Gurobi ===\n")

timer_mip = dt.datetime.now()

mip_model = GurobipyOptimizer.create(mip_problem)
_ = mip_model.optimize()

mip_objval = mip_model.objval
mip_solution = mip_model.get_X()
mip_solution = mip_model.get_X().set_index("variable")

timer_mip = (dt.datetime.now() - timer_mip).total_seconds()


# %% Solve the instance as LP with Gurobi
print("\n=== Running experiment: Solve with Gurobi as LP ===\n")
# Create instances when we are interested in exploring
# the LP problem
dw_relaxed_problem = copy.deepcopy(dw_problem)
dw_relaxed_problem.var_info.type = "C"
lp_problem = dw_relaxed_problem.get_opt_problem()

timer_lp = dt.datetime.now()

lp_model = GurobipyOptimizer.create(lp_problem)
_ = lp_model.optimize()

lp_objval = lp_model.objval
lp_solution = lp_model.get_X()
lp_solution = lp_solution.set_index("variable")

timer_lp = (dt.datetime.now() - timer_lp).total_seconds()


# %% Compare the solution of DW to that of Gurobi
if SAVE_RESULT:
    # Rename "value" to represent the solution approach
    dw_solution_mip.columns = ["DWMIP"]
    dw_solution_lp.columns = ["DWLP"]
    mip_solution.columns = ["MIP"]
    lp_solution.columns = ["LP"]

    solutions = dw_solution_mip.join(dw_solution_lp, how="left")
    solutions = solutions.join(mip_solution, how="left")
    solutions = solutions.join(lp_solution, how="left")

    solutions.to_csv(
        os.path.join(get_temp_dir(), f"{c_time}_{MODEL_NAME}_dw_compare_solutions.csv")
    )


# %% Visualize DW results
xmax = len(record.primal_objvals)
fig, ax = plt.subplots()  # figsize=(10,10))
ax.plot(record.primal_objvals, linewidth=2, label="Dantzig-Wolfe")
ax.plot(record.dual_bounds, linewidth=2, label="DW Bound")
ax.hlines(
    y=lp_objval,
    color="r",
    xmin=0,
    xmax=xmax,
    linewidth=2,
    linestyle=(0, (1, 1)),
    label="LP Objval",
)

# Formating section
ax.set(xlabel="Iteration", ylabel="Obj.Val")
ax.set_xticks(ticks=range(xmax), minor=True)
ax.grid()
plt.legend()
# plt.legend(['Dantzig-Wolfe', 'Normal Opt'])
if SAVE_FIGURE:
    plt.savefig(
        os.path.join(get_temp_dir(), f"{c_time}_{MODEL_NAME}_dw_objval_converge.png"),
        dpi=350,
    )


# %% Print Stats
print("\n===== Statistics =====")
print("\nObjvals:")
print(f'{"DWMIP objval:":<20} {int(dw_objval_mip)}')
print(f'{"MIP objval:":<20} {int(mip_objval)}')
print(f'{"DWLP objval:":<20} {int(dw_objval_lp)}')
print(f'{"LP objval:":<20} {int(lp_objval)}')

mip_dwmip_gap = round(abs((mip_objval - dw_objval_mip) / mip_objval + 0.01) * 100, 2)
print(f'{"MIP-DWMIP gap (%):":<20} {mip_dwmip_gap}')
print(f'{"RMPGap (%):":<20} {round(dw_model.rmpgap, 2)}')
print(f'{"Incre.Improve (%):":<20} {round(dw_model.incre_improve, 2)}')

print("\nDW Opt.time:")
dw_binary_time = dw_model.master_problem.model.Runtime
print(f'{"Opt.time - Master Problem:":<30} {round(master_time, 5)} s')
print(f'{"Opt.time - Subproblem:":<30} {round(subproblem_time, 5)} s')

print(f'{"Generating Proposals (s):":<30} {round(master_time + subproblem_time, 2)}')
print(f'{"Reoptimize with binary (s):":<30} {round(dw_binary_time, 2)}')
print(
    f'{"Total time (s):":<30} {round(master_time + subproblem_time + dw_binary_time, 2)}'
)
print(f'{"Opt.time - MIP Gurobi:":<30} {round(mip_model.runtime, 5)} s')
print(f'{"Opt.time - LP Gurobi:":<30} {round(lp_model.runtime, 5)} s')

print("\nDW Wall clock:")
print(f'{"Parsing DEC (s):":<30} {round(timer_parse_dec, 2)}')
print(f'{"Generating Proposals (s):":<30} {round(timer_dw, 2)}')
print(f'{"Reoptimize with binary (s):":<30} {round(timer_dw_binary, 2)}')
print(
    f'{"Total time (s):":<30} {round( timer_parse_dec+ timer_dw + timer_dw_binary, 2)}'
)
print(f'{"Total MIP Time (s):":<20} {round(timer_mip, 2)}')
print(f'{"Total LP Time (s):":<20} {round(timer_lp, 2)}')


# %% Visualize the stats

dw_runtimes = dw_model.get_runtimes_dict()
dw_itercounts = dw_model.get_itercounts_dict()


def plot_boxplot(subset, ax, subplot_name, value_name) -> None:
    subset = pd.DataFrame(subset)
    ax.boxplot(x=subset.values)
    # Numbering of subproblems start at one
    ax.set_title(subplot_name)
    ax.set_ylabel(value_name)


def get_subplot_name(block_id: int | str) -> str:
    if type(block_id) == int:
        return f"Subp {block_id}"
    else:
        return "Master"


def get_boxplots(
    stat_dict: dict, value_name: str, fig_title: str, save_figure: bool
) -> None:
    blocks = list(stat_dict.keys())
    fig, axes = plt.subplots(
        math.ceil(len(blocks) / 4),
        4,
        # figsize = (15, 15),
        dpi=350,
        layout="constrained",
    )
    for ax_id, ax in enumerate(axes.flat):
        if ax_id < len(blocks):
            block_id = blocks[ax_id]
            subset = stat_dict[block_id]
            subplot_name = f"Block {block_id}"
            plot_boxplot(subset, ax, subplot_name, value_name)
        else:
            ax.set_visible(False)
    fig.suptitle(fig_title, fontsize=16)
    if save_figure:
        plt.savefig(
            os.path.join(
                PDIR, "temp", "decom_results", f"{c_time}_{MODEL_NAME}_{fig_title}.png"
            ),
            dpi=350,
        )
    plt.show()


if DW_BOXPLOTS:
    get_boxplots(
        stat_dict=dw_runtimes,
        value_name="Time (s)",
        fig_title="Optimization time",
        save_figure=SAVE_FIGURE,
    )
    get_boxplots(
        stat_dict=dw_itercounts,
        value_name="Number",
        fig_title="Iteration count",
        save_figure=SAVE_FIGURE,
    )
