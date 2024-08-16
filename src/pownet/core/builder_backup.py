from __future__ import annotations

import math
import os

from gurobipy import GRB
import gurobipy as gp
import networkx as nx
import pandas as pd

from pownet.folder_utils import get_output_dir
from pownet.model import PowerSystemModel


class ModelBuilder:
    """Build an instance of the Unit Commitment Problem."""

    def __init__(self, inputs: "SystemInput") -> None:
        self.inputs = inputs

    def _add_var_dispatch(self, model: gp.Model, sim_period: range) -> None:
        return model.addVars(
            self.inputs.thermal_units,
            sim_period,
            lb={
                (unit_g, t): self.inputs.thermal_min_capacity[unit_g]
                for t in sim_period
                for unit_g in self.inputs.thermal_units
            },
            ub={
                (unit_g, t): self.inputs.thermal_derated_capacity.loc[t, unit_g]
                for t in sim_period
                for unit_g in self.inputs.thermal_units
            },
            vtype=GRB.CONTINUOUS,
            name="dispatch",
        )

    def _add_variables(self, model: gp.Model, sim_period: range) -> None:
        """The lower and upper bounds of variables are defined here instead
        of defining them as constraints.
        """

        #######################
        # Thermal units
        #######################

        # Dispatched power (or power output) from a generator. Unit: MW
        self.dispatch = model.addVars(
            self.inputs.thermal_units,
            sim_period,
            lb={
                (unit_g, t): self.inputs.thermal_min_capacity[unit_g]
                for t in sim_period
                for unit_g in self.inputs.thermal_units
            },
            ub={
                (unit_g, t): self.inputs.thermal_derated_capacity.loc[t, unit_g]
                for t in sim_period
                for unit_g in self.inputs.thermal_units
            },
            vtype=GRB.CONTINUOUS,
            name="dispatch",
        )

        # Commitment. On = 1 and off = 0
        self.u = model.addVars(
            self.inputs.thermal_units,
            sim_period,
            vtype=GRB.BINARY,
            name="status",
        )

        # Switch-on
        self.v = model.addVars(
            self.inputs.thermal_units,
            sim_period,
            vtype=GRB.BINARY,
            name="start",
        )

        # Switch-off
        self.w = model.addVars(
            self.inputs.thermal_units,
            sim_period,
            vtype=GRB.BINARY,
            name="shut",
        )

        # Power generated above minimum. Unit: MW
        self.p = model.addVars(
            self.inputs.thermal_units,
            sim_period,
            lb=0,
            ub={
                (unit_g, t): self.inputs.thermal_derated_capacity.loc[t, unit_g]
                for t in sim_period
                for unit_g in self.inputs.thermal_units
            },
            vtype=GRB.CONTINUOUS,
            name="p",
        )

        # The maximum power available above the minimum capacity. Unit: MW
        # Formula: pbar = p + spin
        self.pbar = model.addVars(
            self.inputs.thermal_units,
            sim_period,
            lb=0,
            ub={
                (unit_g, t): self.inputs.thermal_derated_capacity.loc[t, unit_g]
                for t in sim_period
                for unit_g in self.inputs.thermal_units
            },
            vtype=GRB.CONTINUOUS,
            name="pbar",
        )

        # Spinning reserve. Unit: MW
        # The upper bound is the difference between the derated capacity and the minimum capacity
        self.spin = model.addVars(
            self.inputs.thermal_units,
            sim_period,
            lb=0,
            ub={
                (unit_g, t): self.inputs.thermal_derated_capacity.loc[t, unit_g]
                - self.inputs.thermal_min_capacity[unit_g]
                for t in sim_period
                for unit_g in self.inputs.thermal_units
            },
            vtype=GRB.CONTINUOUS,
            name="spin",
        )

        #######################
        # Renewables and import
        #######################

        # The dispatch from renewables is in absolute term. Unit: MW
        self.phydro = model.addVars(
            self.inputs.hydro_units,
            sim_period,
            lb=0,
            ub={
                (hydro_unit, t): self.inputs.hydro_capacity.loc[t, hydro_unit]
                for t in sim_period
                for hydro_unit in self.inputs.hydro_units
            },
            vtype=GRB.CONTINUOUS,
            name="phydro",
        )

        self.psolar = model.addVars(
            self.inputs.solar_units,
            sim_period,
            lb=0,
            ub={
                (solar_unit, t): self.inputs.solar_capacity.loc[t, solar_unit]
                for t in sim_period
                for solar_unit in self.inputs.solar_units
            },
            vtype=GRB.CONTINUOUS,
            name="psolar",
        )

        self.pwind = model.addVars(
            self.inputs.wind_units,
            sim_period,
            lb=0,
            ub={
                (wind_unit, t): self.inputs.wind_cap.loc[t, wind_unit]
                for t in sim_period
                for wind_unit in self.inputs.wind_units
            },
            vtype=GRB.CONTINUOUS,
            name="pwind",
        )

        # The import from neighboring system in absolute term. Unit: MW
        self.pimp = model.addVars(
            self.inputs.import_units,
            sim_period,
            lb=0,
            ub={
                (import_unit, t): self.inputs.import_capacity.loc[t, import_unit]
                for t in sim_period
                for import_unit in self.inputs.import_units
            },
            vtype=GRB.CONTINUOUS,
            name="pimp",
        )

        #######################
        # System variables
        #######################

        # Spinning reserve of the overall system. Unit: MW
        self.sys_spin = model.addVars(
            sim_period,
            lb=0,
            vtype=GRB.CONTINUOUS,
            name="sys_spin",
        )

        # Positive mismatch. Unit: MW
        self.s_pos = model.addVars(
            self.inputs.demand_nodes,
            sim_period,
            lb=0,
            vtype=GRB.CONTINUOUS,
            name="s_pos",
        )

        # Negative mismatch. Unit: MW
        # Need to clarify when we have negative mismatch.
        self.s_neg = model.addVars(
            self.inputs.demand_nodes,
            sim_period,
            lb=0,
            vtype=GRB.CONTINUOUS,
            name="s_neg",
        )

        # The flow variable f(a,b,t) represents the flow in the
        # line segment (a,b) at hour t in MW/hr). If the flow is positive,
        # then energy flows from a to b.
        # We set the bounds based on the transmission limit
        self.flow = model.addVars(
            self.inputs.edges,
            sim_period,
            lb={
                (source, sink, t): -1
                * self.inputs.line_capacity_factor
                * self.inputs.line_capacity.loc[t, (source, sink)]
                for t in sim_period
                for source, sink in self.inputs.edges
            },
            ub={
                (source, sink, t): self.inputs.line_capacity_factor
                * self.inputs.line_capacity.loc[t, (source, sink)]
                for t in sim_period
                for source, sink in self.inputs.edges
            },
            vtype=GRB.CONTINUOUS,
            name="flow",
        )

        # Volt angle. Unit: radians
        # The upper and lower bounds are [-pi/2 and pi/2] for the voltage angle.
        if self.inputs.dc_opf == "voltage_angle":
            self.theta = model.addVars(
                self.inputs.nodes,
                sim_period,
                lb=math.pi / -2,
                ub=math.pi / 2,
                vtype=GRB.CONTINUOUS,
                name="volt_angle",
            )

        model.update()

    def _get_thermal_fixed_coeffs(self, sim_period: range) -> dict:
        """Fixed cost is a function of rated capacity and fixed cost per unit"""
        return {
            (unit_g, t): self.inputs.thermal_rated_capacity[unit_g]
            * self.inputs.thermal_fixed_cost[unit_g]
            for t in sim_period
            for unit_g in self.inputs.thermal_units
        }

    def _get_thermal_opex_coeffs(self, sim_period: range) -> dict:
        """Variable cost is a function of fuel cost, heat rate, and opex"""
        return {
            (unit_g, t): (
                self.inputs.thermal_fuel_cost[unit_g]
                * self.inputs.thermal_heat_rate[unit_g]
            )
            + self.inputs.thermal_opex[unit_g]
            for t in sim_period
            for unit_g in self.inputs.thermal_units
        }

    def _get_thermal_startup_coeffs(self, sim_period: range) -> dict:
        """Startup cost is a function of rated capacity and startup cost per unit"""
        return {
            (unit_g, t): self.inputs.thermal_rated_capacity[unit_g]
            * self.inputs.thermal_startup_cost[unit_g]
            for t in sim_period
            for unit_g in self.inputs.thermal_units
        }

    def _get_marginal_cost_coeffs(
        self, sim_period: range, units: list, attribute: str
    ) -> dict:
        """
        Generic helper function to calculate coefficients based on marginal cost or a similar attribute for a list of units

        Args:
            units: The list of units to calculate coefficients for
            attribute: The attribute name in self.inputs to use for cost calculation

        Returns
            A dictionary mapping (unit, t) tuples to the calculated coefficients
        """
        return {
            (unit, t): getattr(self.inputs, attribute).loc[t, unit]
            for t in sim_period
            for unit in units
        }

    def _set_objective(self, sim_period: range) -> None:
        """The objective function has four components: fixed cost, variable cost,
        start-up cost, and shortfall cost.
        """
        # Cost coefficients of thermal units
        thermal_fixed_coeffs = self._get_thermal_fixed_coeffs(sim_period=sim_period)
        thermal_opex_coeffs = self._get_thermal_opex_coeffs(sim_period=sim_period)
        thermal_startup_coeffs = self._get_thermal_startup_coeffs(sim_period=sim_period)

        # Cost coefficients of hydro, solar, wind, and import
        hydro_coeffs = self._get_marginal_cost_coeffs(
            sim_period=sim_period,
            units=self.inputs.hydro_units,
            attribute="unit_marginal_cost",
        )

        solar_coeffs = self._get_marginal_cost_coeffs(
            sim_period=sim_period,
            units=self.inputs.solar_units,
            attribute="unit_marginal_cost",
        )

        wind_coeffs = self._get_marginal_cost_coeffs(
            sim_period=sim_period,
            units=self.inputs.wind_units,
            attribute="unit_marginal_cost",
        )

        import_coeffs = self._get_marginal_cost_coeffs(
            sim_period=sim_period,
            units=self.inputs.import_units,
            attribute="unit_marginal_cost",
        )

        # Build cost expressions for each component
        thermal_operation_expr = self.dispatch.prod(thermal_opex_coeffs)
        thermal_fixed_expr = self.u.prod(thermal_fixed_coeffs)
        thermal_startup_expr = self.v.prod(thermal_startup_coeffs)

        hydro_expr = self.phydro.prod(hydro_coeffs)
        solar_expr = self.psolar.prod(solar_coeffs)
        wind_expr = self.pwind.prod(wind_coeffs)

        import_expr = self.pimp.prod(import_coeffs)

        # The cost of shortfall is the slack variable (s_pos) needed to meet demand
        shortfall_expr = self.inputs.shortfall_penalty * (
            gp.quicksum(self.s_pos) + gp.quicksum(self.s_neg)
        )

        # Penalize the system if it cannot meet the spinning reserve requirement
        spin_reserve_penalty_expr = self.inputs.reserve_penalty * gp.quicksum(
            self.sys_spin
        )

        model.setObjective(
            (
                thermal_operation_expr
                + thermal_fixed_expr
                + thermal_startup_expr
                + hydro_expr
                + solar_expr
                + wind_expr
                + import_expr
                + shortfall_expr
                + spin_reserve_penalty_expr
            ),
            sense=GRB.MINIMIZE,
        )

    def _c_link_uvw_init(self, sim_period: range) -> None:
        """Equation 2 of Kneuven et al (2019).
        Define the relationship among unit status, start-up, and shutdown at the first timestep
        of the simulation period.
        """
        start_t = sim_period[0]
        model.addConstrs(
            (
                self.u[unit_g, start_t]
                # Last hour of the previous iteration
                - self.initial_u[unit_g, start_t - 1]
                == self.v[unit_g, start_t] - self.w[unit_g, start_t]
                for unit_g in self.inputs.thermal_units
            ),
            name="link_uvw_init",
        )

    def _c_link_uvw(self, sim_period: range) -> None:
        """Equation 2 of Kneuven et al (2019).
        Define the relationship among unit status, start-up, and shutdown
        """
        # Only consider the second timestep onwards
        start_t = sim_period[0] + 1
        end_t = sim_period[-1]
        model.addConstrs(
            (
                self.u[unit_g, t] - self.u[unit_g, t - 1]
                == self.v[unit_g, t] - self.w[unit_g, t]
                for t in range(start_t, end_t)
                for unit_g in self.inputs.thermal_units
            ),
            name="link_uvw",
        )

    def _c_link_dispatch(self, sim_period: range) -> None:
        """Equation 12 of Kneuven et al (2019). The dispatched power is
        a function of p and the minimum capacity of the unit.
        """
        model.addConstrs(
            (
                self.dispatch[unit_g, t]
                == self.p[unit_g, t]
                + self.inputs.thermal_min_capacity[unit_g] * self.u[unit_g, t]
                for t in sim_period
                for unit_g in self.inputs.thermal_units
            ),
            name="link_dispatch",
        )

    def _c_link_p(self, sim_period: range) -> None:
        """Equation 14 of Kneuven et al (2019).
        Establish the relationship among p, pbar, and spin together
        """
        model.addConstrs(
            (
                self.pbar[unit_g, t] == self.p[unit_g, t] + self.spin[unit_g, t]
                for t in sim_period
                for unit_g in self.inputs.thermal_units
            ),
            name="link_p",
        )

    def _c_link_pu_lower(self, sim_period: range) -> None:
        """Equation 18 of Kneuven et al (2019).
        Set the lower bound of the dispatched power.
        """
        model.addConstrs(
            (
                self.inputs.thermal_min_capacity[unit_g] * self.u[unit_g, t]
                <= self.dispatch[unit_g, t]
                for t in sim_period
                for unit_g in self.inputs.thermal_units
            ),
            name="p_lower_bound",
        )

    def _c_link_pu_upper(self, sim_period: range) -> None:
        """Equation 18 of Knueven et al (2019).
        Set the upper bound of the dispatched power. Also use
        Equation 13 for substituting pbar.
        """
        model.addConstrs(
            (
                self.pbar[unit_g, t]
                + self.inputs.thermal_min_capacity[unit_g] * self.u[unit_g, t]
                <= self.inputs.thermal_derated_capacity.loc[t, unit_g]
                * self.u[unit_g, t]
                for t in sim_period
                for unit_g in self.inputs.thermal_units
            ),
            name="p_upper_bound",
        )

    def _c_min_down_init(self, sim_period: range) -> None:
        """Equation 3b of Kneuven et al (2019).
        Minimum downtime at the first time step
        """
        constraints = []
        start_t = sim_period[0]
        for unit_g in self.inputs.thermal_units:
            # Find the min between the required downtime and the simulation horizon
            min_DT = min(self.initial_min_off[unit_g], self.inputs.sim_horizon)
            constraints.append(
                model.addConstr(
                    self.u.sum(unit_g, range(start_t, start_t + min_DT + 1)) == 0,
                    name=f"minDownInit[{unit_g}]",
                )
            )

    def _c_min_up_init(self, sim_period: range) -> None:
        """Equation 3a of Kneuven et al (2019).
        Minimum uptime at the initial timestep
        """
        start_t = sim_period[0]
        for unit_g in self.inputs.thermal_units:
            # Find the min between the required uptime and the simulation horizon
            min_UT = min(self.initial_min_on[unit_g], self.T)
            model.addConstr(
                self.u.sum(unit_g, range(start_t, start_t + min_UT + 1)) == min_UT,
                name=f"minUpInit[{unit_g}]",
            )

    def _c_min_down(self, sim_period: range) -> None:
        """Equation 5 of Kneuven et al (2019). Minimum downtime.
        This equation is stated to base on Malkin (2003) and
        Rajan and Takriti (2005).
        """
        start_t = sim_period[0]
        for unit_g in self.inputs.thermal_units:
            TD_g = self.inputs.TD[unit_g]
            for t in range(start_t + TD_g, start_t + self.inputs.sim_horiz + 1):
                LHS = gp.quicksum(
                    [self.w[unit_g, i] for i in range(t - TD_g + 1, t + 1)]
                )
                model.addConstr(
                    LHS <= 1 - self.u[unit_g, t], name="minDown" + f"[{unit_g},{t}]"
                )

    def _c_min_up(self, sim_period: range) -> None:
        """Equation 4 of Kneuven et al (2019). Minimum uptime.
        This equation is stated to base on Malkin (2003) and
        Rajan and Takriti (2005).
        """
        start_t = sim_period[0]
        end_t = sim_period[-1]
        for unit_g in self.inputs.thermal_units:
            TU_g = self.inputs.TU[unit_g]
            for t in range(start_t + TU_g, end_t):
                LHS = gp.quicksum(
                    [self.v[unit_g, i] for i in range(t - TU_g + 1, t + 1)]
                )
                model.addConstr(
                    LHS <= self.u[unit_g, t], name="minUp" + f"[{unit_g},{t}]"
                )

    def _c_peak_down_bound(self, sim_period: range) -> None:
        """Equation 23b of Kneuven et al (2019).
        This is the generation limit during the shutdown of a peaking unit.
        A peaking unit has TU = 1.
        """
        start_t = sim_period[0]
        end_t = sim_period[-1]
        model.addConstrs(
            (
                self.p[unit_g, t] + self.spin[unit_g, t]
                <= (
                    self.inputs.thermal_derated_capacity.loc[t, unit_g]
                    - self.inputs.thermal_min_capacity[unit_g]
                )
                * self.u[unit_g, t]
                - (
                    self.inputs.thermal_derated_capacity[t, unit_g]
                    - self.inputs.SD[unit_g]
                )
                * self.w[unit_g, t + 1]
                - max(0, (self.inputs.SD[unit_g] - self.inputs.SU[unit_g]))
                * self.v[unit_g, t]
                for t in range(start_t, end_t - 1)  # The constraints index w at t+1
                for unit_g in self.inputs.thermal_units
                if self.inputs.TU[unit_g] == 1
            ),
            name="peakDownBnd",
        )

    def _c_peak_up_bound(self, sim_period: range) -> None:
        """Equation 23a of Kneuven et al (2019).
        This is the generation limit during the start-up of
        a peaking unit. A peaking unit has TU = 1.
        """
        start_t = sim_period[0]
        end_t = sim_period[-1]
        model.addConstrs(
            (
                self.p[unit_g, t] + self.spin[unit_g, t]
                <= (
                    self.inputs.thermal_derated_capacity.loc[t, unit_g]
                    - self.inputs.thermal_min_capacity[unit_g]
                )
                * self.u[unit_g, t]
                - (
                    self.inputs.thermal_derated_capacity.loc[t, unit_g]
                    - self.inputs.SU[unit_g]
                )
                * self.v[unit_g, t]
                - max(0, (self.inputs.SU[unit_g] - self.inputs.SD[unit_g]))
                * self.w[unit_g, t + 1]
                for t in range(start_t, end_t - 1)  # The constraints index w at t+1
                for unit_g in self.inputs.thermal_units
                if self.inputs.TU[unit_g] == 1
            ),
            name="peakUpBnd",
        )

    def _c_ramp_down_init(self, sim_period: range) -> None:
        """
        Equation 36 of Kneuven et al (2019). Ramping down at the initial timestep"""
        # Ramping when t=1 is dependent on the initial condition at t=0
        t = sim_period[0]
        model.addConstrs(
            (
                self.initial_p[unit_g, t - 1] - self.p[unit_g, t]
                <= (
                    self.inputs.SD[unit_g]
                    - self.inputs.thermal_min_capacity[unit_g]
                    - self.inputs.RD[unit_g]
                )
                * self.w[unit_g, t]
                + self.inputs.RD[unit_g] * self.initial_u[unit_g, t - 1]
                for unit_g in self.inputs.thermal_units
            ),
            name="rampDownInit",
        )

    def _c_ramp_down(self, sim_period: range) -> None:
        """Equation 36 of Kneuven et al (2019). Ramp-down constraint."""
        start_t = sim_period[0] + 1
        end_t = sim_period[-1]
        model.addConstrs(
            (
                self.p[unit_g, t - 1] - self.p[unit_g, t]
                <= (
                    self.inputs.SD[unit_g]
                    - self.inputs.thermal_min_capacity[unit_g]
                    - self.inputs.RD[unit_g]
                )
                * self.w[unit_g, t]
                + self.inputs.RD[unit_g] * self.u[unit_g, t - 1]
                for unit_g in self.inputs.thermal_units
                for t in range(start_t, end_t)
            ),
            name="rampDown",
        )

    def _c_ramp_up_init(self, sim_period: range) -> None:
        """Equation 35 of Kneuven et al (2019). Ramp-up constraint."""
        # Ramp up when t=1 is dependent on the initial condition at t=0
        t = sim_period[0]
        model.addConstrs(
            (
                self.pbar[unit_g, t] - self.initial_p[unit_g, t - 1]
                <= (
                    self.inputs.SU[unit_g]
                    - self.inputs.thermal_min_capacity[unit_g]
                    - self.inputs.RU[unit_g]
                )
                * self.v[unit_g, t]
                + self.inputs.RU[unit_g] * self.u[unit_g, t]
                for unit_g in self.inputs.thermal_units
            ),
            name="rampUpInit",
        )

    def _c_ramp_up(self, sim_period: range) -> None:
        """Equation 35 of Kneuven et al (2019). Ramp-up constraint."""
        start_t = sim_period[0] + 1
        end_t = sim_period[-1]

        model.addConstrs(
            (
                self.pbar[unit_g, t] - self.p[unit_g, t - 1]
                <= (
                    self.inputs.SU[unit_g]
                    - self.inputs.thermal_min_capacity[unit_g]
                    - self.inputs.RU[unit_g]
                )
                * self.v[unit_g, t]
                + self.inputs.RU[unit_g] * self.u[unit_g, t]
                for unit_g in self.inputs.thermal_units
                for t in range(start_t, end_t)
            ),
            name="rampUp",
        )

    def _c_ref_node(self, sim_period: range) -> None:
        """Equation 64d of Kneuven et al (2019).
        Set the voltage angle at a reference node to zero. We generally select
        a node with the largest demand.
        """
        model.addConstrs(
            (self.theta[self.inputs.max_demand_node, t] == 0 for t in sim_period),
            name="refNode",
        )

    def _c_angle_diff(self, sim_period: range) -> None:
        """Equation 64a of Kneuven et al (2019).
        The total flow in a line segment is limited by the difference in voltage angles.
        """
        model.addConstrs(
            (
                self.flow[a, b, t]
                == self.inputs.susceptance.loc[t, (a, b)]
                * (self.theta[a, t] - self.theta[b, t])
                for (a, b) in self.inputs.edges
                for t in sim_period
            ),
            name="angleDiff",
        )

    def _c_kirchhoff_voltage(self, sim_period: range) -> None:
        """Equation 23b in Horsch et al (2018). Although the paper states
        that it is mathematically equivalent to the voltage-angle formulation,
        both formulations will likely not produce the same solution due to the
        connectivity and selection of the reference node.
        """
        cycle_incidence = pd.DataFrame(
            0,
            index=pd.MultiIndex.from_tuples(
                self.inputs.edges, names=["source", "sink"]
            ),
            columns=self.inputs.cycle_map.keys(),
        )

        # The flow is positive with respect to the edges specified by the user
        for cycle_id, cycle in self.inputs.cycle_map.items():
            # Kirchhoff formulation requires summing along the loop direction.
            # If an arc is in cycle_graph and the input file, then 1. Otherwise, -1.
            cycle_graph = nx.path_graph(cycle)
            cycle_edges = list(cycle_graph.edges)
            # Append the last arc connecting the last node to the first node
            cycle_edges.append((cycle_edges[-1][-1], cycle_edges[0][0]))

            # We also need the reactance (susceptance) to calculate the factors in the cycle-incidence
            cycle_susceptance = pd.DataFrame()
            for flow in cycle_edges:
                if flow in self.inputs.edges:
                    cycle_incidence.loc[flow, cycle_id] = 1
                    cycle_susceptance = pd.concat(
                        [cycle_susceptance, self.inputs.susceptance[flow]], axis=1
                    )
                else:
                    cycle_incidence.loc[(flow[1], flow[0]), cycle_id] = -1
                    cycle_susceptance = pd.concat(
                        [
                            cycle_susceptance,
                            self.inputs.susceptance[(flow[1], flow[0])],
                        ],
                        axis=1,
                    )

            model.addConstrs(
                (
                    gp.quicksum(
                        (
                            cycle_incidence.loc[(a, b), cycle_id]
                            * 1
                            / cycle_susceptance.loc[t, [(a, b)]]
                            * self.flow[a, b, t]
                        ).iloc[0]
                        for (a, b) in cycle_susceptance.columns
                    )
                    == 0
                    for t in sim_period
                ),
                name=f"kirchhoff_{cycle_id}",
            )

    def _get_unit_generation(self, unit_g, t):
        """Helper method to get the generation for a given unit and time."""
        if unit_g in self.inputs.thermal_units:
            return self.dispatch[unit_g, t]
        if unit_g in self.inputs.hydro_units:
            return self.phydro[unit_g, t]
        if unit_g in self.inputs.solar_units:
            return self.psolar[unit_g, t]
        if unit_g in self.inputs.wind_units:
            return self.pwind[unit_g, t]
        if unit_g in self.inputs.import_units:
            return self.pimp[unit_g, t]
        return 0

    def _c_flow_balance(self, sim_period: range) -> None:
        """Equation 65 of Kneuven et al (2019).
        The energy balance at each node n and time t.
        """
        # We will tax all generators and import nodes with line loss
        line_efficiency = 1 - self.inputs.line_loss_factor
        for t in sim_period:
            for node in self.inputs.nodes:
                generation = 0
                for unit_g in self.inputs.node_generator[node]:
                    generation += self._get_unit_generation(unit_g, t)

                # Get the demand of node n at time t
                if node in self.inputs.demand_nodes:
                    demand_n_t = self.inputs.demand.loc[t, node]
                    mismatch = self.s_pos[node, t] - self.s_neg[node, t]
                else:
                    demand_n_t = 0
                    mismatch = 0

                # Flow into a node is positive, while flow out is negative
                arc_flow = 0
                for x, y in self.inputs.node_edge[node]:
                    if x == node:
                        arc_flow -= self.flow[x, y, t]
                    elif y == node:
                        arc_flow += self.flow[x, y, t]

                # Given the above terms, we can specify the energy balance
                model.addConstr(
                    (generation + arc_flow * line_efficiency + mismatch == demand_n_t),
                    name="flowBal" + f"[{node},{t}]",
                )

    def _c_reserve_req_1(self, sim_period: range) -> None:
        """Equation 67 of Kneuven et al (2019). System-wide spinning reserve requirement.
        We substitute in the max_dispatch using Equation 13.
        """
        model.addConstrs(
            (
                gp.quicksum(
                    self.pbar[unit_g, t]
                    + self.inputs.thermal_min_capacity[unit_g] * self.u[unit_g, t]
                    for unit_g in self.inputs.thermal_units
                )
                + self.sys_spin[t]
                >= gp.quicksum(
                    self.inputs.demand.loc[t, n] for n in self.inputs.demand_nodes
                )
                + self.inputs.spin_req[t]
                for t in sim_period
            ),
            name="reserveReq",
        )

    def _c_reserve_req_2(self, sim_period: range) -> None:
        """Equation 68 of Kneuven et al (2019). This spinning reserve constraint
        is based on Morales-España et al. (2013).

        """
        model.addConstrs(
            (
                gp.quicksum(
                    self.spin[unit_g, t] for unit_g in self.inputs.thermal_units
                )
                + self.sys_spin[t]
                >= self.inputs.spin_req[t]
                for t in sim_period
            ),
            name="reserveReq",
        )

    def _c_hydro_limit_hourly(self, sim_period: range) -> None:
        """Hydro generation must be less than the maximum capacity of the hydro unit."""
        model.addConstrs(
            (
                self.phydro[hydro_unit, t]
                <= self.inputs.hydro_capacity.loc[t, hydro_unit]
                for t in sim_period
                for hydro_unit in self.inputs.hydro_units
            ),
            name="hydroLimit_hr",
        )

    def _c_hydro_limit_daily(self, step_k: range) -> None:
        raise NotImplementedError("Daily hydro limit is not implemented yet.")
        start_t = sim_period[0]
        end_t = sim_period[-1]
        model.addConstrs(
            (
                gp.quicksum(self.phydro[hydro_unit, t] for t in sim_period)
                <= gp.quicksum(
                    self.inputs.hydro_capacity.loc[
                        (self.k * self.T) / 24
                        + 1 : (self.k * self.T) / 24
                        + self.T / 24,
                        hydro_unit,
                    ]
                )
                for hydro_unit in self.inputs.hydro_units
            ),
            name="hydroLimit_day",
        )

    def _add_constraints(self, sim_period: range) -> None:
        # ---------------- Section: Constraints
        self._c_link_uvw_init(sim_period)
        self._c_link_uvw(sim_period)
        self._c_link_dispatch(sim_period)
        self._c_link_p(sim_period)
        self._c_link_pu_lower(sim_period)
        self._c_link_pu_upper(sim_period)

        self._c_min_down_init(sim_period)
        self._c_min_up_init()

        self._c_min_down()
        self._c_min_up()

        # We do not have shut-down rate or start-up rate for thermal units
        # self._c_peak_down_bound()
        # self._c_peak_up_bound()

        self._c_ramp_down()
        self._c_ramp_up()

        if self.inputs.dc_opf == "voltage_angle":
            self._c_ref_node()
            self._c_angle_diff()
        elif self.inputs.dc_opf == "kirchhoff":
            self._c_kirchhoff_voltage()

        # There are two ways to enforce the hydro limit.
        if self.hydro_timestep == "hourly":
            self._c_hydro_limit_hourly()
        else:
            self._c_hydro_limit_daily()

        self._c_flow_balance()
        self._c_reserve_req_1()

        # Update the model just in case we want to check model structure
        model.update()

    def build(
        self,
        step_k: int,
        init_conds: dict[str, dict],
        sim_period: range,
    ) -> PowerSystemModel:
        self.step_k = step_k

        self.initial_p = init_conds["initial_p"]
        self.initial_u = init_conds["initial_u"]
        self.initial_v = init_conds["initial_v"]
        self.initial_w = init_conds["initial_w"]

        # These two variables are scalar. Defining the remaining time required
        # to be on or off.
        self.initial_min_on = init_conds["initial_min_on"]
        self.initial_min_off = init_conds["initial_min_off"]

        # Create a gurobipy model along with parameter settings
        model = gp.Model(f"{model_name}_{step_k+1}")

        self._add_variables(sim_period=sim_period)
        self._set_objective(sim_period=sim_period)
        self._add_constraints(sim_period=sim_period)

        return PowerSystemModel(model)

    def update(
        self,
        step_k: int,
        init_conds: dict[str, dict],
        do_warmstart: bool,
    ) -> None:
        """Update the model instead of creating a new one
        so we can perform warm start
        """
        # TODO: Consider updating the model instead of creating a new one
        # Update cost coeffs, constraints, RHS
        model = self.build(
            step_k,
            init_conds,
        )

        # Use the solution from the previous solve
        if do_warmstart:
            previous_solution_file = os.path.join(
                get_output_dir(), f"{model_name}_{step_k-1}.sol"
            )
            model.read(previous_solution_file)
            # Delete the since we have loaded the solution
            os.remove(previous_solution_file)

        return model

    def get_hydro_capacity(self) -> pd.DataFrame:
        raise NotImplementedError("Method not implemented yet.")
        if self.hydro_timestep == "daily":
            return self.inputs.hydro_capacity.loc[
                self.T * self.k + 1 : self.T * self.k + self.T
            ]
        else:
            return self.inputs.hydro_capacity.loc[
                self.T * self.k + 1 : self.T * self.k + self.T
            ]

    def update_hydro_capacity(self, new_hydro_capacity: pd.DataFrame) -> None:
        raise NotImplementedError("Method not implemented yet.")
        if self.hydro_timestep == "hourly":
            # Divid new_hydro_capacity evenly across the day
            hourly_hydro_capacity = new_hydro_capacity / 24
            # Repeat the hourly hydro capacity for the entire day
            hourly_hydro_capacity = pd.concat(
                [hourly_hydro_capacity] * 24, ignore_index=True
            )
            # Indexing of timeseries for model building starts at 1
            hourly_hydro_capacity.index += 1

            start_idx = self.T * self.k + 1
            end_idx = self.T * self.k + self.T
            self.inputs.hydro_capacity.loc[
                start_idx:end_idx, hourly_hydro_capacity.columns
            ] = hourly_hydro_capacity.values

        elif self.hydro_timestep == "daily":
            day = new_hydro_capacity.index
            self.inputs.hydro_capacity.loc[day, new_hydro_capacity.columns] = (
                new_hydro_capacity.values
            )
