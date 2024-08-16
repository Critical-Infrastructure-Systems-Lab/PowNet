""" builder.py: ModelBuilder class builds and updates the unit commitment problem.
"""

from __future__ import annotations

import os

from gurobipy import GRB
import gurobipy as gp
import pandas as pd

import pownet.modeling as modeling
from pownet.data_utils import create_init_condition
from pownet.folder_utils import get_output_dir


class ModelBuilder:
    """Build an instance of the Unit Commitment Problem.
    We keep the instance of the Gurobi model throughout simulation to minimize
    the overhead of creating a new model for each iteration and also benefit from
    the warm start feature of Gurobi. This means the following:
    * Variable names are unchanged across iterations
    * Only a subset of constraints are updated at each iteration
      - Remove and build the objective function
      - Update the upper bounds of variables
      - Remove and add constraints that are time-dependent, such as

    Define the lower/upper bounds explicitly at the variable level instead of
    defining them as constraints. This approach can leverage gurobi's presolve
    and reduce the size of the model.

    """

    def __init__(self, inputs: "SystemInput") -> None:
        self.inputs = inputs

        self.timesteps = range(1, self.inputs.sim_horizon + 1)
        # Define the simulation horizon
        self.T: int = self.inputs.sim_horizon

        # Initialize the model
        model_name: str = (
            f"{self.inputs.timestamp}_{self.inputs.model_name}_{self.inputs.sim_horizon}"
        )
        self.model: gp.Model = gp.Model(model_name)

        # Variables
        # Thermal units
        self.pthermal: gp.tupledict = {}
        self.status: gp.tupledict = {}
        self.startup: gp.tupledict = {}
        self.shutdown: gp.tupledict = {}
        self.vpower: gp.tupledict = {}
        self.vpowerbar: gp.tupledict = {}
        self.spin: gp.tupledict = {}

        # Renewable energy and import sources
        self.phydro: gp.tupledict = {}
        self.psolar: gp.tupledict = {}
        self.pwind: gp.tupledict = {}
        self.pimp: gp.tupledict = {}  # import

        # Node variables
        self.pos_pmismatch: gp.tupledict = {}
        self.neg_pmismatch: gp.tupledict = {}

        # Flow variables
        self.flow: gp.tupledict = {}
        self.theta: gp.tupledict = {}

        # System-wide variables
        self.spin_shortfall: gp.tupledict = {}

        # Time-independent terms in the objective function
        self.thermal_fixed_expr: gp.LinExpr = gp.LinExpr()
        self.thermal_opex_expr: gp.LinExpr = gp.LinExpr()
        self.thermal_startup_expr: gp.LinExpr = gp.LinExpr()
        self.load_shortfall_penalty_expr: gp.LinExpr = gp.LinExpr()
        self.spin_shortfall_penalty_expr: gp.LinExpr = gp.LinExpr()

        # Time-dependent constraints that are removed and added at each iteration
        self.c_link_uvw_init: gp.tupledict = None
        self.c_link_pu_upper: gp.tupledict = None
        self.c_min_down_init: gp.tupledict = None
        self.c_min_up_init: gp.tupledict = None
        # self.c_peak_down_bound: gp.tupledict = None
        # self.c_peak_up_bound: gp.tupledict = None
        self.c_ramp_down_init: gp.tupledict = None
        self.c_ramp_up_init: gp.tupledict = None
        self.c_angle_diff: gp.tupledict = None
        self.c_kirchhoff: gp.tupledict = None
        self.c_flow_balance: gp.tupledict = None
        self.c_hydro_capacity: gp.tupledict = None
        self.c_reserve_req: gp.tupledict = None

    def add_variables(self, step_k: int) -> None:
        """Add variables to the model. The variables are grouped into
        thermal units, renewable energy sources, and imports, nodes, and flows.
        The bounds of some variables are time-dependent, so we will update them
        at each iteration.
        """

        ################################
        # Thermal-unit variables
        ################################
        self.pthermal = modeling.add_var_pthermal(
            model=self.model,
            timesteps=self.timesteps,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
            thermal_derated_capacity=self.inputs.thermal_derated_capacity,
        )

        self.status = modeling.add_var_status(
            model=self.model,
            timesteps=self.timesteps,
            thermal_units=self.inputs.thermal_units,
        )

        self.startup = modeling.add_var_startup(
            model=self.model,
            timesteps=self.timesteps,
            thermal_units=self.inputs.thermal_units,
        )

        self.shutdown = modeling.add_var_shutdown(
            model=self.model,
            timesteps=self.timesteps,
            thermal_units=self.inputs.thermal_units,
        )

        self.vpower = modeling.add_var_vpower(
            model=self.model,
            timesteps=self.timesteps,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
            thermal_derated_capacity=self.inputs.thermal_derated_capacity,
        )

        self.vpowerbar = modeling.add_var_vpowerbar(
            model=self.model,
            timesteps=self.timesteps,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
            thermal_derated_capacity=self.inputs.thermal_derated_capacity,
        )

        if self.inputs.use_spin_var:
            self.spin = modeling.add_var_spin(
                model=self.model,
                timesteps=self.timesteps,
                step_k=step_k,
                sim_horizon=self.inputs.sim_horizon,
                thermal_units=self.inputs.thermal_units,
                thermal_min_capacity=self.inputs.thermal_min_capacity,
                thermal_derated_capacity=self.inputs.thermal_derated_capacity,
            )

        ################################
        # Renewable energy and import variables
        ################################

        if self.inputs.hydro_timestep == "hourly":
            self.phydro = modeling.add_var_phydro(
                model=self.model,
                timesteps=self.timesteps,
                step_k=step_k,
                sim_horizon=self.inputs.sim_horizon,
                hydro_units=self.inputs.hydro_units,
                hydro_capacity=self.inputs.hydro_capacity,
            )
        elif self.inputs.hydro_timestep == "daily":
            self.phydro = modeling.add_var_phydro2(
                model=self.model,
                timesteps=self.timesteps,
                hydro_units=self.inputs.hydro_units,
            )
        elif self.inputs.hydro_timestep == "none":
            pass  # No hydropower
        else:
            raise ValueError(
                f"Invalid hydro_timestep parameter: {self.inputs.hydro_timestep}."
            )

        self.psolar = modeling.add_var_psolar(
            model=self.model,
            timesteps=self.timesteps,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            solar_units=self.inputs.solar_units,
            solar_capacity=self.inputs.solar_capacity,
        )

        self.pwind = modeling.add_var_pwind(
            model=self.model,
            timesteps=self.timesteps,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            wind_units=self.inputs.wind_units,
            wind_capacity=self.inputs.wind_capacity,
        )

        self.pimp = modeling.add_var_pimp(
            model=self.model,
            timesteps=self.timesteps,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            import_units=self.inputs.import_units,
            import_capacity=self.inputs.import_capacity,
        )

        ################################
        # Node variables
        ################################

        self.pos_pmismatch = modeling.add_var_pos_pmismatch(
            model=self.model,
            timesteps=self.timesteps,
            demand_nodes=self.inputs.nodes,
        )

        self.neg_pmismatch = modeling.add_var_neg_pmismatch(
            model=self.model,
            timesteps=self.timesteps,
            demand_nodes=self.inputs.nodes,
        )

        ################################
        # Flow variables
        ################################

        if self.inputs.dc_opf == "kirchhoff":
            self.flow = modeling.add_var_flow(
                model=self.model,
                timesteps=self.timesteps,
                step_k=step_k,
                sim_horizon=self.inputs.sim_horizon,
                edges=self.inputs.edges,
                line_capacity_factor=self.inputs.line_capacity_factor,
                line_capacity=self.inputs.line_capacity,
            )
        elif self.inputs.dc_opf == "voltage_angle":
            self.theta = modeling.add_var_voltage_angle(
                model=self.model,
                timesteps=self.timesteps,
                nodes=self.inputs.nodes,
            )
        else:
            raise ValueError(f"Invalid DC-OPF parameter: {self.dc_opf}.")

        ################################
        # System variables
        ################################

        self.spin_shortfall = modeling.add_var_spin_shortfall(
            model=self.model,
            timesteps=self.timesteps,
        )

        self.model.update()

    def set_objfunc(self, step_k: int) -> None:
        """The objective function has four components: unit fixed cost, unit variable cost,
        unit start-up cost, and shortfall cost. THe objective function is to minimize the
        total cost of generation and shortfall. Some terms are time-dependent, such as
        the unit variable cost.

        Args:
            model: The Gurobi model instance.
            step_k: The current step of the simulation.

        Returns:
            None

        """

        ################################
        # Thermal units
        ################################
        thermal_fixed_coeffs = modeling.get_thermal_fixed_coeff(
            timesteps=self.timesteps,
            thermal_units=self.inputs.thermal_units,
            thermal_fixed_cost=self.inputs.thermal_fixed_cost,
            thermal_rated_capacity=self.inputs.thermal_rated_capacity,
        )
        self.thermal_fixed_expr = self.status.prod(thermal_fixed_coeffs)

        # TODO: thermal_fuel_cost should be a time-dependent parameter
        # (Separate out fuel cost from the OPEX cost)
        thermal_opex_coeffs = modeling.get_thermal_opex_coeff(
            timesteps=self.timesteps,
            thermal_units=self.inputs.thermal_units,
            thermal_opex=self.inputs.thermal_opex,
            thermal_fuel_cost=self.inputs.thermal_fuel_cost,
            thermal_heat_rate=self.inputs.thermal_heat_rate,
        )
        self.thermal_opex_expr = self.pthermal.prod(thermal_opex_coeffs)

        thermal_startup_coeffs = modeling.get_thermal_startup_coeff(
            timesteps=self.timesteps,
            thermal_units=self.inputs.thermal_units,
            thermal_startup_cost=self.inputs.thermal_startup_cost,
            thermal_rated_capacity=self.inputs.thermal_rated_capacity,
        )
        self.thermal_startup_expr = self.startup.prod(thermal_startup_coeffs)

        ################################
        # Renewables and import. These are time-dependent
        ################################

        # Cost coefficients of hydro, solar, wind, and import
        hydro_coeffs = modeling.get_marginal_cost_coeff(
            inputs=self.inputs,
            timesteps=self.timesteps,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            units=self.inputs.hydro_units,
            attribute="unit_marginal_cost",
        )
        hydro_expr = self.phydro.prod(hydro_coeffs)

        solar_coeffs = modeling.get_marginal_cost_coeff(
            inputs=self.inputs,
            timesteps=self.timesteps,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            units=self.inputs.solar_units,
            attribute="unit_marginal_cost",
        )
        solar_expr = self.psolar.prod(solar_coeffs)

        wind_coeffs = modeling.get_marginal_cost_coeff(
            inputs=self.inputs,
            timesteps=self.timesteps,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            units=self.inputs.wind_units,
            attribute="unit_marginal_cost",
        )
        wind_expr = self.pwind.prod(wind_coeffs)

        import_coeffs = modeling.get_marginal_cost_coeff(
            inputs=self.inputs,
            timesteps=self.timesteps,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            units=self.inputs.import_units,
            attribute="unit_marginal_cost",
        )
        import_expr = self.pimp.prod(import_coeffs)

        # The cost of shortfall is the slack variable (pos_pmismatch) needed to meet demand
        self.load_shortfall_penalty_expr = self.inputs.load_shortfall_penalty_factor * (
            gp.quicksum(self.pos_pmismatch) + gp.quicksum(self.neg_pmismatch)
        )

        # Penalize the system if it cannot meet the spinning reserve requirement
        self.spin_shortfall_penalty_expr = (
            self.inputs.spin_shortfall_penalty_factor * gp.quicksum(self.spin_shortfall)
        )

        self.model.setObjective(
            (
                self.thermal_fixed_expr
                + self.thermal_opex_expr
                + self.thermal_startup_expr
                + hydro_expr
                + solar_expr
                + wind_expr
                + import_expr
                + self.load_shortfall_penalty_expr
                + self.spin_shortfall_penalty_expr
            ),
            sense=GRB.MINIMIZE,
        )
        self.model.update()

    def add_constraints(self, step_k: int, init_conds: dict) -> None:
        ################################
        # Therma-unit constraints
        ################################

        self.c_link_uvw_init = modeling.add_c_link_uvw_init(
            model=self.model,
            u=self.status,
            v=self.startup,
            w=self.shutdown,
            initial_u=init_conds["initial_u"],
            thermal_units=self.inputs.thermal_units,
        )
        modeling.add_c_link_uvw(
            model=self.model,
            u=self.status,
            v=self.startup,
            w=self.shutdown,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
        )
        modeling.add_c_link_pthermal(
            model=self.model,
            pthermal=self.pthermal,
            p=self.vpower,
            u=self.status,
            timesteps=self.timesteps,
            thermal_units=self.inputs.thermal_units,
            thermal_min_capacity=self.inputs.thermal_min_capacity,
        )
        modeling.add_c_link_pu_lower(
            model=self.model,
            pthermal=self.pthermal,
            u=self.status,
            timesteps=self.timesteps,
            thermal_units=self.inputs.thermal_units,
            thermal_min_capacity=self.inputs.thermal_min_capacity,
        )
        self.c_link_pu_upper = modeling.add_c_link_pu_upper(
            model=self.model,
            pbar=self.vpowerbar,
            u=self.status,
            timesteps=self.timesteps,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
            thermal_min_capacity=self.inputs.thermal_min_capacity,
            thermal_derated_capacity=self.inputs.thermal_derated_capacity,
        )
        self.c_min_down_init = modeling.add_c_min_down_init(
            model=self.model,
            u=self.status,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
            initial_min_off=init_conds["initial_min_off"],
        )
        self.c_min_up_init = modeling.add_c_min_up_init(
            model=self.model,
            u=self.status,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
            initial_min_on=init_conds["initial_min_on"],
        )
        modeling.add_c_min_down(
            model=self.model,
            u=self.status,
            w=self.shutdown,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
            TD=self.inputs.TD,
        )
        modeling.add_c_min_up(
            model=self.model,
            u=self.status,
            v=self.startup,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
            TU=self.inputs.TU,
        )

        # Currently not implemented because we set SD = SU = ramping
        # self.c_peak_down_bound = modeling.add_c_peak_down_bound(
        #     model=self.model,
        #     p=self.vpower,
        #     spin=self.spin,
        #     u=self.status,
        #     v=self.startup,
        #     w=self.shutdown,
        #     sim_horizon=self.inputs.sim_horizon,
        #     step_k=step_k,
        #     thermal_units=self.inputs.thermal_units,
        #     thermal_min_capacity=self.inputs.thermal_min_capacity,
        #     thermal_derated_capacity=self.inputs.thermal_derated_capacity,
        #     SD=self.inputs.SD,
        #     SU=self.inputs.SU,
        #     TU=self.inputs.TU,
        # )

        # self.c_peak_up_bound = modeling.add_c_peak_up_bound(
        #     model=self.model,
        #     p=self.vpower,
        #     spin=self.spin,
        #     u=self.status,
        #     v=self.startup,
        #     w=self.shutdown,
        #     sim_horizon=self.inputs.sim_horizon,
        #     step_k=step_k,
        #     thermal_units=self.inputs.thermal_units,
        #     thermal_min_capacity=self.inputs.thermal_min_capacity,
        #     thermal_derated_capacity=self.inputs.thermal_derated_capacity,
        #     SD=self.inputs.SD,
        #     SU=self.inputs.SU,
        #     TU=self.inputs.TU,
        # )

        self.c_ramp_down_init = modeling.add_c_ramp_down_init(
            model=self.model,
            p=self.vpower,
            w=self.shutdown,
            thermal_units=self.inputs.thermal_units,
            initial_p=init_conds["initial_p"],
            initial_u=init_conds["initial_u"],
            thermal_min_capacity=self.inputs.thermal_min_capacity,
            RD=self.inputs.RD,
            SD=self.inputs.SD,
        )
        self.c_ramp_up_init = modeling.add_c_ramp_up_init(
            model=self.model,
            pbar=self.vpowerbar,
            u=self.status,
            v=self.startup,
            thermal_units=self.inputs.thermal_units,
            initial_p=init_conds["initial_p"],
            thermal_min_capacity=self.inputs.thermal_min_capacity,
            RU=self.inputs.RU,
            SU=self.inputs.SU,
        )
        modeling.add_c_ramp_down(
            model=self.model,
            p=self.vpower,
            u=self.status,
            w=self.shutdown,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
            thermal_min_capacity=self.inputs.thermal_min_capacity,
            RD=self.inputs.RD,
            SD=self.inputs.SD,
        )
        modeling.add_c_ramp_up(
            model=self.model,
            p=self.vpower,
            pbar=self.vpowerbar,
            u=self.status,
            v=self.startup,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
            thermal_min_capacity=self.inputs.thermal_min_capacity,
            RU=self.inputs.RU,
            SU=self.inputs.SU,
        )

        ################################
        # Power flow constraints
        ################################

        if self.inputs.dc_opf == "voltage_angle":
            modeling.add_c_ref_node(
                model=self.model,
                theta=self.theta,
                timesteps=self.timesteps,
                max_demand_node=self.inputs.max_demand_node,
            )
            self.c_angle_diff = modeling.add_c_angle_diff(
                model=self.model,
                flow=self.flow,
                theta=self.theta,
                timesteps=self.timesteps,
                sim_horizon=self.inputs.sim_horizon,
                step_k=step_k,
                edges=self.inputs.edges,
                susceptance=self.inputs.susceptance,
            )
        elif self.inputs.dc_opf == "kirchhoff":
            self.c_kirchhoff = modeling.add_c_kirchhoff(
                model=self.model,
                flow=self.flow,
                timesteps=self.timesteps,
                sim_horizon=self.inputs.sim_horizon,
                step_k=step_k,
                edges=self.inputs.edges,
                cycle_map=self.inputs.cycle_map,
                susceptance=self.inputs.susceptance,
            )
        else:
            raise ValueError(f"Invalid DC-OPF parameter: {self.dc_opf}.")

        self.c_flow_balance = modeling.add_c_flow_balance(
            model=self.model,
            pthermal=self.pthermal,
            phydro=self.phydro,
            psolar=self.psolar,
            pwind=self.pwind,
            pimp=self.pimp,
            pos_pmismatch=self.pos_pmismatch,
            neg_pmismatch=self.neg_pmismatch,
            flow=self.flow,
            timesteps=self.timesteps,
            sim_horizon=self.inputs.sim_horizon,
            step_k=step_k,
            inputs=self.inputs,
            nodes=self.inputs.nodes,
            node_edge=self.inputs.node_edge,
            node_generator=self.inputs.node_generator,
            demand_nodes=self.inputs.demand_nodes,
            demand=self.inputs.demand,
            line_loss_factor=self.inputs.line_loss_factor,
        )

        ################################
        # Hydropower constraint
        ################################

        # There are two ways to enforce the hydro limit.
        if self.inputs.hydro_timestep == "hourly":
            # Hydropower is limited by the upper bound of phydro
            pass
        elif self.inputs.hydro_timestep == "daily":
            # In this case, phydro is not bounded, so we need to add a constraint
            self.c_hydro_capacity = self.inputs.hydro_capacity(
                model=self.model,
                phydro=self.phydro,
                timesteps=self.timesteps,
                step_k=step_k,
                sim_horizon=self.inputs.sim_horizon,
                hydro_units=self.inputs.hydro_units,
                hydro_capacity=self.inputs.hydro_capacity,
            )
        elif self.inputs.hydro_timestep == "none":
            pass
        else:
            raise ValueError(
                f"Invalid hydro_timestep parameter: {self.inputs.hydro_timestep}."
            )

        if self.inputs.use_spin_var:
            modeling.add_c_link_spin(
                model=self.model,
                p=self.vpower,
                pbar=self.vpowerbar,
                spin=self.spin,
                timesteps=self.timesteps,
                thermal_units=self.inputs.thermal_units,
            )
            self.c_reserve_req = modeling.add_c_reserve_req_1(
                model=self.model,
                spin=self.spin,
                spin_shortfall=self.spin_shortfall,
                timesteps=self.timesteps,
                sim_horizon=self.inputs.sim_horizon,
                step_k=step_k,
                thermal_units=self.inputs.thermal_units,
                spin_requirement=self.inputs.spin_requirement,
            )
        else:
            modeling.add_c_link_ppbar(
                model=self.model,
                p=self.vpower,
                pbar=self.vpowerbar,
                timesteps=self.timesteps,
                thermal_units=self.inputs.thermal_units,
            )
            self.c_reserve_req = modeling.add_c_reserve_req_2(
                model=self.model,
                pbar=self.vpowerbar,
                u=self.status,
                spin_shortfall=self.spin_shortfall,
                timesteps=self.timesteps,
                sim_horizon=self.inputs.sim_horizon,
                step_k=step_k,
                thermal_units=self.inputs.thermal_units,
                thermal_min_capacity=self.inputs.thermal_min_capacity,
                demand_nodes=self.inputs.demand_nodes,
                demand=self.inputs.demand,
                spin_requirement=self.inputs.spin_requirement,
            )

        # Update the model just in case we want to check model structure
        self.model.update()

    def build(
        self,
        step_k: int,
        init_conds: dict[str, dict],
    ) -> gp.Model:
        """Build the model for the unit commitment problem."""

        self.add_variables(step_k=step_k)
        self.set_objfunc(step_k=step_k)
        self.add_constraints(step_k=step_k, init_conds=init_conds)

        return self.model

    def _update_variable_bounds(self) -> None:
        pass

    def _update_objective(self) -> None:
        pass

    def _update_constraint_bounds(self) -> None:
        pass

    def update(
        self,
        step_k: int,
        init_conds: dict[str, dict],
    ) -> gp.Model:
        """Update the model instead of creating a new one
        so we can perform warm start
        """
        # Update the objective function

        # Change the upper bounds of variables that are dependent on step_k

        # Remove and update constraints that are dependent on step_k
        self.c_link_uvw_init

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
