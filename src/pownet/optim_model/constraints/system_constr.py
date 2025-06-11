"""system_constr.py: Constraints for the power system"""

import gurobipy as gp
import pandas as pd

from pownet.data_utils import get_capacity_value


def add_c_reserve_req_1(
    model: gp.Model,
    spin: gp.tupledict,
    charge_state: gp.tupledict,
    spin_shortfall: gp.tupledict,
    timesteps: range,
    step_k: int,
    thermal_units: list,
    storage_units: list,
    spin_requirement: pd.Series,
) -> gp.tupledict:
    """Equation 68 of Kneuven et al (2019) based on Morales-España et al. (2013).
    System-wide spinning reserve requirement. The spinning reserve is the sum of
    the spinning reserve of all thermal units.

    NOTE: This formulation is suitable when we implement the spinning-reserve variable (spin).
    Only one reserve_requirement is constraint is needed.

    Args:
        model (gp.Model): The optimization model
        spin (gp.tupledict): The spinning reserve
        charge_state (gp.tupledict): The state of charge of energy storage systems
        spin_shortfall (gp.tupledict): The spinning reserve shortfall
        timesteps (range): The range of timesteps
        step_k (int): The current iteration
        thermal_units (list): The list of thermal units
        storage_units (list): The list of storage units
        spin_requirement (pd.Series): The spinning reserve requirement at each hour (MW)

    Returns:
        gp.tupledict: The constraints for the spinning reserve requirement
    """
    hours_per_step = 24  # len(timesteps)
    return model.addConstrs(
        (
            gp.quicksum(spin[unit, t] for unit in thermal_units)
            + gp.quicksum(charge_state[unit, t] for unit in storage_units)
            + spin_shortfall[t]
            >= spin_requirement.loc[t + (step_k - 1) * hours_per_step]
            for t in timesteps
        ),
        name="reserveReq1",
    )


