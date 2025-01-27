"""constraint.py: Contains functions for constructing the objective function and constraints of the optimization model.
Throughout this module, the number 24 is the number of hours in a day. This number is used to calculate the index of the next day in the optimization model."""

import gurobipy as gp
import networkx as nx
import pandas as pd


def get_capacity_value(t: int, unit: str, step_k: int, capacity_df) -> float:
    value = capacity_df.loc[t + (step_k - 1) * 24, unit]
    if isinstance(value, pd.Series):
        return value.iloc[0]
    return value


"""Functions for thermal-unit constraints
"""


def add_c_link_uvw_init(
    model: gp.Model,
    u: gp.tupledict,
    v: gp.tupledict,
    w: gp.tupledict,
    thermal_units: list,
    initial_u: dict,
) -> gp.tupledict:
    """Equation 2 of Kneuven et al (2019) based on Garver (1962).
    Three binary variables u (status), v (startup), and w (shutdown) are used to model the status of a thermal unit.
    Their logical relationship is defined by this equation. The initial condition is also considered here.

    Args:
        model (gp.Model): The optimization model
        u (gp.tupledict): The status of the thermal unit
        v (gp.tupledict): The startup of the thermal unit
        w (gp.tupledict): The shutdown of the thermal unit
        thermal_units (list): The list of thermal units
        initial_u (dict): The initial status of the thermal unit

    Returns:
        gp.tupledict: The constraints for the initial condition

    """
    return model.addConstrs(
        (
            u[unit_g, 1]
            # Last hour of the previous iteration
            - initial_u[unit_g] == v[unit_g, 1] - w[unit_g, 1]
            for unit_g in thermal_units
        ),
        name="link_uvw_init",
    )


def add_c_link_uvw(
    model: gp.Model,
    u: gp.tupledict,
    v: gp.tupledict,
    w: gp.tupledict,
    sim_horizon: int,
    thermal_units: list,
) -> gp.tupledict:
    """Equation 2 of Kneuven et al (2019) based on Garver (1962).
    Three binary variables u (status), v (startup), and w (shutdown) are used to model the status of a thermal unit.
    Their logical relationship is defined by this equation.

    Args:
        model (gp.Model): The optimization model
        u (gp.tupledict): The status of the thermal unit
        v (gp.tupledict): The startup of the thermal unit
        w (gp.tupledict): The shutdown of the thermal unit
        sim_horizon (int): The simulation horizon
        thermal_units (list): The list of thermal units

    Returns:
        gp.tupledict: The constraints for the subsequent time

    """
    # Only consider the second timestep onwards
    return model.addConstrs(
        (
            u[unit_g, t] - u[unit_g, t - 1] == v[unit_g, t] - w[unit_g, t]
            for unit_g in thermal_units
            for t in range(2, sim_horizon + 1)
        ),
        name="link_uvw",
    )


def add_c_link_pthermal(
    model: gp.Model,
    pthermal: gp.tupledict,
    p: gp.tupledict,
    u: gp.tupledict,
    timesteps: range,
    thermal_units: list,
    thermal_min_capacity: dict,
) -> gp.tupledict:
    """Equation 12 of Kneuven et al (2019). This establishes the power output above
    the minimum capacity, which is a variable promoted by Morales-Espana et al. (2013).

    Args:
        model (gp.Model): The optimization model
        pthermal (gp.tupledict): The power output
        p (gp.tupledict): The power output above the minimum capacity
        u (gp.tupledict): The status of the thermal unit
        timesteps (range): The range of timesteps
        thermal_units (list): The list of thermal units
        thermal_min_capacity (dict): The minimum capacity of the thermal unit

    Returns:
        gp.tupledict: The constraints for the power output above the minimum capacity

    """
    return model.addConstrs(
        (
            pthermal[unit_g, t]
            == p[unit_g, t] + thermal_min_capacity[unit_g] * u[unit_g, t]
            for unit_g in thermal_units
            for t in timesteps
        ),
        name="link_pthermal",
    )


def add_c_link_spin(
    model: gp.Model,
    p: gp.tupledict,
    pbar: gp.tupledict,
    spin: gp.tupledict,
    timesteps: range,
    thermal_units,
) -> gp.tupledict:
    """Equation 14 of Kneuven et al (2019). Establish the relationship among p, pbar, and spin:
    pbar = p + spin
    Note that pbar and p are variables defines as MW above the minimum capacity.

    Args:
        model (gp.Model): The optimization model
        p (gp.tupledict): The power output above the minimum capacity
        pbar (gp.tupledict): The maximum power output above the minimum capacity
        spin (gp.tupledict): The spinning reserve
        timesteps (range): The range of timesteps
        thermal_units (list): The list of thermal units

    Returns:
        gp.tupledict: The constraints for the power output above the minimum capacity

    """
    return model.addConstrs(
        (
            pbar[unit_g, t] == p[unit_g, t] + spin[unit_g, t]
            for unit_g in thermal_units
            for t in timesteps
        ),
        name="link_spin",
    )


def add_c_link_ppbar(
    model: gp.Model,
    p: gp.tupledict,
    pbar: gp.tupledict,
    timesteps: range,
    thermal_units: list,
) -> gp.tupledict:
    """
    Equation 17 of Kneuven et al (2019). Since pbar = p + spin, if we do not implement
    the spin variable, then p <= pbar.
    """
    return model.addConstrs(
        (
            pbar[unit_g, t] >= p[unit_g, t]
            for t in timesteps
            for unit_g in thermal_units
        ),
        name="link_ppbar",
    )


