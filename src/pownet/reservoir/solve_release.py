"""
solve_release.py: Functions to solve the release given other values from a reservoir.
"""

import gurobipy as gp
import pandas as pd


def solve_release_from_target_storage(
    reservoir_name: str,
    start_day: int,
    end_day: int,
    max_release: float,
    max_storage: float,
    initial_storage: float,
    target_storage: pd.Series,
    minflow: pd.Series,
    total_inflow: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series, float]:
    """Build an optimization problem to find the optimal release from the reservoir.
    The objective is to minimize the storage deviation from the target storage with L1 norm.

    OBJECTIVE FUNCTION:
    min | target_storage - storage | + spill

    Rewrite this as:

    min sum_{day} sbar[day]
    s.t.
    - sbar[day] <= target_storage[day] - storage[day] <= sbar[day]

    CONSTRAINTS:

    """
    model = gp.Model(f"match_storage_{reservoir_name}")
    model.setParam("OutputFlag", 0)

    timesteps = range(start_day, end_day + 1)

    # Create the decision variables
    release_vars = model.addVars(
        timesteps,
        lb=0,
        ub=max_release,
        name="release",
    )
    spill_vars = model.addVars(
        timesteps,
        lb=0,
        name="spill",
    )
    storage_vars = model.addVars(
        timesteps,
        lb=0,
        ub=max_storage,
        name="storage",
    )
    # The deviation from target storage is represented by sbar
    sbar = model.addVars(
        timesteps,
        lb=0,
        name="sbar",
    )

    """
    When using max/min as a function, we need to use gp.max_ and gp.min_
    see https://support.gurobi.com/hc/en-us/community/posts/360078185112-gurobipy-Model-addGenConstrMin-Invalid-data-in-vars-array

    spills[day] = max(0, total_inflow[day] + storage[day-1] - max_storage - release[day])
    spills[day] = gp.max_(0, spill_bar[day])

    with
    spill_bar[day] = total_inflow[day] + storage[day-1] - max_storage - release[day]
    """
    spill_bar = model.addVars(
        timesteps,
        lb=-gp.GRB.INFINITY,
        name="spill_bar",
    )

    # Create the objective function
    model.setObjective(
        gp.quicksum(sbar[day] + spill_vars[day] for day in timesteps),
        sense=gp.GRB.MINIMIZE,
    )

    # Lower and upper bounds for the storage deviation are defined by sbar
    model.addConstrs(
        (
            -1 * sbar[day] <= target_storage[day] - storage_vars[day]
            for day in timesteps
        ),
        name="c_min_sbar",
    )
    model.addConstrs(
        (target_storage[day] - storage_vars[day] <= sbar[day] for day in timesteps),
        name="c_max_sbar",
    )
    # Minimum release has not been enforced when defining
    # the variable.
    model.addConstrs(
        (release_vars[day] >= minflow[day] for day in timesteps),
        name="c_min_release",
    )
    # Define spill
    model.addConstrs(
        (spill_vars[day] == gp.max_(0, spill_bar[day]) for day in timesteps),
        name="c_spill",
    )

    # Define spill_bar
    for day in timesteps:
        if day == start_day:
            model.addConstr(
                (
                    spill_bar[day]
                    == initial_storage
                    + total_inflow[day]
                    - release_vars[day]
                    - max_storage
                ),
                name=f"c_define_spill_bar[{day}]",
            )
        else:
            model.addConstr(
                (
                    spill_bar[day]
                    == storage_vars[day - 1]
                    + total_inflow[day]
                    - release_vars[day]
                    - max_storage
                ),
                name=f"c_define_spill_bar[{day}]",
            )

    # The storage at the start day is the initial storage
    model.addConstr(
        (
            storage_vars[start_day]
            == initial_storage
            + total_inflow[start_day]
            - release_vars[start_day]
            - spill_vars[start_day]
        ),
        name="c_initial_storage",
    )

    # Storage at other days
    model.addConstrs(
        (
            storage_vars[day]
            == storage_vars[day - 1]
            + total_inflow[day]
            - release_vars[day]
            - spill_vars[day]
            for day in range(start_day + 1, end_day + 1)
        ),
        name="c_storage",
    )

    # Solve the optimization problem
    model.optimize()

    # Check the status of the optimization
    if model.status == gp.GRB.INFEASIBLE:
        # Export IIS file if the problem is infeasible
        model.computeIIS()
        model.write(f"release_from_storage_{reservoir_name}.ilp")
        raise Exception(f"Match storage is infeasible: {reservoir_name}")

    # Get the solution
    opt_release = pd.Series(
        [release_vars[i].x for i in release_vars],
        name="release",
        index=timesteps,
    )
    opt_spill = pd.Series(
        [spill_vars[i].X for i in spill_vars],
        name="spill",
        index=timesteps,
    )
    opt_storage = pd.Series(
        [storage_vars[i].X for i in storage_vars],
        name="storage",
        index=timesteps,
    )
    return opt_release, opt_spill, opt_storage, model.objVal