def add_c_reserve_req_2(
    model: gp.Model,
    pbar: gp.tupledict,
    u: gp.tupledict,
    charge_state: gp.tupledict,
    spin_shortfall: gp.tupledict,
    timesteps: range,
    step_k: int,
    thermal_units: list,
    thermal_min_capacity: dict,
    storage_units: list,
    total_demand: pd.Series,
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
        storage_units (list): The list of storage units
        thermal_min_capacity (dict): The minimum capacity of the thermal unit
        demand_nodes (list): The list of demand nodes
        total_demand (pd.Series): The total system demand at each hour (MW)
        spin_requirement (pd.Series): The spinning reserve requirement at each hour (MW)

    Returns:
        gp.tupledict: The constraints for the spinning reserve requirement
    """
    hours_per_step = 24  # For rolling horizon
    return model.addConstrs(
        (
            gp.quicksum(
                pbar[unit, t] + thermal_min_capacity[unit] * u[unit, t]
                for unit in thermal_units
            )
            + gp.quicksum(charge_state[unit, t] for unit in storage_units)
            + spin_shortfall[t]
            >= total_demand.loc[t + (step_k - 1) * hours_per_step]
            + spin_requirement[t + (step_k - 1) * hours_per_step]
            for t in timesteps
        ),
        name="reserveReq2",
    )


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

    Note: Currently not implemented in the model. The load shortfall is not a variable in the model.

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
    flow_fwd: gp.tupledict,
    flow_bwd: gp.tupledict,
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
    ess_charge_units: dict,
    ess_discharge_units: dict,
    demand_nodes: list,
    demand: pd.DataFrame,
    gen_loss_factor: float,
    line_loss_factor: float,
) -> gp.tupledict:
    """Adds power flow balance constraints to the optimization model.

    These constraints ensure that for each node and each timestep, the total
    power flowing into the node equals the total power flowing out of the node.
    This represents Kirchhoff's Current Law (KCL) applied to power flow in the
    network.

    The balance considers:
    - Power generated at the node (adjusted for generation efficiency).
    - Power flow into and out of the node via transmission lines (adjusted for line losses).
    - Power consumed by energy storage charging at the node.
    - Power injected by energy storage discharging at the node.
    - Power demand at the node.
    - Power mismatch variables (positive and negative slack).

    Args:
        model (gp.Model): The optimization model
        pthermal (gp.tupledict): The power output of thermal units
        phydro (gp.tupledict): The power output of hydro units
        psolar (gp.tupledict): The power output of solar units
        pwind (gp.tupledict): The power output of wind units
        pimp (gp.tupledict): The power output of import units
        pcharge (gp.tupledict): The charge of energy storage units
        pdis (gp.tupledict): The discharge of energy storage units
        pos_pmismatch (gp.tupledict): The positive power mismatch
        neg_pmismatch (gp.tupledict): The negative power mismatch
        flow_fwd (gp.tupledict): The power flow from forward k -> s
        flow_bwd (gp.tupledict): The power flow from backward s <- k
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
        ess_charge_units (dict): Storage units to charge from this node
        ess_discharge_units (dict): Storage units to discharge to this node
        demand_nodes (list): The list of demand nodes
        demand (pd.DataFrame): The demand data
        gen_loss_factor (float): The system-wide generation loss factor
            (applied at generation source)
        line_loss_factor (float): The system-wide line loss factor

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
    # Generation efficiency after considering system-wide losses at the source
    gen_efficiency = 1 - gen_loss_factor

    # Line efficiency (power received / power sent)
    line_efficiency = 1 - line_loss_factor

    hours_per_step = 24  # For rolling horizon

    for t in timesteps:
        for node in nodes:
            generation = 0
            # Loops through generators located *in* the node (aggregated generation)
            for unit_g in node_generator[node]:
                generation += get_unit_generation(unit_g, t)

            # A grid storage system charges from this node
            storage_charge = 0
            if node in ess_charge_units:
                storage_systems = ess_charge_units[node]
                for storage_system in storage_systems:
                    storage_charge += pcharge[storage_system, t]

            # The grid storage also injects into this node
            storage_discharge = 0
            if node in ess_discharge_units:
                storage_systems = ess_discharge_units[node]
                for storage_system in storage_systems:
                    storage_discharge += pdis[storage_system, t]

            # Get the demand of node n at time t
            demand_n_t = 0
            if node in demand_nodes:
                demand_n_t = demand.loc[t + (step_k - 1) * hours_per_step, node]

            # The net line flow into the node is the sum of the power flow
            net_line_flow_into_node = 0
            if node in node_edge:
                for x, y in node_edge[node]:
                    if x == node:
                        net_line_flow_into_node -= flow_fwd[x, y, t]
                        net_line_flow_into_node += (
                            flow_bwd[node, y, t] * line_efficiency
                        )
                    elif y == node:
                        net_line_flow_into_node += (
                            flow_fwd[x, node, t] * line_efficiency
                        )
                        net_line_flow_into_node -= flow_bwd[x, node, t]

            # Mismatch variables
            mismatch = pos_pmismatch[node, t] - neg_pmismatch[node, t]

            # Given the above terms, we can specify the energy balance
            cname = f"flowBal[{node},{t}]"
            constraints[cname] = model.addConstr(
                (
                    generation * gen_efficiency
                    + net_line_flow_into_node
                    + mismatch
                    + storage_discharge  # Already factored in discharge efficiency is the ESS balance
                    == demand_n_t + storage_charge
                ),
                name=cname,
            )
    return constraints


def add_c_ref_node(
    model: gp.Model,
    theta: gp.tupledict,
    timesteps: range,
    max_demand_node: str,
) -> gp.tupledict:
    """Equation 64d of Kneuven et al (2019). Set the voltage angle
    at the reference node to zero. The reference node is typically
    the node with the highest demand.

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
    flow_fwd: gp.tupledict,
    flow_bwd: gp.tupledict,
    theta: gp.tupledict,
    timesteps: range,
    step_k: int,
    edges: list,
    susceptance: pd.DataFrame,
) -> gp.tupledict:
    """Equation 64a of Kneuven et al (2019) expresses the power flow in a transmission line
    as a function of the voltage angle difference between the two buses it connects.
    In DC-OPF, the real power flow on a transmission line is directly proportional
    to the difference in voltage angles.

    Note: If the voltage-angle variable is not implemented, then we can use the Kirchhoff formulation.

    Args:
        model (gp.Model): The optimization model
        flow_fwd (gp.tupledict): The power flow from forward k -> s
        flow_bwd (gp.tupledict): The power flow from backward s <- k
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
            flow_fwd[a, b, t] - flow_bwd[a, b, t]
            == susceptance.loc[t + (step_k - 1) * 24, (a, b)]
            * (theta[a, t] - theta[b, t])
            for (a, b) in edges
            for t in timesteps
        ),
        name="angleDiff",
    )