def add_c_link_pu_lower(
    model: gp.Model,
    pthermal: gp.tupledict,
    u: gp.tupledict,
    timesteps: range,
    thermal_units: list,
    thermal_min_capacity: dict,
) -> gp.tupledict:
    """Equation 18 of Kneuven et al (2019) based on Carrion and Arroyo (2006).
    Set the lower bound of the dispatched power.

    Args:
        model (gp.Model): The optimization model
        pthermal (gp.tupledict): The dispatched power
        u (gp.tupledict): The status of the thermal unit
        timesteps (range): The range of timesteps
        thermal_units (list): The list of thermal units
        thermal_min_capacity (dict): The minimum capacity of the thermal unit

    Returns:
        gp.tupledict: The constraints for the lower bound of the dispatched power
    """
    return model.addConstrs(
        (
            thermal_min_capacity[unit_g] * u[unit_g, t] <= pthermal[unit_g, t]
            for unit_g in thermal_units
            for t in timesteps
        ),
        name="pthermal_lb",
    )


def add_c_link_pu_upper(
    model=gp.Model,
    pbar=gp.tupledict,
    u=gp.tupledict,
    timesteps=range,
    step_k=int,
    thermal_units=list,
    thermal_min_capacity=dict,
    thermal_derated_capacity=pd.DataFrame,
) -> gp.tupledict:
    """Equation 18 of Knueven et al (2019) based on Carrion and Arroyo (2006).
    Set the upper bound of the dispatched power.

    Args:
        model (gp.Model): The optimization model
        pbar (gp.tupledict): The maximum power output above the minimum capacity
        u (gp.tupledict): The status of the thermal unit
        timesteps (range): The range of timesteps
        step_k (int): The current iteration
        thermal_units (list): The list of thermal units
        thermal_min_capacity (dict): The minimum capacity of the thermal unit
        thermal_derated_capacity (pd.DataFrame): The derated capacity of the thermal unit

    Returns:
        gp.tupledict: The constraints for the upper bound of the dispatched power

    """
    return model.addConstrs(
        (
            pbar[unit, t] + thermal_min_capacity[unit] * u[unit, t]
            <= thermal_derated_capacity.loc[t + (step_k - 1) * 24, unit] * u[unit, t]
            for unit in thermal_units
            for t in timesteps
        ),
        name="pthermal_ub",
    )


def add_c_thermal_curtail(
    model: gp.Model,
    pthermal: gp.tupledict,
    pthermal_curtail: gp.tupledict,
    pcharge: gp.tupledict,
    timesteps: range,
    step_k: int,
    thermal_must_take_units: list,
    thermal_derated_capacity: pd.DataFrame,
    ess_attached: dict,
) -> gp.tupledict:
    """For must-take thermal units, the curtailment is the difference between the derated capacity and the dispatched power."""
    constraints = gp.tupledict()
    for unit in thermal_must_take_units:
        has_storage = unit in ess_attached
        for t in timesteps:
            pcharge_unit_t = 0
            if has_storage:
                # A unit may have multiple storage systems
                for storage_unit in ess_attached[unit]:
                    pcharge_unit_t += pcharge[storage_unit, t]

            cname = f"thermal_curtail[{unit},{t}]"
            constraints[cname] = model.addConstr(
                (
                    pthermal[unit, t] + pthermal_curtail[unit, t] + pcharge_unit_t
                    == thermal_derated_capacity.loc[t + (step_k - 1) * 24, unit]
                ),
                name=cname,
            )
    return constraints


def add_c_min_down_init(
    model: gp.Model,
    u: gp.tupledict,
    sim_horizon: int,
    thermal_units: list,
    initial_min_off: dict,
) -> gp.tupledict:
    """Equation 3b of Kneuven et al (2019). Minimum downtime of thermal units at t=1.

    Args:
        model (gp.Model): The optimization model
        u (gp.tupledict): The status of the thermal unit
        sim_horizon (int): The simulation horizon
        thermal_units (list): The list of thermal units
        initial_min_off (dict): The remaining minimum downtime of the thermal unit from the previous iteration

    Returns:
        gp.tupledict: The constraints for the minimum downtime of thermal units at t=1

    """
    constraints = gp.tupledict()
    for unit_g in thermal_units:
        cname = f"minDownInit[{unit_g}]"
        # Find the min between the required downtime and the simulation horizon
        min_DT = min(initial_min_off[unit_g], sim_horizon)
        constraints[cname] = model.addConstr(
            u.sum(unit_g, range(1, min_DT + 1)) == 0,
            name=cname,
        )
    return constraints


def add_c_min_up_init(
    model: gp.Model,
    u: gp.tupledict,
    sim_horizon: int,
    thermal_units: list,
    initial_min_on: dict,
) -> gp.tupledict:
    """Equation 3a of Kneuven et al (2019). Minimum uptime of thermal units at t=1.

    Args:
        model (gp.Model): The optimization model
        u (gp.tupledict): The status of the thermal unit
        sim_horizon (int): The simulation horizon
        thermal_units (list): The list of thermal units
        initial_min_on (dict): The remaining minimum uptime of the thermal unit from the previous iteration

    Returns:
        gp.tupledict: The constraints for the minimum uptime of thermal units at t=1

    """
    constraints = gp.tupledict()
    for unit_g in thermal_units:
        cname = f"minUpInit[{unit_g}]"
        # Find the min between the required uptime and the simulation horizon
        min_UT = min(initial_min_on[unit_g], sim_horizon)
        constraints[cname] = model.addConstr(
            u.sum(unit_g, range(1, min_UT + 1)) == min_UT,
            name=cname,
        )
    return constraints


