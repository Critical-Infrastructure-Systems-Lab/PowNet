""" variable.py: Contains functions for adding variables to the optimization model.
"""

import math
import gurobipy as gp
from gurobipy import GRB
import pandas as pd


"""
Functions for adding thermal variables
"""


def add_var_pthermal(
    model: gp.Model,
    timesteps: range,
    step_k: int,
    sim_horizon: int,
    thermal_units: list,
    thermal_derated_capacity: pd.DataFrame,
) -> gp.tupledict:
    """
    Power output by a thermal unit (also called dispatch). Unit: MW.
    The lower bound is the minimum capacity of the thermal unit.
    The upper bound is the derated capacity of the thermal unit.

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.
        step_k (int): The step index.
        sim_horizon (int): The simulation horizon.
        thermal_units (list): The list of thermal units.
        thermal_derated_capacity (pd.DataFrame): The dataframe of thermal units' derated capacity.

    Returns:
        gp.tupledict: The dispatch variable representing the power output by each thermal unit.

    """
    return model.addVars(
        thermal_units,
        timesteps,
        lb=0,
        ub={
            (unit_g, t): thermal_derated_capacity.loc[
                t + (step_k - 1) * sim_horizon, unit_g
            ]
            for t in timesteps
            for unit_g in thermal_units
        },
        vtype=GRB.CONTINUOUS,
        name="pthermal",
    )


def add_var_status(
    model: gp.Model, timesteps: range, thermal_units: list
) -> gp.tupledict:
    """
    The commitment status of a thermal unit. On = 1 and off = 0. Unitless.

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.
        thermal_units (list): The list of thermal units.

    Returns:
        gp.tupledict: The commitment status of each thermal unit.

    """
    return model.addVars(
        thermal_units,
        timesteps,
        vtype=GRB.BINARY,
        name="status",
    )


def add_var_startup(
    model: gp.Model, timesteps: range, thermal_units: list
) -> gp.tupledict:
    """The startup variable is a binary variable indicating if a unit is starting up.
    Unitless.

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.
        thermal_units (list): The list of thermal units.

    Returns:
        gp.tupledict: The startup variable indicating if a unit is starting up.

    """
    return model.addVars(
        thermal_units,
        timesteps,
        vtype=GRB.BINARY,
        name="startup",
    )


def add_var_shutdown(
    model: gp.Model, timesteps: range, thermal_units: list
) -> gp.tupledict:
    """The shutdown variable is a binary variable indicating if a unit is shutting down. Unitless.

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.
        thermal_units (list): The list of thermal units.

    Returns:
        gp.tupledict: The shutdown variable indicating if a unit is shutting down.

    """
    return model.addVars(
        thermal_units,
        timesteps,
        vtype=GRB.BINARY,
        name="shutdown",
    )


def add_var_vpower(
    model: gp.Model,
    timesteps: range,
    step_k: int,
    sim_horizon: int,
    thermal_units,
    thermal_derated_capacity: pd.DataFrame,
) -> gp.tupledict:
    """Power output *ABOVE* the minimum output of a thermal unit. Unit: MW
    This is also called variable power output.

    Formula: vpower + P_min = pthermal

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.
        step_k (int): The step index.
        sim_horizon (int): The simulation horizon.
        thermal_units: The list of thermal units.
        thermal_derated_capacity (pd.DataFrame): The dataframe of thermal units' derated capacity.

    Returns:
        gp.tupledict: The power output above the minimum capacity of each thermal unit

    """
    return model.addVars(
        thermal_units,
        timesteps,
        lb=0,
        ub={
            (unit_g, t): thermal_derated_capacity.loc[
                t + (step_k - 1) * sim_horizon, unit_g
            ]
            for t in timesteps
            for unit_g in thermal_units
        },
        vtype=GRB.CONTINUOUS,
        name="vpower",
    )


def add_var_vpowerbar(
    model: gp.Model,
    timesteps: range,
    step_k: int,
    sim_horizon: int,
    thermal_units: list,
    thermal_derated_capacity: pd.DataFrame,
) -> gp.tupledict:
    """Maximum power available *ABOVE* the minimum capacity of a thermal unit. Unit: MW.
    The original variable, maximum power available, was introduced by Carrion and Arroyo (2006).
    Here, we reformulated similarly to vpower.

    Formula: vpowerbar = vpower + spin

    The upper bound is the derated capacity of the thermal unit.

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.
        step_k (int): The step index.
        sim_horizon (int): The simulation horizon.
        thermal_units (list): The list of thermal units.
        thermal_derated_capacity (pd.DataFrame): The dataframe of thermal units' derated capacity.

    Returns:
        gp.tupledict: The maximum power available above the minimum capacity of each thermal unit.

    """
    return model.addVars(
        thermal_units,
        timesteps,
        lb=0,
        ub={
            (unit_g, t): thermal_derated_capacity.loc[
                t + (step_k - 1) * sim_horizon, unit_g
            ]
            for t in timesteps
            for unit_g in thermal_units
        },
        vtype=GRB.CONTINUOUS,
        name="vpowerbar",
    )


