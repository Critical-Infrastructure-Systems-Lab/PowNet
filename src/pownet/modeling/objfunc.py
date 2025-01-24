"""model_formulation.py: Contains functions for constructing the objective function and constraints of the optimization model."""

from pownet.core.input import SystemInput

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
        (unit, t): thermal_rated_capacity[unit] * thermal_fixed_cost[unit]
        for t in timesteps
        for unit in thermal_units
    }


def get_thermal_opex_coeff(
    step_k: int,
    timesteps: range,
    thermal_units: list,
    thermal_opex: dict,
    fuel_contracts: dict,
    contract_costs: dict,
    thermal_heat_rate: dict,
) -> dict:
    """Variable cost is a function of fuel cost, heat rate, and opex"""
    # TODO: thermal_fuel_cost should be a time-dependent parameter
    return {
        (unit, t): (
            contract_costs[(fuel_contracts[unit], t + (step_k - 1) * 24)]
            * thermal_heat_rate[unit]
        )
        + thermal_opex[unit]
        for t in timesteps
        for unit in thermal_units
    }


def get_thermal_startup_coeff(
    timesteps: range,
    thermal_units: list,
    thermal_startup_cost: dict,
    thermal_rated_capacity: dict,
) -> dict:
    """Startup cost is a function of rated capacity and startup cost per unit"""
    return {
        (unit, t): thermal_rated_capacity[unit] * thermal_startup_cost[unit]
        for t in timesteps
        for unit in thermal_units
    }


def get_marginal_cost_coeff(
    step_k: int,
    timesteps: range,
    units: list,
    nondispatch_contracts: dict,
    contract_costs: dict,
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
        (unit, t): contract_costs[(nondispatch_contracts[unit], t + (step_k - 1) * 24)]
        for t in timesteps
        for unit in units
    }
