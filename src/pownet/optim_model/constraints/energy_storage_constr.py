"""energy_storage_constr.py: Constraints for energy storage units."""

import gurobipy as gp


def add_c_link_ess_charge(
    model: gp.Model,
    pcharge: gp.tupledict,
    ucharge: gp.tupledict,
    timesteps: range,
    units: list,
    max_charge: dict[str, float],
) -> gp.tupledict:
    """Link the charging indicator to the continuous charging variable.
    The charging variable is limited by the maximum charging capacity of the unit.

    Args:
        model (gp.Model): The Gurobi model.
        pcharge (gp.tupledict): Continuous charging variable.
        ucharge (gp.tupledict): Binary charging indicator.
        timesteps (range): Range of time steps.
        units (list): List of energy storage units.
        max_charge (dict[str, float]): Maximum charging capacity for each unit.

    Returns:
        gp.tupledict: The added constraints.
    """
    return model.addConstrs(
        (
            pcharge[unit, t] <= ucharge[unit, t] * max_charge[unit]
            for unit in units
            for t in timesteps
        ),
        name="link_ess_charge",
    )


def add_c_link_ess_discharge(
    model: gp.Model,
    pdischarge: gp.tupledict,
    udischarge: gp.tupledict,
    timesteps: range,
    units: list,
    max_discharge: dict[str, float],
) -> gp.tupledict:
    """Link the discharging indicator to the continuous discharging variable.
    The discharging variable is limited by the maximum discharging capacity of the unit.

    Args:
        model (gp.Model): The Gurobi model.
        pdischarge (gp.tupledict): Continuous discharging variable.
        udischarge (gp.tupledict): Binary discharging indicator.
        timesteps (range): Range of time steps.
        units (list): List of energy storage units.
        max_discharge (dict[str, float]): Maximum discharging capacity for each unit.

    Returns:
        gp.tupledict: The added constraints.
    """
    return model.addConstrs(
        (
            pdischarge[unit, t] <= udischarge[unit, t] * max_discharge[unit]
            for unit in units
            for t in timesteps
        ),
        name="link_ess_discharge",
    )


def add_c_link_ess_state(
    model: gp.Model,
    ucharge: gp.tupledict,
    udischarge: gp.tupledict,
    timesteps: range,
    units: list,
) -> gp.tupledict:
    """Link the charging and discharging indicators to ensure that only one can be active at a time.

    Args:
        model (gp.Model): The Gurobi model.
        ucharge (gp.tupledict): Binary charging indicator.
        udischarge (gp.tupledict): Binary discharging indicator.
        timesteps (range): Range of time steps.
        units (list): List of energy storage units.

    Returns:
        gp.tupledict: The added constraints.
    """
    return model.addConstrs(
        (
            ucharge[unit, t] + udischarge[unit, t] <= 1
            for unit in units
            for t in timesteps
        ),
        name="link_ess_state",
    )


def add_c_unit_ess_balance_init(
    model: gp.Model,
    pcharge: gp.tupledict,
    pdischarge: gp.tupledict,
    charge_state: gp.tupledict,
    units: list,
    charge_state_init: dict[str, float],
    charge_efficiency: dict[str, float],
    discharge_efficiency: dict[str, float],
    self_discharge_rate: dict[str, float],
) -> gp.tupledict:
    """Initial balance for energy storage units at the first time step.

    Args:
        model (gp.Model): The Gurobi model.
        pcharge (gp.tupledict): Continuous charging variable.
        pdischarge (gp.tupledict): Continuous discharging variable.
        charge_state (gp.tupledict): Charge state variable.
        units (list): List of energy storage units.
        charge_state_init (dict[str, float]): Initial charge state for each unit.
        charge_efficiency (dict[str, float]): Charging efficiency for each unit.
        discharge_efficiency (dict[str, float]): Discharging efficiency for each unit.
        self_discharge_rate (dict[str, float]): Self-discharge rate for each unit.

    Returns:
        gp.tupledict: The added constraints.
    """
    t = 1
    return model.addConstrs(
        (
            charge_state[unit, t]
            == (1 - self_discharge_rate[unit]) * charge_state_init[unit]
            + charge_efficiency[unit] * pcharge[unit, t]
            - pdischarge[unit, t] / discharge_efficiency[unit]
            for unit in units
        ),
        name="unit_ess_balance_init",
    )


def add_c_unit_ess_balance(
    model: gp.Model,
    pcharge: gp.tupledict,
    pdischarge: gp.tupledict,
    charge_state: gp.tupledict,
    units: list,
    sim_horizon: int,
    charge_efficiency: dict[str, float],
    discharge_efficiency: dict[str, float],
    self_discharge_rate: dict[str, float],
) -> gp.tupledict:
    """Balance for energy storage units at the second time step and onwards.
    The balance equation ensures that the charge state at time t is equal to the charge state at time t-1,
    adjusted for the charging and discharging variables, as well as the self-discharge rate.

    Args:
        model (gp.Model): The Gurobi model.
        pcharge (gp.tupledict): Continuous charging variable.
        pdischarge (gp.tupledict): Continuous discharging variable.
        charge_state (gp.tupledict): Charge state variable.
        units (list): List of energy storage units.
        sim_horizon (int): Simulation horizon.
        charge_efficiency (dict[str, float]): Charging efficiency for each unit.
        discharge_efficiency (dict[str, float]): Discharging efficiency for each unit.
        self_discharge_rate (dict[str, float]): Self-discharge rate for each unit.

    Returns:
        gp.tupledict: The added constraints.
    """
    return model.addConstrs(
        (
            charge_state[unit, t]
            == (1 - self_discharge_rate[unit]) * charge_state[unit, t - 1]
            + charge_efficiency[unit] * pcharge[unit, t]
            - pdischarge[unit, t] / discharge_efficiency[unit]
            for unit in units
            for t in range(2, sim_horizon + 1)
        ),
        name="unit_ess_balance",
    )
