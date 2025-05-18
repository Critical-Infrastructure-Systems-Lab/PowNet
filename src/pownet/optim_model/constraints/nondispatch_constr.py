"""nondispatch_constr.py: Constraints for non-dispatchable units."""

import gurobipy as gp
import pandas as pd


def add_c_hourly_unit_ub(
    model: gp.Model,
    pdispatch: gp.tupledict,
    unit_type: str,
    timesteps: range,
    units: list,
    contracted_capacity_dict: dict[str, float],
) -> gp.tupledict:
    """
    Add constraints to define the hourly availability of non-dispatchable units. This is limited by the
    contracted_capacity

    Args:
        model (gp.Model): The optimization model.
        pdispatch (gp.tupledict): The dispatch variable.
        unit_type (str): The type of unit ("wind", "solar", "hydro", "import").
        timesteps (range): The range of timesteps.
        units (list): The list of units.
        contracted_capacity_dict (dict[str, float]): The contracted capacity of the unit.

    Returns:
        gp.tupledict: The constraints linking the dispatch variable and the unit status variable.
    """
    return model.addConstrs(
        (
            pdispatch[unit, t] <= contracted_capacity_dict[unit]
            for unit in units
            for t in timesteps
        ),
        name=f"hourly_{unit_type}_ub",
    )


def add_c_link_unit_pu(
    model: gp.Model,
    pdispatch: gp.tupledict,
    u: gp.tupledict,
    unit_type: str,
    timesteps: range,
    units: list,
    contracted_capacity_dict: dict[str, float],
) -> gp.tupledict:
    """
    Add constraints to link the dispatch variable and the unit status variable.
    The dispatch variable is limited by the unit status variable and the maximum
    dispatch of the unit (contracted capacity).

    Args:
        model (gp.Model): The optimization model.
        pdispatch (gp.tupledict): The dispatch variable.
        u (gp.tupledict): The unit status variable.
        unit_type (str): The type of unit ("wind", "solar", "hydro", "import").
        timesteps (range): The range of timesteps.
        units (list): The list of units.
        contracted_capacity_dict (dict[str, float]): The contracted capacity of the unit.

    Returns:
        gp.tupledict: The constraints linking the dispatch variable and the unit status variable.
    """
    return model.addConstrs(
        (
            pdispatch[unit, t] <= u[unit, t] * contracted_capacity_dict[unit]
            for unit in units
            for t in timesteps
        ),
        name=f"link_{unit_type}_pu",
    )


def add_c_hydro_limit_daily(
    model: gp.Model,
    phydro: gp.tupledict,
    step_k: int,
    sim_horizon: int,
    hydro_units: list,
    hydro_capacity: pd.DataFrame,
) -> gp.tupledict:
    """
    Add constraints to limit hydropower by the daily amount. The sum of dispatch variables
    for each hydro unit over a 24-hour period must be less than or equal to the daily capacity.

    Args:
        model (gp.Model): The optimization model
        phydro (gp.tupledict): The power output of hydro units
        step_k (int): The current iteration
        sim_horizon (int): The simulation horizon
        hydro_units (list): The list of hydro units
        hydro_capacity (pd.DataFrame): The daily capacity of the hydro unit

    Returns:
        gp.tupledict: The constraints for the daily hydro limit

    Raises:
        ValueError: If the simulation horizon is not divisible by 24

    """
    # When formulating with daily hydropower, sim_horizon must be divisible
    # by 24 because the hydro_capacity is daily.
    if sim_horizon % 24 != 0:
        raise ValueError(
            "The simulation horizon must be divisible by 24 when using daily hydropower capacity."
        )
    constraints = gp.tupledict()
    max_day = sim_horizon // 24
    for day in range(step_k, step_k + max_day):
        for hydro_unit in hydro_units:
            current_day = day - step_k + 1
            cname = f"hydro_limit_daily[{hydro_unit},{current_day}]"
            constraints[cname] = model.addConstr(
                gp.quicksum(
                    phydro[hydro_unit, t]
                    for t in range(1 + (current_day - 1) * 24, current_day * 24 + 1)
                )
                <= hydro_capacity.loc[day, hydro_unit],
                name=cname,
            )
    return constraints