def add_c_kirchhoff(
    model: gp.Model,
    flow_fwd: gp.tupledict,
    flow_bwd: gp.tupledict,
    timesteps: range,
    step_k: int,
    edges: list,
    cycle_map: dict,
    susceptance: pd.DataFrame,
) -> gp.tupledict:
    """Equation 23b in Horsch et al (2018). This constraint implements
    the Kirchhoff circuit laws (KCL) directly on the flow variables.

    Note: This constraint replaces the voltage-angle difference formulation.

    Args:
        model (gp.Model): The optimization model
        flow_fwd (gp.tupledict): The power flow variable
        flow_bwd (gp.tupledict): The power flow variable
        timesteps (range): The range of timesteps
        step_k (int): The current iteration
        edges (list): The list of edges
        cycle_map (dict): The cycle map (created by DataProcessor class)
        susceptance (pd.DataFrame): The susceptance matrix

    Returns:
        gp.tupledict: The constraints for the Kirchhoff circuit laws

    """

    hours_per_step = 24  # For rolling horizon
    kvl_constraints = gp.tupledict()

    # Build the cycle_incidence matrix once if it's static based on 'edges' and 'cycle_map'
    for cycle_id, cycle_nodes in cycle_map.items():
        # 1. Determine the directed edges for this cycle based on cycle_nodes
        if not cycle_nodes or len(cycle_nodes) < 3:  # Basic check for a valid cycle
            continue

        current_cycle_directed_edges = (
            []
        )  # List of ( (n1,n2), (n2,n1), ... ) representing traversal
        for i in range(len(cycle_nodes)):
            u = cycle_nodes[i]
            v = cycle_nodes[
                (i + 1) % len(cycle_nodes)
            ]  # Wraps around to close the cycle
            current_cycle_directed_edges.append((u, v))

        # 2. For each edge in this cycle's traversal, find its properties
        #    (original edge name, sign, and its susceptance)

        # edges_in_current_kvl_sum will be a list of tuples:
        # ( (original_a, original_b), sign_in_sum )
        # where (original_a, original_b) is an edge from your input 'edges' list.
        edges_for_kvl_sum_in_this_cycle = []

        # (u,v) is the edge traversed in cycle
        for u, v in current_cycle_directed_edges:

            # Traversed edge (u,v) IS a defined edge
            if (u, v) in edges:
                edges_for_kvl_sum_in_this_cycle.append(((u, v), 1))

            # Traversed edge (u,v) is REVERSE of defined edge (v,u)
            elif (v, u) in edges:
                edges_for_kvl_sum_in_this_cycle.append(((v, u), -1))
            else:
                # This should not happen if cycle_map is valid and all lines exist
                raise ValueError(
                    f"Edge segment ({u},{v}) in cycle {cycle_id} not found in defined edges."
                )

        # 3. Add constraints for each timestep for this cycle
        for t in timesteps:
            kirchhoff_sum_expr = gp.LinExpr()
            time_index_for_susceptance = t + (step_k - 1) * hours_per_step

            for original_edge_ab, sign in edges_for_kvl_sum_in_this_cycle:
                a, b = original_edge_ab

                # Ensure the edge exists in the susceptance DataFrame for safety
                if (a, b) not in susceptance.columns:
                    raise ValueError(
                        f"Warning: Edge ({a},{b}) not in susceptance data for cycle {cycle_id}, time {t}"
                    )

                # Get susceptance, B_ab
                b_ab = susceptance.loc[time_index_for_susceptance, (a, b)]
                if b_ab == 0:
                    # TODO: Decide how to handle: skip term, raise error, or use a very small number if it implies infinite reactance
                    # For KVL, a zero susceptance line (infinite reactance) would mean zero flow unless it's the only path.
                    raise ValueError(
                        f"Susceptance for edge ({a},{b}) is zero at time {t}."
                    )
                reactance_x_ab = 1.0 / b_ab
                net_flow_p_ab = flow_fwd[a, b, t] - flow_bwd[a, b, t]
                kirchhoff_sum_expr.add(sign * reactance_x_ab * net_flow_p_ab)

            cname = f"kirchhoff[{cycle_id},{t}]"
            kvl_constraints[cname] = model.addConstr(
                kirchhoff_sum_expr == 0, name=cname
            )
    return kvl_constraints


