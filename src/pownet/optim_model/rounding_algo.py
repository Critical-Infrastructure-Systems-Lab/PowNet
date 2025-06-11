"""rounding_algo.py: Functions to perform iterative rounding."""

import gurobipy as gp
import numpy as np

import logging

logger = logging.getLogger(__name__)


def get_variables(model: gp.Model, target_varnames: list[str] = None) -> dict:
    """Extract non-binary variables from a Gurobi model.

    Args:
        model (gp.Model): The Gurobi model to extract variables from.
        target_varnames (list[str], optional):
            A list of variable name prefixes to include.
            If None, defaults to ["status"].

    Returns:
        dict: A dictionary mapping variable names to their corresponding
              non-binary values (v.X).

    """
    if target_varnames is None:
        target_varnames = ["status"]
    filtered_vars = {}
    for v in model.getVars():
        # Extract the prefix of the variable name (e.g., 'status' from 'status[1,2]')
        if v.varName.split("[")[0] in target_varnames:
            filtered_vars[v.varName] = v
    return filtered_vars


def find_fraction_vars(
    binary_vars: dict,
    atol: float = 1e-5,
) -> dict:
    """Return a list of variable names when their values are fractional."""
    fractional_vars = {}
    for varname in binary_vars:
        x_value = binary_vars[varname].X
        if not (np.isclose(x_value, 0, atol=atol) or np.isclose(x_value, 1, atol=atol)):
            fractional_vars[varname] = binary_vars[varname]
    return fractional_vars


def round_up(variable: gp.Var) -> None:
    variable.lb = 1
    variable.ub = 1


def round_down(variable: gp.Var) -> None:
    variable.lb = 0
    variable.ub = 0


def slow_rounding(
    fraction_vars: dict,
    threshold: float = 0,
) -> None:
    """Iteratively rounding variables with the largest value at each iteration.
    Values above the threshold are rounded up. Values below the threshold are rounded down.
    """
    max_value = max([v.X for v in fraction_vars.values()])
    for var in fraction_vars.values():
        if var.X == max_value:
            if max_value >= threshold:
                round_up(var)
            else:
                round_down(var)


def fast_rounding(fraction_vars: dict, threshold: float = 0) -> None:
    for bin_var in fraction_vars.values():
        if bin_var.X >= threshold:
            round_up(bin_var)
        else:
            round_down(bin_var)


def check_binary_values(var_dict: dict) -> bool:
    """
    Check if all variables in a dictionary have binary values (0 or 1).

    Args:
        var_dict (dict): A dictionary where keys are variable names and
                          values are gurobipy.Var objects.

    Returns:
        bool: True if all variables have binary values, False otherwise.
    """
    for var_name, var in var_dict.items():
        var_value = var.X
        if not (var_value == 0 or var_value == 1):
            logger.info(f"Variable {var_name} has non-binary value: {var_value}")
            return False
    return True


def optimize_with_rounding(
    model: gp.Model,
    rounding_strategy: str,
    threshold: float,
    max_rounding_iter: int,
    mipgap: float,
    timelimit: int,
    num_threads: int,
    log_to_console: bool,
) -> tuple[gp.Model, float, int]:
    """
    Optimize a Gurobi model using iterative rounding with a given threshold.

    This function first relaxes the input model and then iteratively rounds
    fractional variables until an integer solution is found or the maximum
    number of iterations is reached.

    Args:
        model (gp.Model): The Gurobi model to optimize.
        threshold (float): The threshold for rounding fractional variables.
        max_rounding_iter (int): The maximum number of rounding iterations.
        log_to_console (bool): Whether to log optimization output to the console.
        mipgap (float): The relative MIP optimality gap.
        timelimit (int): The time limit for the optimization in seconds.
        num_threads (int): The number of threads to use for optimization.

    Returns:
        gp.Model: The optimized Gurobi model.
    """

    # First specify the model parameters
    model.Params.LogToConsole = log_to_console
    model.Params.MIPGap = mipgap
    model.Params.TimeLimit = timelimit
    model.Params.Threads = num_threads

    rounding_model = model.relax()
    rounding_model.Params.LogToConsole = False
    binary_vars = get_variables(rounding_model)

    rounding_optimization_time = 0
    for current_iter in range(max_rounding_iter):
        rounding_model.optimize()

        # Keep track of the optimization time
        rounding_optimization_time += rounding_model.runtime

        # Fixing variables can cause infeasibility
        if rounding_model.status == 3:
            logger.warning("\nPowNet: Rounding is infeasible. Use the MIP method.")
            model.optimize()
            return model, None, None
        # The model should be feasible, but raise an error if not.
        elif rounding_model.status != 2:
            raise ValueError(f"Unrecognized model status: {rounding_model.status}")

        # Round variables and update the model
        fraction_vars = find_fraction_vars(binary_vars)

        # An empty dict means we have an integer solution.
        if len(fraction_vars) == 0:
            return rounding_model, rounding_optimization_time, current_iter

        if rounding_strategy == "slow":
            slow_rounding(fraction_vars=fraction_vars, threshold=threshold)
        else:
            fast_rounding(fraction_vars=fraction_vars, threshold=threshold)

        # Remove the rounded variables
        rounding_model.update()

    # If no integer solution is found after max_rounding_iter
    logger.warning(
        "\nPowNet: The rounding heuristic has terminated before finding an integer solution."
    )
    model.optimize()
    return model, None, None
