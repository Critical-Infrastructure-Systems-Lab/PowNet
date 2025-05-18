"""variable_func.py: Contains functions for adding variables to the optimization model."""

import gurobipy as gp
from gurobipy import GRB
import pandas as pd

from pownet.data_utils import (
    get_capacity_value,
)


def add_var_with_variable_ub(
    model: gp.Model,
    varname: str,
    timesteps: range,
    step_k: int,
    units: list,
    capacity_df: pd.DataFrame,
) -> gp.tupledict:
    """Add a variable with a variable upper bound in a day-ahead rolling horizon optimization.

    Args:
        model (gp.Model): The optimization model.
        varname (str): The name of the variable.
        timesteps (range): The range of timesteps.
        step_k (int): The step index.
        units (list): The list of units.
        capacity_df (pd.DataFrame): The dataframe of capacities.

    Returns:
        gp.tupledict: The variable with a variable upper bound.

    """

    return model.addVars(
        units,
        timesteps,
        lb=0,
        ub={
            (unit, t): get_capacity_value(t, unit, step_k, capacity_df)
            for t in timesteps
            for unit in units
        },
        vtype=GRB.CONTINUOUS,
        name=varname,
    )


def update_var_with_variable_ub(
    variables: gp.tupledict,
    step_k: int,
    capacity_df: pd.DataFrame,
) -> None:
    """Update the time-dependent upper bound of the variable.

    Args:
        variables (gp.tupledict): The variable with a variable upper bound.
        step_k (int): The step index.
        capacity_df (pd.DataFrame): The dataframe of capacities.

    Returns:
        None
    """
    for (unit, t), v in variables.items():
        capacity_value = get_capacity_value(t, unit, step_k, capacity_df)
        v.ub = capacity_value
    return


def update_flow_vars(
    flow_variables: gp.tupledict,
    step_k: int,
    capacity_df: pd.DataFrame,
    line_capacity_factor: float,
) -> None:
    """Update the lower and upper bounds of the flow variables based on the capacity dataframes"""
    hours_per_step = 24
    for (node1, node2, t), flow_variable in flow_variables.items():
        edge = (node1, node2)
        line_capacity = capacity_df.loc[t + (step_k - 1) * hours_per_step, edge]
        flow_variable.ub = line_capacity * line_capacity_factor