def add_var_spin(
    model: gp.Model,
    timesteps: range,
    step_k: int,
    sim_horizon: int,
    thermal_units: list,
    thermal_derated_capacity: pd.DataFrame,
    thermal_min_capacity: dict,
) -> gp.tupledict:
    """Spinning reserve of a thermal unit. Unit: MW.
    The upper bound is the difference between the derated capacity and the minimum capacity.

    Formula: spin = vpowerbar - vpower

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.
        step_k (int): The step index.
        sim_horizon (int): The simulation horizon.
        thermal_units (list): The list of thermal units.
        thermal_derated_capacity (pd.DataFrame): The dataframe of thermal units' derated capacity.
        thermal_min_capacity (dict): The dictionary of thermal units' minimum capacity.

    Returns:
        gp.tupledict: The spinning reserve of each thermal unit.

    """
    return model.addVars(
        thermal_units,
        timesteps,
        lb=0,
        ub={
            (unit_g, t): thermal_derated_capacity.loc[
                t + (step_k - 1) * sim_horizon, unit_g
            ]
            - thermal_min_capacity[unit_g]
            for t in timesteps
            for unit_g in thermal_units
        },
        vtype=GRB.CONTINUOUS,
        name="spin",
    )


################################################################
# Functions for adding RE/import variables
################################################################


def add_var_phydro(
    model: gp.Model,
    timesteps: range,
    step_k: int,
    sim_horizon: int,
    hydro_units: list,
    hydro_capacity: pd.DataFrame,
) -> gp.tupledict:
    """The power output of hydro units. Unit: MW.

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.
        step_k (int): The step index.
        sim_horizon (int): The simulation horizon.
        hydro_units (list): The list of hydro units.
        hydro_capacity (pd.DataFrame): The dataframe of hydro units' capacity.

    Returns:
        gp.tupledict: The power output of each hydro unit.

    """
    return model.addVars(
        hydro_units,
        timesteps,
        lb=0,
        ub={
            (hydro_unit, t): hydro_capacity.loc[
                t + (step_k - 1) * sim_horizon, hydro_unit
            ].iloc[0]
            for t in timesteps
            for hydro_unit in hydro_units
        },
        vtype=GRB.CONTINUOUS,
        name="phydro",
    )


def add_var_phydro2(
    model: gp.Model, timesteps: range, hydro_units: list, turbine_capacity: dict
) -> gp.tupledict:
    """The power output of hydro units bounded by their turbine capacity. Unit: MW.
    Use this method when the system operator also controls the reservoirs, so the
    hydropower availability is limited by the turbine capacity.

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.
        hydro_units (list): The list of hydro units.
        turbine_capacity (dict): Mapping of hydro units to their turbine capacity.

    Returns:
        gp.tupledict: The power output of each hydro unit.

    """
    return model.addVars(
        hydro_units,
        timesteps,
        lb=0,
        ub={
            (hydro_unit, t): turbine_capacity[hydro_unit]
            for t in timesteps
            for hydro_unit in hydro_units
        },
        vtype=GRB.CONTINUOUS,
        name="phydro",
    )


def add_var_psolar(
    model: gp.Model,
    timesteps: range,
    step_k: int,
    sim_horizon: int,
    solar_units: list,
    solar_capacity: pd.DataFrame,
) -> gp.tupledict:
    """The power output of solar units. Unit: MW.

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.
        step_k (int): The step index.
        sim_horizon (int): The simulation horizon.
        solar_units (list): The list of solar units.
        solar_capacity (pd.DataFrame): The dataframe of solar units' capacity.

    Returns:
        gp.tupledict: The power output of each solar unit.

    """
    return model.addVars(
        solar_units,
        timesteps,
        lb=0,
        ub={
            (solar_unit, t): solar_capacity.loc[
                t + (step_k - 1) * sim_horizon, solar_unit
            ].iloc[0]
            for t in timesteps
            for solar_unit in solar_units
        },
        vtype=GRB.CONTINUOUS,
        name="psolar",
    )


