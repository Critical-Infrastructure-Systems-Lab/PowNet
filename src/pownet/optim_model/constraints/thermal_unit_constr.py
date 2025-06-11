"""thermal_unit_constr.py: Constraints for thermal units"""

import gurobipy as gp
import pandas as pd


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
            u[unit, 1]
            # Last hour of the previous iteration
            - initial_u[unit] == v[unit, 1] - w[unit, 1]
            for unit in thermal_units
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
            u[unit, t] - u[unit, t - 1] == v[unit, t] - w[unit, t]
            for unit in thermal_units
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
            pthermal[unit, t] == p[unit, t] + thermal_min_capacity[unit] * u[unit, t]
            for unit in thermal_units
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
            pbar[unit, t] == p[unit, t] + spin[unit, t]
            for unit in thermal_units
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

    Args:
        model (gp.Model): The optimization model
        p (gp.tupledict): The power output above the minimum capacity
        pbar (gp.tupledict): The maximum power output above the minimum capacity
        timesteps (range): The range of timesteps
        thermal_units (list): The list of thermal units

    Returns:
        gp.tupledict: The constraints for the power output above the minimum capacity
        and the maximum power output above the minimum capacity
    """
    return model.addConstrs(
        (pbar[unit, t] >= p[unit, t] for unit in thermal_units for t in timesteps),
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
            thermal_min_capacity[unit] * u[unit, t] <= pthermal[unit, t]
            for unit in thermal_units
            for t in timesteps
        ),
        name="pthermal_lb",
    )


def add_c_link_pu_upper(
    model: gp.Model,
    pbar: gp.tupledict,
    u: gp.tupledict,
    timesteps: range,
    step_k: int,
    thermal_units: list,
    thermal_min_capacity: dict,
    thermal_derated_capacity: pd.DataFrame,
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
    for unit in thermal_units:
        cname = f"minDownInit[{unit}]"
        # Find the min between the required downtime and the simulation horizon
        min_DT = min(initial_min_off[unit], sim_horizon)
        constraints[cname] = model.addConstr(
            u.sum(unit, range(1, min_DT + 1)) == 0,
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
    for unit in thermal_units:
        cname = f"minUpInit[{unit}]"
        # Find the min between the required uptime and the simulation horizon
        min_UT = min(initial_min_on[unit], sim_horizon)
        constraints[cname] = model.addConstr(
            u.sum(unit, range(1, min_UT + 1)) == min_UT,
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
    for unit in thermal_units:
        TD_g = TD[unit]
        for t in range(TD_g, sim_horizon + 1):
            cname = f"minDown[{unit},{t}]"
            LHS = gp.quicksum([w[unit, i] for i in range(t - TD_g + 1, t + 1)])
            constraints[cname] = model.addConstr(LHS <= 1 - u[unit, t], name=cname)
    return constraints


def add_c_min_up(
    model: gp.Model,
    u: gp.tupledict,
    v: gp.tupledict,
    sim_horizon: int,
    thermal_units: list,
    TU: dict,
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
    for unit in thermal_units:
        TU_g = TU[unit]
        for t in range(TU_g, sim_horizon + 1):
            cname = f"minUp[{unit},{t}]"
            LHS = gp.quicksum([v[unit, i] for i in range(t - TU_g + 1, t + 1)])
            constraints[cname] = model.addConstr(LHS <= u[unit, t], name=cname)
    return constraints


def add_c_peak_down_bound(
    model: gp.Model,
    p: gp.tupledict,
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
    """Shutdown capability based on Gentile et al. (2017) for TU=1 units.
    Implements Eq. (1) for t=1 and Eq. (4) for t in [2, T-1].

    Args:
        model (gp.Model): The optimization model
        p (gp.tupledict): The power output above the minimum capacity
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
    constraints = gp.tupledict()
    for unit_g in thermal_units:
        if TU.get(unit_g) == 1:  # Check if TU entry exists and is 1
            # For t = 1 (Gentile Eq. 1)
            # p_1 <= (P_bar_1 - P_underline)u_1 - (P_bar_1 - SD)w_2
            if sim_horizon >= 1:
                t = 1
                # Current P_bar for period t
                p_bar_t = thermal_derated_capacity.loc[t + (step_k - 1) * 24, unit_g]
                p_underline = thermal_min_capacity[unit_g]

                if sim_horizon >= 2:  # w[unit_g, 2] must be valid for Eq. (1)
                    constraints[unit_g, t, "GentilePeakDown_t1"] = model.addConstr(
                        p[unit_g, t]
                        <= (p_bar_t - p_underline) * u[unit_g, t]
                        - (p_bar_t - SD[unit_g]) * w[unit_g, t + 1],  # t+1 is 2
                        name=f"GentilePeakDown_t1[{unit_g},{t}]",
                    )
                # If sim_horizon == 1, Eq. (1) which uses w_2 is not applicable as written.
                # Gentile's formulation implies T >= 2 for this specific equation.

            # For t in [2, T-1] (Gentile Eq. 4)
            # p_t <= (P_bar_t - P_underline)u_t - (P_bar_t - SD)w_{t+1} - max(0, SD-SU)v_t
            # Loop range(2, sim_horizon) covers t from 2 to sim_horizon - 1
            for t in range(2, sim_horizon):
                p_bar_t = thermal_derated_capacity.loc[t + (step_k - 1) * 24, unit_g]
                p_underline = thermal_min_capacity[unit_g]

                constraints[unit_g, t, "GentilePeakDown_intermediate"] = (
                    model.addConstr(
                        p[unit_g, t]
                        <= (p_bar_t - p_underline) * u[unit_g, t]
                        - (p_bar_t - SD[unit_g]) * w[unit_g, t + 1]
                        - max(0, SD[unit_g] - SU[unit_g]) * v[unit_g, t],
                        name=f"GentilePeakDown_intermediate[{unit_g},{t}]",
                    )
                )
    return constraints