def solve_release_from_dispatch(
    reservoir_name: str,
    daily_dispatch: float,
    turbine_factor: float,
    max_head: float,
    max_level: float,
    min_level: float,
    level_t0: float,
    storage_max: float,
    storage_t0: float,
    inflow: float,
    min_release: float,
    max_release: float,
    max_generation: float,
) -> tuple[float, float, float, float, float, float, float]:
    """
    For each day, solve for release_t from daily dispatch_t as an optimization problem.

    min         abs(DISPATCH_t - daily_hydropower_t)
    s.t.

    1. Calculate hourly_hydropower_t
        hourly_hydropower_t = TURBINE_FACTOR * DENSITY * g * head_t * release_t

            where
                    DENSITY = 998  # kg/m3
                    g = 9.81  # m/s2

    2. Hydrautic head is a function of water levvel
    head_t = MAX_HEAD - (MAX_LEVEL - mid_level_t)

    where mid_level_t = (level_t0 + level_t) / 2

    3. level_t is a function of storage
    level_t = storage_t / STORAGE_MAX * (MAX_LEVEL - MIN_LEVEL) + MIN_LEVEL

    4. Definition of storage
    storage_t = STORAGE_t0 + INFLOW_t - release_t - spill_t

    5. Definition of spill
    spill_t = max(0, INFLOW_t + storage_t - STORAGE_MAX - release_t)
    Rearrange to
    spill_t = max(0, spill_bar)

    6. Definition of spill_bar
    spill_bar = INFLOW_t + storage_t-1 - STORAGE_MAX - release_t

    Note that the objective function is not linear because of the absolute value.
    To make it linear, we introduce a new variable mismatch_t and rewrite
    the objective function as:

    min     mismatch

    s.t.

            -mismatch <= DISPATCH_t - daily_hydropower_t <= mismatch

    """
    ############################
    # Creating the model
    ############################
    model = gp.Model(f"get_release_from_dispatch_{reservoir_name}")
    model.setParam("OutputFlag", 0)

    # Create variables
    mismatch = model.addVar(lb=0.0, name="mismatch")
    release = model.addVar(lb=min_release, ub=max_release, name="release")

    spill = model.addVar(lb=0.0, name="spill")
    spill_bar = model.addVar(lb=-gp.GRB.INFINITY, name="spill_bar")

    level = model.addVar(lb=min_level, ub=max_level, name="level")
    storage = model.addVar(lb=0.0, ub=storage_max, name="storage")

    head = model.addVar(lb=0.0, ub=max_head, name="head")

    # Unbounded hydropower
    unb_hourly_hydropower = model.addVar(lb=0.0, name="unb_hourly_hydropower")
    # Bounded hydropower
    hourly_hydropower = model.addVar(lb=0.0, name="hourly_hydropower")
    daily_hydropower = model.addVar(lb=0.0, name="daily_hydropower")

    # Set objective
    model.setObjective(mismatch, gp.GRB.MINIMIZE)

    # Bounds of mismatch
    model.addConstr(
        -mismatch <= daily_dispatch - daily_hydropower, name="c_mismatch_lb"
    )
    model.addConstr(mismatch >= daily_dispatch - daily_hydropower, name="c_mismatch_ub")

    # (1) Define hydropower. Note that the equation requires
    # converting the release from m3/day to m3/s.
    density = 998  # kg/m3
    gravity = 9.81  # m/s2
    num_seconds_in_day = 24 * 3600

    model.addConstr(
        unb_hourly_hydropower
        == turbine_factor
        * density
        * gravity
        * head
        * release
        / num_seconds_in_day
        / 1e6,  # Convert to MW
        name="c_unbounded_hydropower",
    )

    # (1a) Limit hourly hydropower by turbine capacity
    model.addConstr(
        hourly_hydropower == gp.min_(unb_hourly_hydropower, constant=max_generation),
        name="c_hydropower",
    )

    # (1b) Daily_hydropower in MW-day
    model.addConstr(
        daily_hydropower == hourly_hydropower * 24,
        name="c_daily_hydropower",
    )

    # (2) Define hydraulic head as a function of mid_level
    model.addConstr(
        head == max_head - (max_level - (level_t0 + level) / 2),
        name="c_head",
    )

    # (3) Define level
    model.addConstr(
        level == storage / storage_max * (max_level - min_level) + min_level,
        name="c_level",
    )

    # (4) Define storage
    model.addConstr(
        storage == storage_t0 + inflow - release - spill,
        name="c_storage",
    )

    # (5) Define spill_bar
    model.addConstr(
        spill_bar == storage_t0 + inflow - storage_max - release,
        name="c_spill_bar",
    )

    # (6) Define spill
    model.addConstr(spill == gp.max_(0, spill_bar), name="c_spill")

    ############################
    # Solve the optimization problem
    ############################
    model.optimize()

    # Check the status of the optimization
    if model.status == gp.GRB.INFEASIBLE:
        # Export IIS file if the problem is infeasible
        model.computeIIS()
        model.write("match_dispatch.ilp")
        print(f"\nMatching dispatch is infeasible: {reservoir_name}")

    # Get the solution
    release_t = release.X
    spill_t = spill.X
    storage_t = storage.X
    level_t = level.X
    hourly_hydropower_t = hourly_hydropower.X
    daily_hydropower_t = daily_hydropower.X
    mismatch_t = mismatch.X

    return (
        release_t,
        spill_t,
        storage_t,
        level_t,
        hourly_hydropower_t,
        daily_hydropower_t,
        mismatch_t,
    )
