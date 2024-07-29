""" This script runs the rounding experiment. Each rounding strategy
only stops when we have recovered an integer solution or the model
becomes infeasible.
"""

import csv
from datetime import datetime
import os

import gurobipy as gp
import pandas as pd

from pownet.folder_sys import get_temp_dir, get_output_dir, count_mps_files
from pypolp.functions import get_non_binary_from_model


# Gurobi MIPGAP
gp.setParam("OutputFlag", False)


def round_up(variable: gp.Var) -> None:
    variable.lb = 1
    variable.ub = 1


def round_down(variable: gp.Var) -> None:
    variable.lb = 0
    variable.ub = 0


def slow_rounding(
    model: gp.Model,
    non_binary_var_df: pd.DataFrame,
    threshold: float,
) -> None:
    """Iteratively rounding variables with the largest value at each iteration.
    Values above the threshold are rounded up. Values below the threshold are rounded down.
    """
    # Identify the largest fractional value
    max_value = non_binary_var_df["value"].max()
    # Filter variable names to those with the largest fractional value
    max_varnames = non_binary_var_df.loc[
        non_binary_var_df["value"] == max_value, "name"
    ]
    # Rounding up/down is dependent on the threshold
    if max_value >= threshold:
        for max_varname in max_varnames:
            max_var = model.getVarByName(max_varname)
            round_up(variable=max_var)
    else:
        for max_varname in max_varnames:
            max_var = model.getVarByName(max_varname)
            round_down(variable=max_var)


def fast_rounding(
    model: gp.Model,
    non_binary_var_df: pd.DataFrame,
    threshold,
) -> None:
    """Round variables at the same time.
    Variables above the thredhold are rounded up.
    Variables below the threshold are rounded down.
    """
    for _, row in non_binary_var_df.iterrows():
        var = model.getVarByName(row["name"])
        if row["value"] >= threshold:
            round_up(variable=var)
        else:
            round_down(variable=var)


def calculate_set_mipgap(rounding_objval: float, true_objval: float) -> float:
    """The value to set the Gurobi solver is calculated as
    the fractional difference between the objective value from rounding
    and the actual:
    set_mipgap = |rounding_objval - mip_objval| / |mip_objval|
    """
    # If the model is infeasible, then set MIPGap of Gurobi to 1.0
    if rounding_objval is None:
        return 1.0
    else:
        return abs(rounding_objval - true_objval) / abs(true_objval)