def add_c_hydro_limit_daily_dict(
    model: gp.Model,
    phydro: gp.tupledict,
    step_k: int,
    sim_horizon: int,
    hydro_units: list,
    hydro_capacity_dict: dict[tuple[str, int], float],
) -> gp.tupledict:
    """
    Add constraints to limit hydropower by the daily amount. The sum of dispatch variables
    for each hydro unit over a 24-hour period must be less than or equal to the daily capacity.

    Args:
        model (gp.Model): The optimization model
        phydro (gp.tupledict): The power output of hydro units
        step_k (int): The current iteration
        sim_horizon (int): The simulation horizon
        hydro_units (list): The list of hydro units
        hydro_capacity_dict: The daily capacity of the hydro unit

    Returns:
        gp.tupledict: The constraints for the daily hydro limit

    Raises:
        ValueError: If the simulation horizon is not divisible by 24

    """
    if len(hydro_units) == 0:
        return gp.tupledict()

    # When formulating with daily hydropower, sim_horizon must be divisible
    # by 24 because the hydro_capacity is daily.
    if sim_horizon % 24 != 0:
        raise ValueError(
            "The simulation horizon must be divisible by 24 when using daily hydropower capacity."
        )
    constraints = gp.tupledict()
    max_day = sim_horizon // 24
    for day in range(step_k, step_k + max_day):
        for hydro_unit in hydro_units:
            current_day = day - step_k + 1
            cname = f"hydro_limit_daily[{hydro_unit},{current_day}]"
            constraints[cname] = model.addConstr(
                gp.quicksum(
                    phydro[hydro_unit, t]
                    for t in range(1 + (current_day - 1) * 24, current_day * 24 + 1)
                )
                <= hydro_capacity_dict[hydro_unit, day],
                name=cname,
            )
    return constraints


def add_c_hydro_limit_weekly(
    model: gp.Model,
    phydro: gp.tupledict,
    step_k: int,
    sim_horizon: int,
    hydro_units: list,
    hydro_capacity: pd.DataFrame,
    hydro_capacity_min: pd.DataFrame,
) -> gp.tupledict:
    """
    Defines the weekly limit (lower and upper bounds) of hydro generation.
    Assumes that a certain amount of water is available for hydropower generation each day.

    Args:
        model (gp.Model): The optimization model
        phydro (gp.tupledict): The power output of hydro units
        step_k (int): The current iteration
        sim_horizon (int): The simulation horizon
        hydro_units (list): The list of hydro units
        hydro_capacity (pd.DataFrame): The capacity of the hydro unit

    Returns:
        gp.tupledict: The constraints for the weekly hydro limit

    Raises:
        ValueError: If the simulation horizon is not divisible by 24

    """
    if len(hydro_units) == 0:
        return gp.tupledict()

    # When formulating with weekly hydropower, sim_horizon must be divisible
    # by 168 because the hydro_capacity is weekly.
    if sim_horizon % 168 != 0:
        raise ValueError(
            "The simulation horizon must be divisible by 168 when using weekly hydropower capacity."
        )
    constraints = gp.tupledict()
    max_week = sim_horizon // 168
    for week in range(step_k, step_k + max_week):
        for hydro_unit in hydro_units:
            cname = f"hydro_limit_weekly_ub[{hydro_unit},{week}]"
            cname_min = f"hydro_limit_weekly_lb[{hydro_unit},{week}]"
            current_week = week - step_k + 1

            # Upper bound constraint
            constraints[cname] = model.addConstr(
                gp.quicksum(
                    phydro[hydro_unit, t]
                    for t in range(1 + (current_week - 1) * 168, current_week * 168 + 1)
                )
                <= hydro_capacity.loc[week, hydro_unit],
                name=cname,
            )

            # Lower bound constraint
            constraints[cname_min] = model.addConstr(
                gp.quicksum(
                    phydro[hydro_unit, t]
                    for t in range(1 + (current_week - 1) * 168, current_week * 168 + 1)
                )
                >= hydro_capacity_min.loc[week, hydro_unit],
                name=cname_min,
            )
    return constraints