def add_var_pwind(
    model: gp.Model,
    timesteps: range,
    step_k: int,
    sim_horizon: int,
    wind_units: list,
    wind_capacity: pd.DataFrame,
) -> gp.tupledict:
    """The power output of wind units. Unit: MW.

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.
        step_k (int): The step index.
        sim_horizon (int): The simulation horizon.
        wind_units (list): The list of wind units.
        wind_capacity (pd.DataFrame): The dataframe of wind units' capacity.

     Returns:
        gp.tupledict: The power output of each wind unit.

    """
    return model.addVars(
        wind_units,
        timesteps,
        lb=0,
        ub={
            (wind_unit, t): wind_capacity.loc[
                t + (step_k - 1) * sim_horizon, wind_unit
            ].iloc[0]
            for t in timesteps
            for wind_unit in wind_units
        },
        vtype=GRB.CONTINUOUS,
        name="pwind",
    )


def add_var_pimp(
    model: gp.Model,
    timesteps: range,
    step_k: int,
    sim_horizon: int,
    import_units: list,
    import_capacity: pd.DataFrame,
) -> gp.tupledict:
    """The import from neighboring system. Unit: MW.

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.
        step_k (int): The step index.
        sim_horizon (int): The simulation horizon.
        import_units (list): The list of import units.
        import_capacity (pd.DataFrame): The dataframe of import units' capacity.

    Returns:
        gp.tupledict: The import from each neighboring system

    """
    return model.addVars(
        import_units,
        timesteps,
        lb=0,
        ub={
            (import_unit, t): import_capacity.loc[
                t + (step_k - 1) * sim_horizon, import_unit
            ].iloc[0]
            for t in timesteps
            for import_unit in import_units
        },
        vtype=GRB.CONTINUOUS,
        name="pimp",
    )


################################################################
# Functions for adding node variables
################################################################


def add_var_pos_pmismatch(
    model: gp.Model, timesteps: range, demand_nodes: list
) -> gp.tupledict:
    """The positive power mismatch of a node. Unit: MW.

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.
        demand_nodes (list): The list of demand nodes.

    Returns:
        gp.tupledict: The positive mismatch of each demand node.

    """
    return model.addVars(
        demand_nodes,
        timesteps,
        lb=0,
        vtype=GRB.CONTINUOUS,
        name="p_pmismatch",
    )


def add_var_neg_pmismatch(
    model: gp.Model, timesteps: range, demand_nodes: list
) -> gp.tupledict:
    """The negative power mismatch of a node. Unit: MW.

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.
        demand_nodes (list): The list of demand nodes.

    Returns:
        gp.tupledict: The negative mismatch of each demand node.

    """
    return model.addVars(
        demand_nodes,
        timesteps,
        lb=0,
        vtype=GRB.CONTINUOUS,
        name="n_pmismatch",
    )


def add_var_load_shortfall(
    model: gp.Model, timesteps: range, demand_nodes: list
) -> gp.tupledict:
    """The shortfall of electricity of the overall system. Unit: MW.
    NOTE: Currently not in used.
    Formula: load_shortfall = p_pmismatch + n_pmismatch

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.

    Returns:
        gp.tupledict: The shortfall of the overall system.

    """
    return model.addVars(
        demand_nodes,
        timesteps,
        lb=-GRB.INFINITY,
        vtype=GRB.CONTINUOUS,
        name="load_shortfall",
    )


################################################################
# Functions for adding flow variables
################################################################


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
            * line_capacity.loc[t + (step_k - 1) * sim_horizon, (source, sink)]
            for t in timesteps
            for source, sink in edges
        },
        ub={
            (source, sink, t): line_capacity_factor
            * line_capacity.loc[t + (step_k - 1) * sim_horizon, (source, sink)]
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


################################################################
# Functions for adding System variables
################################################################


def add_var_spin_shortfall(model: gp.Model, timesteps: range) -> gp.tupledict:
    """The shortfall of the spinning reserve of the overall system. Unit: MW.

    Args:
        model (gp.Model): The optimization model.
        timesteps (range): The range of timesteps.

    Returns:
        gp.tupledict: The spinning reserve of the overall system.

    """
    return model.addVars(
        timesteps,
        lb=0,
        vtype=GRB.CONTINUOUS,
        name="spin_shortfall",
    )