def run_experiment(
    model_name: str,
    T_simulate: int,
    round_strategy: str,
    round_threshold: float,
    verbose: bool,
    max_round_iter: int = 1000,
) -> None:

    # Define the session name
    ctime = datetime.now().strftime("%Y%m%d_%H%M")
    session_name = (
        f"{ctime}_rounding_{model_name}_{T_simulate}_{round_strategy}_{round_threshold}"
    )

    # We store the statistics of all sessions
    # in a folder called 'rounding_stats_new'
    rounding_folder = os.path.join(get_temp_dir(), "new_rounding_stats")
    if not os.path.exists(rounding_folder):
        os.mkdir(os.path.join(rounding_folder))

    print(f"\n\nStarting session {session_name}...")

    # Load the true values to use in setting mipgap
    true_objvals = pd.read_csv(
        os.path.join(
            get_temp_dir(),
            "true_values",
            f"{model_name}_{T_simulate}.csv",
        ),
        usecols=["mip_objval"],
        header=0,
    )

    # Start the timer for the whole session
    start_time = datetime.now()

    # Fields are headers in of our statistics csv file
    FIELDS = [
        "model_name",
        "T_simulate",
        "rounding_k",
        "rounding_objval",
        "rounding_opt_time",
        "wall_clock_rounding",
        "rounding_is_feasible",
        "set_mipgap",
        "mip_objval",
        "mip_opt_time",
        "wall_clock_mip",
        "true_objval",
    ]
    csv_name = os.path.join(rounding_folder, f"{session_name}.csv")
    with open(csv_name, "w", newline="", encoding="utf-8") as csvfile:
        # creating a csv writer object
        csvwriter = csv.writer(csvfile)
        # writing the fields
        csvwriter.writerow(FIELDS)

    # Find the number of instances
    instance_folder = os.path.join(
        get_output_dir(), f"{model_name}_{T_simulate}_instances"
    )
    num_instances = count_mps_files(instance_folder)

    # Solve the instances and collect the statistics
    for k in range(num_instances):
        if verbose:
            print(f"\n\nIterative rounding: === Solving Day {k} ===")

        path_mps = os.path.join(instance_folder, f"{model_name}_{k}.mps")

        wall_clock_rounding_timer = datetime.now()
        rounding_model = gp.read(path_mps)
        rounding_model = rounding_model.relax()

        # Keep track of the optimization time
        round_opt_time = 0
        # kk is the rounding iteration number
        round_iter = 0
        # Stop rounding if the solution is integer
        is_integer = False

        while (not is_integer) and (round_iter < max_round_iter):
            if verbose:
                print(f"\nIterative rounding: Iteration: {round_iter}")

            # Solve the model and record the time
            rounding_model.optimize()
            round_opt_time += rounding_model.runtime

            # Check the model status after optimization
            # Fixing model variables can cause infeasibility
            if rounding_model.status == 2:
                rounding_objval = rounding_model.objval
                rounding_is_feasible = True

            # If the model is infeasible, then stop
            elif rounding_model.status == 3:
                rounding_objval = None
                rounding_is_feasible = False

                # Save the ilp file
                ilp_name = os.path.join(
                    get_temp_dir(), "infeasible_models", f"{session_name}_{k}.ilp"
                )
                rounding_model.computeIIS()
                rounding_model.write(ilp_name)
                break

            else:
                raise ValueError("Model status is neither optimal nor infeasible.")

            # The tight formulation of thermal units should recover start/shut as int
            # when rounding up the status variables. Hence, we only deal with
            # status variables here.
            non_binary_var_df = get_non_binary_from_model(
                model=rounding_model, target_varnames=["status"]
            )
            is_integer = len(non_binary_var_df) == 0

            if verbose:
                print(f"\nRounding the following variables with {round_strategy}")
                print(non_binary_var_df)
                print(f"\nNumber of non-binary variables: {len(non_binary_var_df)}")

            # Select a rounding strategy
            if round_strategy == "fast_rounding":
                fast_rounding(
                    model=rounding_model,
                    non_binary_var_df=non_binary_var_df,
                    threshold=round_threshold,
                )
            elif round_strategy == "slow_rounding":
                slow_rounding(
                    model=rounding_model,
                    non_binary_var_df=non_binary_var_df,
                    threshold=round_threshold,
                )
            else:
                raise ValueError(f"Unimplemented rounding strategy: {round_strategy}")

            # IMPORTANT: update the model
            rounding_model.update()
            round_iter += 1

        wall_clock_rounding_timer = (
            datetime.now() - wall_clock_rounding_timer
        ).total_seconds()

        # ----- Solve with Gurobi as MIP
        wall_clock_mip = datetime.now()
        mip_model = gp.read(path_mps)
        # Set the MIPGap competitively to the rounding objective value
        # Assume k represents the same instance
        true_objval = true_objvals.loc[k, "mip_objval"]
        set_mipgap = calculate_set_mipgap(rounding_objval, true_objval)
        mip_model.setParam("MIPGap", set_mipgap)

        mip_model.optimize()
        mip_opt_time = mip_model.runtime

        wall_clock_mip = (datetime.now() - wall_clock_mip).total_seconds()

        # ----- Saving intermediate results
        with open(csv_name, "a", newline="", encoding="utf-8") as csvfile:
            # creating a csv writer object
            csvwriter = csv.writer(csvfile)
            csvwriter.writerow(
                [
                    model_name,
                    T_simulate,
                    round_iter,  # rounding_k
                    rounding_objval,  # rounding_objval
                    round_opt_time,  # rounding_opt_time
                    wall_clock_rounding_timer,  # wall_clock_rounding
                    rounding_is_feasible,  # rounding_is_feasible
                    set_mipgap,
                    mip_model.objval,  # mip_objval
                    mip_opt_time,  # mip_opt_time
                    wall_clock_mip,  # wall_lock_mip
                    true_objval,
                ]
            )

    print(f"\n\nCompleted {session_name}...")
    print(f"Total time taken = {datetime.now() - start_time}")


if __name__ == "__main__":
    model_name = "laos"
    T_simulates = [24]
    round_strategies = ["fast_rounding"]
    thresholds = [0.5]  # Between 0.01 and 0.15
    verbose = False

    exp_pairs = [
        (T_simulate, strategy, threshold)
        for T_simulate in T_simulates
        for strategy in round_strategies
        for threshold in thresholds
    ]

    for T_simulate, round_strategy, round_threshold in exp_pairs:
        run_experiment(
            model_name=model_name,
            T_simulate=T_simulate,
            round_strategy=round_strategy,
            round_threshold=round_threshold,
            verbose=verbose,
        )