def add_c_min_down(
    model: gp.Model,
    u: gp.tupledict,
    w: gp.tupledict,
    sim_horizon: int,
    thermal_units: list,
    TD: dict,
) -> gp.tupledict:
    """Equation 5 of Kneuven et al (2019) based on Malkin (2003) and Rajan and Takriti (2005).
    Minimum downtime of thermal units at t>1.

    Args:
        model (gp.Model): The optimization model
        u (gp.tupledict): The status of the thermal unit
        w (gp.tupledict): The shutdown of the thermal unit
        sim_horizon (int): The simulation horizon
        thermal_units (list): The list of thermal units
        TD (dict): The minimum downtime of thermal units

    Returns:
        gp.tupledict: The constraints for the minimum downtime of thermal units at t>1

    """
    constraints = gp.tupledict()
    for unit_g in thermal_units:
        TD_g = TD[unit_g]
        for t in range(TD_g, sim_horizon + 1):
            cname = f"minDown[{unit_g},{t}]"
            LHS = gp.quicksum([w[unit_g, i] for i in range(t - TD_g + 1, t + 1)])
            constraints[cname] = model.addConstr(LHS <= 1 - u[unit_g, t], name=cname)
    return constraints


def add_c_min_up(
    model=gp.Model,
    u=gp.tupledict,
    v=gp.tupledict,
    sim_horizon=int,
    thermal_units=list,
    TU=dict,
) -> gp.tupledict:
    """Equation 4 of Kneuven et al (2019) based on Malkin (2003) and Rajan and Takriti (2005).
    Minimum uptime of thermal units at t>1.

    Args:
        model (gp.Model): The optimization model
        u (gp.tupledict): The status of the thermal unit
        v (gp.tupledict): The startup of the thermal unit
        sim_horizon (int): The simulation horizon
        thermal_units (list): The list of thermal units
        TU (dict): The minimum uptime of thermal units

    Returns:
        gp.tupledict: The constraints for the minimum uptime of thermal units at t>1

    """
    constraints = gp.tupledict()
    for unit_g in thermal_units:
        TU_g = TU[unit_g]
        for t in range(TU_g, sim_horizon + 1):
            cname = f"minUp[{unit_g},{t}]"
            LHS = gp.quicksum([v[unit_g, i] for i in range(t - TU_g + 1, t + 1)])
            constraints[cname] = model.addConstr(LHS <= u[unit_g, t], name=cname)
    return constraints


def add_c_peak_down_bound(
    model: gp.Model,
    p: gp.tupledict,
    spin: gp.tupledict,
    u: gp.tupledict,
    v: gp.tupledict,
    w: gp.tupledict,
    sim_horizon: int,
    step_k: int,
    thermal_units: list,
    thermal_min_capacity: dict,
    thermal_derated_capacity: pd.DataFrame,
    SD: dict,
    SU: dict,
    TU: dict,
) -> gp.tupledict:
    """Equation 23b of Kneuven et al (2019) based on Gentile et al. (2017).
    When a peaking thermal unit (TD=1) is shutting down, its power output is limited by
    the shutdown rate (SD).

    Args:
        model (gp.Model): The optimization model
        p (gp.tupledict): The power output above the minimum capacity
        spin (gp.tupledict): The spinning reserve
        u (gp.tupledict): The status of the thermal unit
        v (gp.tupledict): The startup of the thermal unit
        w (gp.tupledict): The shutdown of the thermal unit
        sim_horizon (int): The simulation horizon
        step_k (int): The current iteration
        thermal_units (list): The list of thermal units
        thermal_min_capacity (dict): The minimum capacity of the thermal unit
        thermal_derated_capacity (pd.DataFrame): The derated capacity of the thermal unit
        SD (dict): The shutdown rate of the thermal unit
        SU (dict): The startup rate of the thermal unit
        TU (dict): The minimum uptime of thermal units

    Returns:
        gp.tupledict: The constraints for the peak down bound

    """
    return model.addConstrs(
        (
            p[unit_g, t] + spin[unit_g, t]
            <= (
                thermal_derated_capacity.loc[t + (step_k - 1) * 24, unit_g]
                - thermal_min_capacity[unit_g]
            )
            * u[unit_g, t]
            - (thermal_derated_capacity.loc[t + (step_k - 1) * 24, unit_g] - SD[unit_g])
            * w[unit_g, t + 1]
            - max(0, (SD[unit_g] - SU[unit_g])) * v[unit_g, t]
            for t in range(
                1, sim_horizon
            )  # The constraints index w at t+1, so we stop at T-1
            for unit_g in thermal_units
            if TU[unit_g] == 1
        ),
        name="peakDownBnd",
    )