def add_c_thermal_curtail_ess(
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
    """Adds curtailment constraints for must-take thermal units, considering ESS charging.

    For must-take thermal units, the total potential generation (derated capacity)
    must equal the sum of dispatched power, curtailed power, and power used to
    charge any attached energy storage systems.

    Constraint:
    pthermal[unit, t] + pthermal_curtail[unit, t] + pcharge_ess[unit, t] == derated_capacity[unit, t]

    Args:
        model (gp.Model): The optimization model.
        pthermal (gp.tupledict): Power dispatched from thermal units [unit, t].
        pthermal_curtail (gp.tupledict): Power curtailed from thermal units [unit, t].
        pcharge (gp.tupledict): Power used to charge energy storage systems [ess_unit, t].
        timesteps (range): The range of timesteps for the constraints.
        step_k (int): The current optimization step (for indexing time-series data).
        thermal_must_take_units (list): List of thermal units designated as must-take.
        thermal_derated_capacity (pd.DataFrame): DataFrame of derated capacity for thermal units (index=time, columns=unit).
        ess_attached (dict): Dictionary mapping generation units to lists of attached ESS units {gen_unit: [ess_unit1, ess_unit2, ...]}.

    Returns:
        gp.tupledict: Dictionary of added curtailment constraints.
    """
    hours_per_step = 24  # For rolling horizon
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
                    == thermal_derated_capacity.loc[
                        t + (step_k - 1) * hours_per_step, unit
                    ]
                ),
                name=cname,
            )
    return constraints


