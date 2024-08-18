""" variable.py: Contains functions for adding variables to the optimization model.
"""

import math
import gurobipy as gp
from gurobipy import GRB
import pandas as pd


"""
Functions for adding thermal variables
"""


def add_var_with_ub(
    model: gp.Model,
    varname: str,
    timesteps: range,
    step_k: int,
    sim_horizon: int,
    units: list,
    capacity_df: pd.DataFrame,
) -> gp.tupledict:

    return model.addVars(
        units,
        timesteps,
        lb=0,
        ub={
            (unit_g, t): capacity_df.loc[t + (step_k - 1) * 24, unit_g]
            for t in timesteps
            for unit_g in units
        },
        vtype=GRB.CONTINUOUS,
        name=varname,
    )


def add_var_flow(
    model: gp.Model,
    timesteps: range,
    step_k: int,
    sim_horizon: int,
    edges: list,
    line_capacity_factor: float,
    line_capacity: pd.DataFrame,
) -> gp.tupledict:
    """The flow variable f(a,b,t) represents the flow in the
    line segment (a,b) at hour t in MW/hr). If the flow is positive,
    then energy flows from a to b. Unit: MW/hr.

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.
        step_k (int): The step index.
        sim_horizon (int): The simulation horizon.
        edges (list): The list of edges.
        line_capacity_factor (float): The line capacity factor.
        line_capacity (pd.DataFrame): The dataframe of line capacities.

    Returns:
        gp.tupledict: The flow variable representing the flow in each line segment
    """
    return model.addVars(
        edges,
        timesteps,
        lb={
            (source, sink, t): -1
            * line_capacity_factor
            * line_capacity.loc[t + (step_k - 1) * 24, (source, sink)]
            for t in timesteps
            for source, sink in edges
        },
        ub={
            (source, sink, t): line_capacity_factor
            * line_capacity.loc[t + (step_k - 1) * 24, (source, sink)]
            for t in timesteps
            for source, sink in edges
        },
        vtype=GRB.CONTINUOUS,
        name="flow",
    )


def add_var_voltage_angle(
    model: gp.Model, timesteps: range, nodes: list
) -> gp.tupledict:
    """The voltage angle of a node. Unit: radians.
    This refers to the angular difference between the voltage phasor
    at a particular bus and the reference bus (usually the slack bus).

    NOTE: The voltage angle is bounded between -pi and pi.
    This choice simulates the theoretical limit of the voltage angle.
    Since the assumption of DC-OPF is that the voltage angle is small,
    some studies use the bound of -pi/2 and pi/2.

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.
        nodes (list): The list of nodes.

    Returns:
        gp.tupledict: The voltage angle of each node.

    """
    return model.addVars(
        nodes,
        timesteps,
        lb=-math.pi,
        ub=math.pi,
        vtype=GRB.CONTINUOUS,
        name="theta",
    )