def add_c_peak_up_bound(
    model: gp.Model,
    p: gp.tupledict,
    spin: gp.tupledict,
    u: gp.tupledict,
    v: gp.tupledict,
    w: gp.tupledict,
    sim_horizon: int,
    step_k: int,
    thermal_units: list,
    thermal_min_capacity: dict,
    thermal_derated_capacity: pd.DataFrame,
    SD: dict,
    SU: dict,
    TU: dict,
) -> gp.tupledict:
    """Equation 23a of Kneuven et al (2019) based on Gentile et al. (2017).
    When a peaking thermal unit (TU=1) is starting up, its power output is limited by
    the startup rate (SU).

    Args:
        model (gp.Model): The optimization model
        p (gp.tupledict): The power output above the minimum capacity
        spin (gp.tupledict): The spinning reserve
        u (gp.tupledict): The status of the thermal unit
        v (gp.tupledict): The startup of the thermal unit
        w (gp.tupledict): The shutdown of the thermal unit
        sim_horizon (int): The simulation horizon
        step_k (int): The current iteration
        thermal_units (list): The list of thermal units
        thermal_min_capacity (dict): The minimum capacity of the thermal unit
        thermal_derated_capacity (pd.DataFrame): The derated capacity of the thermal unit
        SD (dict): The shutdown rate of the thermal unit
        SU (dict): The startup rate of the thermal unit
        TU (dict): The minimum uptime of thermal units

    Returns:
        gp.tupledict: The constraints for the peak up bound

    """
    return model.addConstrs(
        (
            p[unit_g, t] + spin[unit_g, t]
            <= (
                thermal_derated_capacity.loc[t + (step_k - 1) * 24, unit_g]
                - thermal_min_capacity[unit_g]
            )
            * u[unit_g, t]
            - (thermal_derated_capacity.loc[t + (step_k - 1) * 24, unit_g] - SU[unit_g])
            * v[unit_g, t]
            - max(0, (SU[unit_g] - SD[unit_g])) * w[unit_g, t + 1]
            for t in range(1, sim_horizon)  # The constraints index w at t+1
            for unit_g in thermal_units
            if TU[unit_g] == 1
        ),
        name="peakUpBnd",
    )


def add_c_ramp_down_init(
    model: gp.Model,
    p: gp.tupledict,
    w: gp.tupledict,
    thermal_units: list,
    initial_p: dict,
    initial_u: dict,
    thermal_min_capacity: dict,
    RD: dict,
    SD: dict,
) -> gp.tupledict:
    """
    Equation 36 of Kneuven et al (2019) based on Damci-Kurt et al. (2016).
    Ramp-down constraint at t=1. The equation was modified to be expressed
    in terms of power output above the minimum capacity.

    Args:
        model (gp.Model): The optimization model
        p (gp.tupledict): The power output above the minimum capacity
        w (gp.tupledict): The shutdown of the thermal unit
        thermal_units (list): The list of thermal units
        initial_p (dict): The initial power output above the minimum capacity
        initial_u (dict): The initial status of the thermal unit
        thermal_min_capacity (dict): The minimum capacity of the thermal unit
        RD (dict): The ramp-down rate of the thermal unit
        SD (dict): The shutdown rate of the thermal unit

    Returns:
        gp.tupledict: The constraints for the ramp-down at t=1

    """
    # Ramping when t=1 is dependent on the initial condition at t=0
    return model.addConstrs(
        (
            initial_p[unit_g] - p[unit_g, 1]
            <= (SD[unit_g] - thermal_min_capacity[unit_g] - RD[unit_g]) * w[unit_g, 1]
            + RD[unit_g] * initial_u[unit_g]
            for unit_g in thermal_units
        ),
        name="rampDownInit",
    )


def add_c_ramp_down(
    model: gp.Model,
    p: gp.tupledict,
    u: gp.tupledict,
    w: gp.tupledict,
    sim_horizon: int,
    thermal_units: list,
    thermal_min_capacity: dict,
    RD: dict,
    SD: dict,
) -> gp.tupledict:
    """Equation 36 of Kneuven et al (2019) based on Damci-Kurt et al. (2016).
    Ramp-down constraint at t>1. The equation was modified to be expressed
    in terms of power output above the minimum capacity.

    Args:
        model (gp.Model): The optimization model
        p (gp.tupledict): The power output above the minimum capacity
        u (gp.tupledict): The status of the thermal unit
        w (gp.tupledict): The shutdown of the thermal unit
        sim_horizon (int): The simulation horizon
        thermal_units (list): The list of thermal units
        thermal_min_capacity (dict): The minimum capacity of the thermal unit
        RD (dict): The ramp-down rate of the thermal unit
        SD (dict): The shutdown rate of the thermal unit

    Returns:
        gp.tupledict: The constraints for the ramp-down at t>1

    """
    return model.addConstrs(
        (
            p[unit_g, t - 1] - p[unit_g, t]
            <= (SD[unit_g] - thermal_min_capacity[unit_g] - RD[unit_g]) * w[unit_g, t]
            + RD[unit_g] * u[unit_g, t - 1]
            for unit_g in thermal_units
            for t in range(2, sim_horizon + 1)
        ),
        name="rampDown",
    )