def add_c_unit_curtail_ess(
    model: gp.Model,
    pdispatch: gp.tupledict,
    pcurtail: gp.tupledict,
    pcharge: gp.tupledict,
    unit_type: str,
    timesteps: range,
    step_k: int,
    units: list,
    capacity_df: pd.DataFrame,
    ess_attached: dict[str, list[str]],
) -> gp.tupledict:
    """Adds generic curtailment constraints for a specified unit type, considering ESS charging.

    This function ensures that for each unit of the specified type and each timestep,
    the total available capacity equals the sum of the power dispatched to the grid,
    the power curtailed, and the power used to charge any directly attached
    energy storage systems (ESS).

    Constraint for each unit `u` and time `t`:
    pdispatch[u, t] + pcurtail[u, t] + pcharge_ess[u, t] == capacity[u, t]

    Where `pcharge_ess[u, t]` is the sum of `pcharge` for all ESS units attached to `u`.

    Args:
        model (gp.Model): The Gurobi optimization model.
        pdispatch (gp.tupledict): Decision variables for power dispatched from units [unit, t].
        pcurtail (gp.tupledict): Decision variables for power curtailed from units [unit, t].
        pcharge (gp.tupledict): Decision variables for power charging ESS units [ess_unit, t].
        unit_type (str): A string identifier for the type of unit (e.g., 'solar', 'wind')
                         used for naming constraints.
        timesteps (range): The range of timesteps to add constraints for.
        step_k (int): The current optimization step (used for indexing time-series data like capacity).
        units (list): A list of unit identifiers (strings) of the specified type.
        capacity_df (pd.DataFrame): DataFrame containing the available capacity of each unit
                                   over time (index=time, columns=unit).
        ess_attached (Dict[str, List[str]]): A dictionary mapping generation unit IDs
                                            to a list of attached ESS unit IDs.
                                            Example: {'solar_farm_1': ['battery_1', 'battery_2']}

    Returns:
        gp.tupledict: A Gurobi tupledict containing the added constraints, indexed by constraint name.
    """
    constraints = gp.tupledict()
    for unit in units:
        has_storage = unit in ess_attached
        for t in timesteps:
            pcharge_unit_t = 0
            if has_storage:
                # A unit may have multiple storage systems
                for storage_unit in ess_attached[unit]:
                    pcharge_unit_t += pcharge[storage_unit, t]

            cname = f"{unit_type}_curtail_ess[{unit},{t}]"
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
    unit_type: str,
    sim_horizon: int,
    step_k: int,
    units: list,
    capacity_df: pd.DataFrame,
    ess_attached: dict[str, list[str]],
) -> gp.tupledict:
    """Adds daily energy balance constraints for specified units, considering ESS charging.

    This function aggregates the hourly dispatch, curtailment, and associated ESS charging
    over a full day (24 hours) and ensures this sum equals the total available energy
    capacity for that unit on that day. This is useful for constraints or objectives
    that operate on a daily timescale.

    Constraint for each unit `u` and day `d`:
    Sum_{t in day d}(pdispatch[u, t]) + Sum_{t in day d}(pcurtail[u, t]) + Sum_{t in day d}(pcharge_ess[u, t]) == daily_capacity[u, d]

    Where `pcharge_ess[u, t]` is the sum of `pcharge` for all ESS units attached to `u` at hour `t`.
    The capacity is assumed to be provided as a single value for the entire day.

    Args:
        model (gp.Model): The Gurobi optimization model.
        pdispatch (gp.tupledict): Decision variables for hourly power dispatched [unit, t].
        pcurtail (gp.tupledict): Decision variables for hourly power curtailed [unit, t].
        pcharge (gp.tupledict): Decision variables for hourly power charging ESS [ess_unit, t].
        unit_type (str): String identifier for the unit type (e.g., 'solar', 'wind')
                         used for naming constraints.
        sim_horizon (int): Total simulation horizon in hours. Used to determine the number of full days.
        step_k (int): The starting day index for adding constraints. Assumes days are numbered
                      sequentially (e.g., 1, 2, 3...).
        units (list): List of unit identifiers (strings) of the specified type.
        capacity_df (pd.DataFrame): DataFrame containing the total *daily* available energy capacity
                                   for each unit. **Crucially, this DataFrame must be indexed by
                                   day number (matching the `day` loop variable) and have units as columns.**
                                   Example index: [1, 2, 3...], columns: ['unit1', 'unit2', ...].
        ess_attached (Dict[str, List[str]]): Dictionary mapping generation unit IDs to lists
                                            of attached ESS unit IDs.
                                            Example: {'solar_farm_1': ['battery_1']}

    Returns:
        gp.tupledict: A Gurobi tupledict containing the added daily constraints, indexed by constraint name.

    """
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

            cname = f"{unit_type}_curtail_ess[{unit},{day}]"
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