def add_c_peak_up_bound(
    model: gp.Model,
    p: gp.tupledict,
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
    """Startup capability based on Gentile et al. (2017) for TU=1 units.
    Implements Eq. (5) for t in [2, T-1] and Eq. (3) for t=T.
    Constraint applies to p (power above minimum output).

    Args:
        model (gp.Model): The optimization model
        p (gp.tupledict): The power output above the minimum capacity
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
    constraints = gp.tupledict()
    for unit_g in thermal_units:
        if TU.get(unit_g) == 1:  # Check if TU entry exists and is 1
            # For t in [2, T-1] (Gentile Eq. 5)
            # p_t <= (P_bar_t - P_underline)u_t - (P_bar_t - SU)v_t - max(0, SU-SD)w_{t+1}
            # Loop range(2, sim_horizon) covers t from 2 to sim_horizon - 1
            for t in range(2, sim_horizon):
                p_bar_t = thermal_derated_capacity.loc[t + (step_k - 1) * 24, unit_g]
                p_underline = thermal_min_capacity[unit_g]

                constraints[unit_g, t, "GentilePeakUp_intermediate"] = model.addConstr(
                    p[unit_g, t]
                    <= (p_bar_t - p_underline) * u[unit_g, t]
                    - (p_bar_t - SU[unit_g]) * v[unit_g, t]
                    - max(0, SU[unit_g] - SD[unit_g]) * w[unit_g, t + 1],
                    name=f"GentilePeakUp_intermediate[{unit_g},{t}]",
                )

            # For t = T (sim_horizon) (Gentile Eq. 3)
            # p_T <= (P_bar_T - P_underline)u_T - (P_bar_T - SU)v_T
            if (
                sim_horizon >= 1
            ):  # This constraint applies if there's at least one period
                t = sim_horizon
                p_bar_t = thermal_derated_capacity.loc[t + (step_k - 1) * 24, unit_g]
                p_underline = thermal_min_capacity[unit_g]

                constraints[unit_g, t, "GentilePeakUp_finalT"] = model.addConstr(
                    p[unit_g, t]
                    <= (p_bar_t - p_underline) * u[unit_g, t]
                    - (p_bar_t - SU[unit_g]) * v[unit_g, t],
                    name=f"GentilePeakUp_finalT[{unit_g},{t}]",
                )
    return constraints


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
            initial_p[unit] - p[unit, 1]
            <= (SD[unit] - thermal_min_capacity[unit] - RD[unit]) * w[unit, 1]
            + RD[unit] * initial_u[unit]
            for unit in thermal_units
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
            p[unit, t - 1] - p[unit, t]
            <= (SD[unit] - thermal_min_capacity[unit] - RD[unit]) * w[unit, t]
            + RD[unit] * u[unit, t - 1]
            for unit in thermal_units
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
            pbar[unit, 1] - initial_p[unit]
            <= (SU[unit] - thermal_min_capacity[unit] - RU[unit]) * v[unit, 1]
            + RU[unit] * u[unit, 1]
            for unit in thermal_units
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

    Returns:
        gp.tupledict: The constraints for the ramp-up at t>1

    """
    return model.addConstrs(
        (
            pbar[unit, t] - p[unit, t - 1]
            <= (SU[unit] - thermal_min_capacity[unit] - RU[unit]) * v[unit, t]
            + RU[unit] * u[unit, t]
            for unit in thermal_units
            for t in range(2, sim_horizon + 1)
        ),
        name="rampUp",
    )