def add_c_ramp_up_init(
    model: gp.Model,
    pbar: gp.tupledict,
    u: gp.tupledict,
    v: gp.tupledict,
    thermal_units: list,
    initial_p: dict,
    thermal_min_capacity: dict,
    RU: dict,
    SU: dict,
) -> gp.tupledict:
    """Equation 35 of Kneuven et al (2019) based on Damci-Kurt et al. (2016).
    Ramp-up constraint at t=1. The equation was modified to be expressed
    in terms of power output above the minimum capacity.

    Args:
        model (gp.Model): The optimization model
        pbar (gp.tupledict): The maximum power output above the minimum capacity
        u (gp.tupledict): The status of the thermal unit
        v (gp.tupledict): The startup of the thermal unit
        thermal_units (list): The list of thermal units
        initial_p (dict): The initial power output above the minimum capacity
        thermal_min_capacity (dict): The minimum capacity of the thermal unit
        RU (dict): The ramp-up rate of the thermal unit
        SU (dict): The startup rate of the thermal unit

    Returns:
        gp.tupledict: The constraints for the ramp-up at t=1

    """
    # Ramp up when t=1 is dependent on the initial condition at t=0
    return model.addConstrs(
        (
            pbar[unit_g, 1] - initial_p[unit_g]
            <= (SU[unit_g] - thermal_min_capacity[unit_g] - RU[unit_g]) * v[unit_g, 1]
            + RU[unit_g] * u[unit_g, 1]
            for unit_g in thermal_units
        ),
        name="rampUpInit",
    )


def add_c_ramp_up(
    model: gp.Model,
    p: gp.tupledict,
    pbar: gp.tupledict,
    u: gp.tupledict,
    v: gp.tupledict,
    sim_horizon: int,
    thermal_units: list,
    thermal_min_capacity: dict,
    RU: dict,
    SU: dict,
) -> gp.tupledict:
    """Equation 35 of Kneuven et al (2019) based on Damci-Kurt et al. (2016).
    Ramp-up constraint at t>1. The equation was modified to be expressed
    in terms of power output above the minimum capacity.

    Args:
        model (gp.Model): The optimization model
        p (gp.tupledict): The power output above the minimum capacity
        pbar (gp.tupledict): The maximum power output above the minimum capacity
        u (gp.tupledict): The status of the thermal unit
        v (gp.tupledict): The startup of the thermal unit
        sim_horizon (int): The simulation horizon
        thermal_units (list): The list of thermal units
        thermal_min_capacity (dict): The minimum capacity of the thermal unit
        RU (dict): The ramp-up rate of the thermal unit
        SU (dict): The startup rate of the thermal unit

    """
    return model.addConstrs(
        (
            pbar[unit_g, t] - p[unit_g, t - 1]
            <= (SU[unit_g] - thermal_min_capacity[unit_g] - RU[unit_g]) * v[unit_g, t]
            + RU[unit_g] * u[unit_g, t]
            for unit_g in thermal_units
            for t in range(2, sim_horizon + 1)
        ),
        name="rampUp",
    )


"""Functions for power flow"""


def add_c_link_shortfall(
    model: gp.Model,
    load_shortfall: gp.tupledict,
    p_pmismatch: gp.tupledict,
    n_pmismatch: gp.tupledict,
    timesteps: range,
) -> gp.tupledict:
    """Equation 66 of Kneuven et al (2019). Supply-demand is balanced with an equality constraint.
    To prevent model infeasibility, we introduce a variable to represent the load shortfall s_n(t),
    which can be expressed in terms of non-negative variables: the positive and negative power mismatch.

    Formula: s_n(t) = s_pos(t) - s_neg(t)

    Args:
        model (gp.Model): The optimization model
        load_shortfall (gp.tupledict): The load shortfall
        p_pmismatch (gp.tupledict): The positive power mismatch
        n_pmismatch (gp.tupledict): The negative power mismatch
        timesteps (range): The range of timesteps

    Returns:
        gp.tupledict: The constraints for the load shortfall

    """
    return model.addConstrs(
        load_shortfall[t] == p_pmismatch[t] - n_pmismatch[t] for t in timesteps
    )


def add_c_ref_node(
    model: gp.Model,
    theta: gp.tupledict,
    timesteps: range,
    max_demand_node: str,
) -> gp.tupledict:
    """Equation 64d of Kneuven et al (2019).
    Set the voltage angle at a reference node to zero. The reference node is typically the node with the highest demand.

    Args:
        model (gp.Model): The optimization model
        theta (gp.tupledict): The voltage angle
        timesteps (range): The range of timesteps
        max_demand_node (str): The node with the highest demand

    Returns:
        gp.tupledict: The constraints for the reference node
    """
    return model.addConstrs(
        (theta[max_demand_node, t] == 0 for t in timesteps),
        name="refNode",
    )


def add_c_angle_diff(
    model: gp.Model,
    flow: gp.tupledict,
    theta: gp.tupledict,
    timesteps: range,
    step_k: int,
    edges: list,
    susceptance: pd.DataFrame,
) -> gp.tupledict:
    """Equation 64a of Kneuven et al (2019) expresses the power flow in a transmission line
    as a function of the voltage angle difference between the two buses it connects.
    In DC-OPF, the real power flow in a transmission line is directly proportional
    to the difference in voltage angles.

    Note: If the voltage-angle variable is not implemented, then we can use the Kirchhoff formulation.

    Args:
        model (gp.Model): The optimization model
        flow (gp.tupledict): The power flow
        theta (gp.tupledict): The voltage angle
        timesteps (range): The range of timesteps
        step_k (int): The current iteration
        edges (list): The list of edges
        susceptance (pd.DataFrame): The susceptance matrix

    Returns:
        gp.tupledict: The constraints for the angle difference

    """
    return model.addConstrs(
        (
            flow[a, b, t]
            == susceptance.loc[t + (step_k - 1) * 24, (a, b)]
            * (theta[a, t] - theta[b, t])
            for (a, b) in edges
            for t in timesteps
        ),
        name="angleDiff",
    )


