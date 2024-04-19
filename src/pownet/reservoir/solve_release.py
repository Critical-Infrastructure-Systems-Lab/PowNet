"""
This script uses the Gurobi solver to solve for release when reoperation
encounters Case 2a: If dispatch is less than the original hydroenergy, 
then set release to dispatch to save water.

We need to solve the following optimization problem to find release_t:

min         abs(DISPATCH_t - hydroenergy_t)
s.t.

1. Calculate hydroenergy_t
    hydroenergy_t = TURBINE_FACTOR * DENSITY * g * head_t * release_t
    
        where
                DENSITY = 998  # kg/m3
                g = 9.81  # m/s2

2. Hydrautic head (d_t) is a function of storage level 
head_t = MAX_HEAD - (MAX_LEVEL - ( level_t + LEVEL_t0 ) / 2)

3. level_t is a function of storage
level_t = storage_t / STORAGE_MAX * (MAX_LEVEL - MIN_LEVEL) + MIN_LEVEL

4. Definition of storage
storage_t = STORAGE_t0 + INFLOW_t - release_t - spill_t

5. Definition of spill
spill_t = max(0, INFLOW_t + STORAGE_t0 - STORAGE_MAX - release_t)
Rearrange to
spill_t = max(0, spill_bar)

6. Definition of spill_bar
spill_bar = INFLOW_t + STORAGE_t0 - STORAGE_MAX - release_t



Note that we need to rearrange the objective function to make it linear.
min     z

s.t.

        -z <= DISPATCH_t - hydroenergy_t <= z

"""

import gurobipy as gp


def gp_solve_release(
    dispatch: float,
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
    res_name: str,
) -> tuple[float, float, float, float]:
    """
    Solve for release_t when reoperation encounters Case 2a: If dispatch is less than the original hydroenergy,
    then set release to dispatch to save water.
    """
    # Create a new model
    model = gp.Model(f"match_dispatch_{res_name}")
    model.setParam("OutputFlag", 0)

    # Create variables
    z = model.addVar(lb=0.0, name="z")
    release = model.addVar(
        lb=min_release,
        ub=max_release,
        name="release",
    )

    spill = model.addVar(lb=0.0, name="spill")
    spill_bar = model.addVar(lb=-gp.GRB.INFINITY, name="spill_bar")

    storage = model.addVar(lb=0.0, ub=storage_max, name="storage")
    level = model.addVar(
        lb=min_level,
        ub=max_level,
        name="level",
    )

    head = model.addVar(lb=0.0, ub=max_head, name="head")
    unbounded_hydropower = model.addVar(lb=0.0, name="unbounded_hydropower")
    hydropower = model.addVar(lb=0.0, name="hydropower")

    hydroenergy = model.addVar(lb=0.0, name="hydroenergy")

    # Set objective
    model.setObjective(z, gp.GRB.MINIMIZE)

    # Bounds of z
    model.addConstr(-z <= dispatch - hydroenergy, name="c_zlb")
    model.addConstr(z >= dispatch - hydroenergy, name="c_zub")

    # (1) Define hydropower. Note that we need to convert
    # inflow from m3/s to m3/day. Also,
    # we are solving for hydropower in MW.
    model.addConstr(
        unbounded_hydropower
        == turbine_factor * 998 * 9.81 * head * release / (24 * 3600) / 1e6,
        name="c_unbounded_hydropower",
    )

    # (1a) Define hydropower
    model.addConstr(
        hydropower == gp.min_(unbounded_hydropower, constant=max_generation),
        name="c_hydropower",
    )

    # (1b) Define hydroenergy.
    # Convert the average hydropower in MW to hydroenergy in MW-day
    model.addConstr(
        hydroenergy == hydropower * 24,
        name="c_hydroenergy",
    )

    # (2) Define hydraulic head
    model.addConstr(
        head == max_head - (max_level - (level_t0 + level) / 2), name="c_head"
    )

    # (3) Define level
    model.addConstr(
        level == storage / storage_max * (max_level - min_level) + min_level,
        name="c_level",
    )

    # (4) Define storage
    model.addConstr(storage_t0 + inflow - release - spill == storage, name="c_storage")

    # (5) Define spill_bar
    model.addConstr(
        spill_bar == inflow + storage_t0 - storage_max - release, name="c_spill_bar"
    )

    # (6) Define spill
    model.addConstr(spill == gp.max_(0, spill_bar), name="c_spill")

    # Optimize model
    model.optimize()

    # Check the status of the optimization
    if model.status == gp.GRB.INFEASIBLE:
        # Export IIS file if the problem is infeasible
        model.computeIIS()
        model.write("match_dispatch.ilp")
        print(f"\nMatching dispatch is infeasible: {res_name}")

    # Get the solution
    release_t = release.X
    spill_t = spill.X
    storage_t = storage.X
    level_t = level.X
    hydroenergy_t = hydroenergy.X
    z_t = z.X

    return release_t, spill_t, storage_t, level_t, hydroenergy_t, z_t, hydropower.X


if __name__ == "__main__":
    # Example
    dispatch = 1887.63
    turbine_factor = 0.9
    max_head = 122
    max_level = 610
    min_level = 500
    level_t0 = 577.3428
    storage_max = 432000000
    storage_t0 = 303746459.501682
    inflow = 997541.0496
    min_release = 4710998.66
    max_release = 8948918.6595
    max_generation = 194
    res_name = "infeasible_kamchay_k4_reop1"

    release_t, spill_t, storage_t, level_t, hydroenergy_t, z_t = gp_solve_release(
        dispatch=dispatch,
        turbine_factor=turbine_factor,
        max_head=max_head,
        max_level=max_level,
        min_level=min_level,
        level_t0=level_t0,
        storage_max=storage_max,
        storage_t0=storage_t0,
        inflow=inflow,
        min_release=min_release,
        max_release=max_release,
        max_generation=max_generation,
        res_name=res_name,
    )

    print(f"release_t = {release_t}")
    print(f"spill_t = {spill_t}")
    print(f"storage_t = {storage_t}")
    print(f"level_t = {level_t}")
    print(f"hydroenergy_t = {hydroenergy_t}")
    print(f"z_t = {z_t}")
