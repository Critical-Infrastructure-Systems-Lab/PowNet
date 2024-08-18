"""model_formulation.py: Contains functions for constructing the objective function and constraints of the optimization model."""

from __future__ import annotations

import gurobipy as gp
import gurobipy as GRB
import pandas as pd


""" Functions for the objective function
"""


def get_thermal_fixed_coeff(
    timesteps: range,
    thermal_units: list,
    thermal_fixed_cost: dict,
    thermal_rated_capacity: dict,
) -> dict:
    """Fixed cost is a function of rated capacity and fixed cost per unit"""
    return {
        (unit_g, t): thermal_rated_capacity[unit_g] * thermal_fixed_cost[unit_g]
        for t in timesteps
        for unit_g in thermal_units
    }


def get_thermal_opex_coeff(
    timesteps: range,
    thermal_units: list,
    thermal_opex: dict,
    thermal_fuel_cost: dict,
    thermal_heat_rate: dict,
) -> dict:
    """Variable cost is a function of fuel cost, heat rate, and opex"""
    # TODO: thermal_fuel_cost should be a time-dependent parameter
    return {
        (unit_g, t): (thermal_fuel_cost[unit_g] * thermal_heat_rate[unit_g])
        + thermal_opex[unit_g]
        for t in timesteps
        for unit_g in thermal_units
    }


def get_thermal_startup_coeff(
    timesteps: range,
    thermal_units: list,
    thermal_startup_cost: dict,
    thermal_rated_capacity: dict,
) -> dict:
    """Startup cost is a function of rated capacity and startup cost per unit"""
    return {
        (unit_g, t): thermal_rated_capacity[unit_g] * thermal_startup_cost[unit_g]
        for t in timesteps
        for unit_g in thermal_units
    }


def get_marginal_cost_coeff(
    inputs: "SystemInput",
    step_k: int,
    timesteps: range,
    sim_horizon: int,
    units: list,
    attribute: str,
) -> dict:
    """
    Generic helper function to calculate coefficients based on marginal cost or a similar attribute for a list of units

    Args:
        units: The list of units to calculate coefficients for
        attribute: The attribute name in inputs to use for cost calculation

    Returns
        A dictionary mapping (unit, t) tuples to the calculated coefficients
    """
    return {
        (unit, t): getattr(inputs, attribute).loc[t + (step_k - 1) * 24, unit]
        for t in timesteps
        for unit in units
    }