def add_c_kirchhoff(
    model: gp.Model,
    flow: gp.tupledict,
    timesteps: range,
    step_k: int,
    edges: list,
    cycle_map: dict,
    susceptance: pd.DataFrame,
) -> gp.tupledict:
    """Equation 23b in Horsch et al (2018). This constraint implements
    the Kirchhoff circuit laws directly on the flow variables.

    Note: This constraint replaces the voltage-angle difference formulation.

    Args:
        model (gp.Model): The optimization model
        flow (gp.tupledict): The power flow variable
        timesteps (range): The range of timesteps
        step_k (int): The current iteration
        edges (list): The list of edges
        cycle_map (dict): The cycle map (created by DataProcessor class)
        susceptance (pd.DataFrame): The susceptance matrix

    Returns:
        gp.tupledict: The constraints for the Kirchhoff circuit laws

    """
    cycle_incidence = pd.DataFrame(
        0,
        index=pd.MultiIndex.from_tuples(edges, names=["source", "sink"]),
        columns=cycle_map.keys(),
    )

    # The flow is positive with respect to the edges specified by the user
    for cycle_id, cycle in cycle_map.items():
        # Kirchhoff formulation requires summing along the loop direction.
        # If an arc is in cycle_graph and the input file, then 1. Otherwise, -1.
        cycle_graph = nx.path_graph(cycle)
        cycle_edges = list(cycle_graph.edges)
        # Append the last arc connecting the last node to the first node
        cycle_edges.append((cycle_edges[-1][-1], cycle_edges[0][0]))

        # We also need the reactance (susceptance) to calculate the factors in the cycle-incidence
        cycle_susceptance = pd.DataFrame()
        for cycle_edge in cycle_edges:
            if cycle_edge in edges:
                cycle_incidence.loc[cycle_edge, cycle_id] = 1
                cycle_susceptance = pd.concat(
                    [cycle_susceptance, susceptance[cycle_edge]], axis=1
                )
            else:
                cycle_incidence.loc[(cycle_edge[1], cycle_edge[0]), cycle_id] = -1
                cycle_susceptance = pd.concat(
                    [
                        cycle_susceptance,
                        susceptance[(cycle_edge[1], cycle_edge[0])],
                    ],
                    axis=1,
                )

        return model.addConstrs(
            (
                gp.quicksum(
                    (
                        cycle_incidence.loc[(a, b), cycle_id]
                        * 1
                        / cycle_susceptance.loc[t + (step_k - 1) * 24, [(a, b)]].values[
                            0
                        ]
                        * flow[a, b, t]
                    )
                    for (a, b) in cycle_susceptance.columns
                )
                == 0
                for t in timesteps
            ),
            name=f"kirchhoff_{cycle_id}",
        )


def add_c_flow_balance(
    model: gp.Model,
    pthermal: gp.tupledict,
    phydro: gp.tupledict,
    psolar: gp.tupledict,
    pwind: gp.tupledict,
    pimp: gp.tupledict,
    pcharge: gp.tupledict,
    pdis: gp.tupledict,
    pos_pmismatch: gp.tupledict,
    neg_pmismatch: gp.tupledict,
    flow: gp.tupledict,
    timesteps: range,
    step_k: int,
    thermal_units: list,
    hydro_units: list,
    solar_units: list,
    wind_units: list,
    import_units: list,
    nodes: list,
    node_edge: dict,
    node_generator: dict,
    charge_storage: dict,
    discharge_storage: dict,
    demand_nodes: list,
    demand: pd.DataFrame,
    line_loss_factor: float,
) -> gp.tupledict:
    """Equation 65 of Kneuven et al (2019). Supply-demand is balanced with an equality constraint.
    The power flow in the transmission line is also considered.

    Args:
        model (gp.Model): The optimization model
        pthermal (gp.tupledict): The power output of thermal units
        phydro (gp.tupledict): The power output of hydro units
        psolar (gp.tupledict): The power output of solar units
        pwind (gp.tupledict): The power output of wind units
        pimp (gp.tupledict): The power output of import units
        pcharge (gp.tupledict): The charge of energy storage units
        pdis (gp.tupledict): The discharge of energy storage units
        p_pmismatch (gp.tupledict): The positive power mismatch
        n_pmismatch (gp.tupledict): The negative power mismatch
        flow (gp.tupledict): The power flow
        timesteps (range): The range of timesteps
        step_k (int): The current iteration
        thermal_units (list): The list of thermal units
        hydro_units (list): The list of hydro units
        solar_units (list): The list of solar units
        wind_units (list): The list of wind units
        import_units (list): The list of import units
        nodes (list): The list of nodes
        node_edge (dict): The edges connected to a node
        node_generator (dict): The generators connected to a node
        charge_ess (dict): Storage units to charge from this node
        discharge_ess (dict): Storage units to discharge to this node
        demand_nodes (list): The list of demand nodes
        demand (pd.DataFrame): The demand data
        line_loss_factor (float): The transmission line loss factor

    Returns:
        gp.tupledict: The constraints for the power flow balance

    """

    def get_unit_generation(unit: str, t: int):
        if unit in thermal_units:
            return pthermal[unit, t]
        elif unit in hydro_units:
            return phydro[unit, t]
        elif unit in solar_units:
            return psolar[unit, t]
        elif unit in wind_units:
            return pwind[unit, t]
        elif unit in import_units:
            return pimp[unit, t]
        else:
            raise ValueError(
                f"PowNet: Unit {unit} not found in any of the generation types but is connected to the node."
            )

    constraints = gp.tupledict()
    # Impose a line loss factor to account for the inefficiency of the transmission line
    line_efficiency = 1 - line_loss_factor
    for t in timesteps:
        for node in nodes:
            generation = 0
            # Loops through generators located *in* the node (aggregated generation)
            for unit_g in node_generator[node]:
                generation += get_unit_generation(unit_g, t)

            # A grid storage system charges from this node
            storage_charge = 0
            if node in charge_storage:
                storage_systems = charge_storage[node]
                for storage_system in storage_systems:
                    storage_charge += pcharge[storage_system, t]

            # If an ESS is to inject into this node
            storage_discharge = 0
            if node in discharge_storage:
                storage_systems = discharge_storage[node]
                for storage_system in storage_systems:
                    storage_discharge += pdis[storage_system, t]

            # Get the demand of node n at time t
            if node in demand_nodes:
                demand_n_t = demand.loc[t + (step_k - 1) * 24, node]
                mismatch = pos_pmismatch[node, t] - neg_pmismatch[node, t]
            else:
                demand_n_t = 0
                mismatch = 0

            # Flow into a node is positive, while flow out is negative
            arc_flow = 0
            for x, y in node_edge[node]:
                if x == node:
                    arc_flow -= flow[x, y, t]
                elif y == node:
                    arc_flow += flow[x, y, t]

            # Given the above terms, we can specify the energy balance
            cname = f"flowBal[{node},{t}]"
            constraints[cname] = model.addConstr(
                (
                    generation * line_efficiency
                    + arc_flow
                    + mismatch
                    + storage_discharge  # Already factored in discharge efficiency is the ESS balance
                    == demand_n_t + storage_charge
                ),
                name=cname,
            )
    return constraints


"""Functions for the spinning-reserve requirement"""


def add_c_reserve_req_1(
    model: gp.Model,
    spin: gp.tupledict,
    spin_shortfall: gp.tupledict,
    timesteps: range,
    step_k: int,
    thermal_units: list,
    spin_requirement: pd.DataFrame,
) -> gp.tupledict:
    """Equation 68 of Kneuven et al (2019) based on Morales-España et al. (2013).
    System-wide spinning reserve requirement. The spinning reserve is the sum of
    the spinning reserve of all thermal units.

    NOTE: This formulation is suitable when we implement the spinning-reserve variable (spin).
    Only one reserve_requirement is constraint is needed.

    Args:
        model (gp.Model): The optimization model
        spin (gp.tupledict): The spinning reserve
        spin_shortfall (gp.tupledict): The spinning reserve shortfall
        timesteps (range): The range of timesteps
        step_k (int): The current iteration
        thermal_units (list): The list of thermal units
        spin_requirement (pd.DataFrame): The spinning reserve requirement at each hour (MW)

    Returns:
        gp.tupledict: The constraints for the spinning reserve requirement


    """
    return model.addConstrs(
        (
            gp.quicksum(spin[unit_g, t] for unit_g in thermal_units) + spin_shortfall[t]
            >= spin_requirement[t + (step_k - 1) * 24]
            for t in timesteps
        ),
        name="reserveReq1",
    )


def add_c_reserve_req_2(
    model: gp.Model,
    pbar: gp.tupledict,
    u: gp.tupledict,
    spin_shortfall: gp.tupledict,
    timesteps: range,
    step_k: int,
    thermal_units: list,
    thermal_min_capacity: dict,
    demand_nodes: list,
    demand: pd.DataFrame,
    spin_requirement: pd.Series,
) -> gp.tupledict:
    """Equation 67 of Kneuven et al (2019) based on Carrion and Arroyo (2006)
    and Ostrowski et al. (2012). The spinning reserve is expressed in terms of the
    maximum power output of all thermal units. Since the pbar in our implementation is
    actuallly pbar_tilde in Knueven et al (2019), we substitute pbar with pbar + u*min_capacity.

    NOTE: This formulation is suitable when we implement the pbar variable. Only one reserve_requirement
    is constraint is needed.

    Args:
        model (gp.Model): The optimization model
        pbar (gp.tupledict): The maximum power output above the minimum capacity
        u (gp.tupledict): The status of the thermal unit
        spin_shortfall (gp.tupledict): The spinning reserve shortfall
        timesteps (range): The range of timesteps
        step_k (int): The current iteration
        thermal_units (list): The list of thermal units
        thermal_min_capacity (dict): The minimum capacity of the thermal unit
        demand_nodes (list): The list of demand nodes
        demand (pd.DataFrame): The demand data
        spin_requirement (pd.Series): The spinning reserve requirement at each hour (MW)

    Returns:
        gp.tupledict: The constraints for the spinning reserve requirement

    """
    return model.addConstrs(
        (
            gp.quicksum(
                pbar[unit_g, t] + thermal_min_capacity[unit_g] * u[unit_g, t]
                for unit_g in thermal_units
            )
            + spin_shortfall[t]
            >= gp.quicksum(demand.loc[t + (step_k - 1) * 24, n] for n in demand_nodes)
            + spin_requirement[t + (step_k - 1) * 24]
            for t in timesteps
        ),
        name="reserveReq2",
    )


"""Functions for renewables and others"""


def add_c_hydro_limit_daily(
    model: gp.Model,
    phydro: gp.tupledict,
    step_k: int,
    sim_horizon: int,
    hydro_units: list,
    hydro_capacity: pd.DataFrame,
) -> gp.tupledict:
    """
    Defines the daily limit of hydro generation. Assumes that a certain amount of water is
    available for hydropower generation each day. In this case, the dataframe hydro_capacity has a length of 365 days
    instead of 8760 hours.

    Args:
        model (gp.Model): The optimization model
        phydro (gp.tupledict): The power output of hydro units
        step_k (int): The current iteration
        sim_horizon (int): The simulation horizon
        hydro_units (list): The list of hydro units
        hydro_capacity (pd.DataFrame): The capacity of the hydro unit

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
            cname = f"hydro_limit_daily[{hydro_unit},{day}]"
            current_day = day - step_k + 1
            constraints[cname] = model.addConstr(
                gp.quicksum(
                    phydro[hydro_unit, t]
                    for t in range(1 + (current_day - 1) * 24, current_day * 24 + 1)
                )
                <= hydro_capacity.loc[day, hydro_unit],
                name=cname,
            )
    return constraints


def add_c_link_unit_pu(
    model: gp.Model,
    pdispatch: gp.tupledict,
    u: gp.tupledict,
    type: str,  # "wind" or "solar" or "hydro" or "import"
    timesteps: range,
    step_k: int,
    units: list,
    capacity_df: pd.DataFrame,
) -> gp.tupledict:
    return model.addConstrs(
        (
            pdispatch[unit, t]
            <= u[unit, t] * get_capacity_value(t, unit, step_k, capacity_df)
            for unit in units
            for t in timesteps
        ),
        name=f"link_{type}_pu",
    )


def add_c_link_unit_pu_constant(
    model: gp.Model,
    pdispatch: gp.tupledict,
    u: gp.tupledict,
    timesteps: range,
    units: list,
    contracted_capacity: dict[str, float],
) -> gp.tupledict:
    """Similar to add_c_link_unit_pu, but the upper bound has a constant capacity"""
    return model.addConstrs(
        pdispatch[unit, t] <= u[unit, t] * contracted_capacity[unit]
        for unit in units
        for t in timesteps
    )


def add_c_unit_curtail_ess(
    model: gp.Model,
    pdispatch: gp.tupledict,
    pcurtail: gp.tupledict,
    pcharge: gp.tupledict,
    type: str,  # "wind" or "solar"
    timesteps: range,
    step_k: int,
    units: list,
    capacity_df: pd.DataFrame,
    ess_attached: dict[str, list[str]],
) -> gp.tupledict:

    constraints = gp.tupledict()
    for unit in units:
        has_storage = unit in ess_attached
        for t in timesteps:
            pcharge_unit_t = 0
            if has_storage:
                # A unit may have multiple storage systems
                for storage_unit in ess_attached[unit]:
                    pcharge_unit_t += pcharge[storage_unit, t]

            cname = f"{type}_curtail_ess[{unit},{t}]"
            constraints[cname] = model.addConstr(
                (
                    pdispatch[unit, t] + pcurtail[unit, t] + pcharge_unit_t
                    == get_capacity_value(t, unit, step_k, capacity_df)
                ),
                name=cname,
            )
    return constraints


def add_c_unit_curtail_ess_daily(
    model: gp.Model,
    pdispatch: gp.tupledict,
    pcurtail: gp.tupledict,
    pcharge: gp.tupledict,
    type: str,  # "wind" or "solar"
    sim_horizon: int,
    step_k: int,
    units: list,
    capacity_df: pd.DataFrame,
    ess_attached: dict[str, list[str]],
) -> gp.tupledict:

    constraints = gp.tupledict()
    max_day = sim_horizon // 24
    for unit in units:
        has_storage = unit in ess_attached
        for day in range(step_k, step_k + max_day):

            current_day = day - step_k + 1
            timesteps_in_day = range(1 + (current_day - 1) * 24, current_day * 24 + 1)

            pcharge_unit_day = 0
            if has_storage:
                # A unit may have multiple storage systems
                for storage_unit in ess_attached[unit]:
                    pcharge_unit_day += gp.quicksum(
                        pcharge[storage_unit, t] for t in timesteps_in_day
                    )

            cname = f"{type}_curtail_ess[{unit},{day}]"
            constraints[cname] = model.addConstr(
                (
                    gp.quicksum(
                        pdispatch[unit, t] + pcurtail[unit, t] for t in timesteps_in_day
                    )
                    + pcharge_unit_day
                    == capacity_df.loc[day, unit]
                ),
                name=cname,
            )
    return constraints


""" Energy storage constraints
"""


def add_c_link_ess_charge(
    model: gp.Model,
    pcharge: gp.tupledict,
    ucharge: gp.tupledict,
    timesteps: range,
    units: list,
    max_charge: dict[str, float],
) -> gp.tupledict:
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
