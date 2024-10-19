""" builder.py: ModelBuilder class builds and updates the unit commitment problem.
"""

from .input import SystemInput
import logging

from gurobipy import GRB
import gurobipy as gp
import pandas as pd

import pownet.modeling as modeling
from pownet.modeling import PowerSystemModel
from pownet.data_utils import get_unit_hour_from_varnam, get_edge_hour_from_varname

logger = logging.getLogger(__name__)


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

    def __init__(self, inputs: SystemInput) -> None:
        self.inputs = inputs

        self.timesteps = range(1, self.inputs.sim_horizon + 1)

        self.model: gp.Model = None

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
        self.phydro: gp.tupledict = gp.tupledict()
        self.psolar: gp.tupledict = gp.tupledict()
        self.pwind: gp.tupledict = gp.tupledict()
        self.pimp: gp.tupledict = gp.tupledict()  # import

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

        # Constraints
        self.c_link_uvw_init: gp.tupledict = None
        self.c_link_uvw: gp.tupledict = None
        self.c_link_pthermal: gp.tupledict = None
        self.c_link_pu_lower: gp.tupledict = None
        self.c_link_pu_upper: gp.tupledict = None
        self.c_min_down_init: gp.tupledict = None
        self.c_min_up_init: gp.tupledict = None
        self.c_min_down: gp.tupledict = None
        self.c_min_up: gp.tupledict = None
        self.c_peak_down_bound: gp.tupledict = None
        self.c_peak_up_bound: gp.tupledict = None
        self.c_ramp_down_init: gp.tupledict = None
        self.c_ramp_up_init: gp.tupledict = None
        self.c_ramp_down: gp.tupledict = None
        self.c_ramp_up: gp.tupledict = None
        self.c_ref_node: gp.tupledict = None
        self.c_angle_diff: gp.tupledict = None
        self.c_kirchhoff: gp.tupledict = None
        self.c_flow_balance: gp.tupledict = None
        self.c_hydro_capacity: gp.tupledict = None
        self.c_link_spin: gp.tupledict = None
        self.c_link_ppbar: gp.tupledict = None
        self.c_reserve_req: gp.tupledict = None

    def add_variables(self, step_k: int) -> None:
        """Add variables to the model. The variables are grouped into
        thermal units, renewable energy sources, and imports, nodes, and flows.

        Thermal-unit variables:
        -----------------
        - `pthermal`: Power output by a thermal unit (also called dispatch). Unit: MW.
        - `vpower`: Power output *ABOVE* the minimum capacity of a thermal unit. Unit: MW.
        - `vpowerbar`: Maximum power output *ABOVE* the minimum capacity of a thermal unit. Unit: MW.
        - `status`: Indicator of online status. On = 1 and off = 0. Unitless.
        - `startup`: Indicator if a unit is shutting down. Unitless.
        - `shutdown`: Indicator if a unit is starting up. Unitless.
        - `spin` (optional): Spinning reserve. Unit: MW.

        Renewable energy and import variables:
        -----------------
        - `psolar`: Solar power output. Unit: MW.
        - `pwind`: Wind power output. Unit: MW.
        - `pimp`: Import power output. Unit: MW.
        - `phydro`: Hydropower output. Unit: MW.

        Node variables:
        -----------------
        - `pos_pmismatch`: Positive power mismatch. Unit: MW.
        - `neg_pmismatch`: Negative power mismatch. Unit: MW.

        Flow variables:
        -----------------
        - `flow`: Power flow on transmission lines. Unit: MW/hr.
        - `theta`: Voltage angle. Unit: Radians.

        System variables:
        -----------------
        - `spin_shortfall`: Spinning reserve shortfall. Unit: MW.

        Args:
            step_k: The current step of the simulation.

        Returns:
            None

        """

        ################################
        # Variables without upper bounds
        ################################

        var_with_ub_tuples = [
            ("pthermal", "thermal_units", self.inputs.thermal_derated_capacity),
            ("vpower", "thermal_units", self.inputs.thermal_derated_capacity),
            ["vpowerbar", "thermal_units", self.inputs.thermal_derated_capacity],
            ("psolar", "solar_units", self.inputs.solar_capacity),
            ("pwind", "wind_units", self.inputs.wind_capacity),
            ("pimp", "import_units", self.inputs.import_capacity),
        ]

        for varname, unit_type, capacity_df in var_with_ub_tuples:
            # Update the self attribute directly
            setattr(
                self,
                varname,
                modeling.add_var_with_ub(
                    model=self.model,
                    varname=varname,
                    timesteps=self.timesteps,
                    step_k=step_k,
                    units=getattr(self.inputs, unit_type),
                    capacity_df=capacity_df,
                ),
            )

        ################################
        # Variables without upper bounds
        ################################

        vars_tuples = [
            ("pos_pmismatch", "demand_nodes"),
            ("neg_pmismatch", "demand_nodes"),
        ]

        for varname, unit_type in vars_tuples:
            setattr(
                self,
                varname,
                self.model.addVars(
                    getattr(self.inputs, unit_type),
                    self.timesteps,
                    name=varname,
                ),
            )

        # Spinning reserve can be modeled with or without
        # the spin variable
        if self.inputs.use_spin_var:
            self.spin = self.model.addVars(
                self.inputs.thermal_units,
                self.timesteps,
                name="spin",
            )

        # System-wide spinning reserve shortfall
        self.spin_shortfall = self.model.addVars(
            self.timesteps,
            name="spin_shortfall",
        )

        ################################
        # Binary variables of thermal units
        ################################
        var_binary_tuples = [
            ("status", "thermal_units"),
            ("startup", "thermal_units"),
            ("shutdown", "thermal_units"),
        ]
        for varname, unit_type in var_binary_tuples:
            setattr(
                self,
                varname,
                self.model.addVars(
                    self.inputs.thermal_units,
                    self.timesteps,
                    vtype=GRB.BINARY,
                    name=varname,
                ),
            )

        ################################
        # Daily hydropower availability is limited by a constraint expression
        # instead of an upper bound on the variables
        ################################

        if self.inputs.hydro_timestep == "hourly":
            setattr(
                self,
                "phydro",
                modeling.add_var_with_ub(
                    model=self.model,
                    varname="phydro",
                    timesteps=self.timesteps,
                    step_k=step_k,
                    units=getattr(self.inputs, "hydro_units"),
                    capacity_df=self.inputs.hydro_capacity,
                ),
            )
        elif self.inputs.hydro_timestep == "daily":
            self.phydro = self.model.addVars(
                self.inputs.hydro_units,
                self.timesteps,
                lb=0,
                vtype=GRB.CONTINUOUS,
                name="phydro",
            )
        elif self.inputs.hydro_timestep == "none":
            pass  # No hydropower
        else:
            raise ValueError(
                f"Invalid hydro_timestep parameter: {self.inputs.hydro_timestep}."
            )

        ################################
        # Flow variables
        ################################

        self.flow = modeling.add_var_flow(
            model=self.model,
            timesteps=self.timesteps,
            step_k=step_k,
            edges=self.inputs.edges,
            line_capacity_factor=self.inputs.line_capacity_factor,
            line_capacity=self.inputs.line_capacity,
        )

        if self.inputs.dc_opf == "voltage_angle":
            self.theta = modeling.add_var_voltage_angle(
                model=self.model,
                timesteps=self.timesteps,
                nodes=self.inputs.nodes,
            )

        ################################
        # End of adding variables
        ################################

        self.model.update()

    def _build_rnw_import_objfunc_terms(self, step_k: int) -> gp.LinExpr:
        """Build the objective function for renewable energy and import sources."""
        variable_unit_pairs = [
            (self.phydro, self.inputs.hydro_units),
            (self.psolar, self.inputs.solar_units),
            (self.pwind, self.inputs.wind_units),
            (self.pimp, self.inputs.import_units),
        ]
        rnw_import_expr = gp.LinExpr()
        for var_dict, units in variable_unit_pairs:
            cost_coeffs = modeling.get_marginal_cost_coeff(
                inputs=self.inputs,
                timesteps=self.timesteps,
                step_k=step_k,
                units=units,
                attribute="unit_marginal_cost",
            )
            rnw_import_expr.add(var_dict.prod(cost_coeffs))
        return rnw_import_expr

    def set_objfunc(self, step_k: int) -> None:
        """The objective function has four components: unit fixed cost, unit variable cost,
        unit start-up cost, and shortfall cost. THe objective function is to minimize the
        total cost of generation and shortfall. Some terms are time-dependent, such as
        the unit variable cost.

        Args:
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
        # Shortfall penalties
        ################################

        # The cost of shortfall is the slack variable (pos_pmismatch) needed to meet demand
        self.load_shortfall_penalty_expr = self.inputs.load_shortfall_penalty_factor * (
            gp.quicksum(self.pos_pmismatch)
        ) + (self.inputs.load_curtail_penalty_factor * gp.quicksum(self.neg_pmismatch))

        # Penalize the system if it cannot meet the spinning reserve requirement
        self.spin_shortfall_penalty_expr = (
            self.inputs.spin_shortfall_penalty_factor * gp.quicksum(self.spin_shortfall)
        )

        ################################
        # Renewable energy and import sources
        ################################
        rnw_import_expr = self._build_rnw_import_objfunc_terms(step_k=step_k)

        self.model.setObjective(
            (
                self.thermal_fixed_expr
                + self.thermal_opex_expr
                + self.thermal_startup_expr
                + self.load_shortfall_penalty_expr
                + self.spin_shortfall_penalty_expr
                + rnw_import_expr
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
        self.c_link_uvw = modeling.add_c_link_uvw(
            model=self.model,
            u=self.status,
            v=self.startup,
            w=self.shutdown,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
        )
        self.c_link_pthermal = modeling.add_c_link_pthermal(
            model=self.model,
            pthermal=self.pthermal,
            p=self.vpower,
            u=self.status,
            timesteps=self.timesteps,
            thermal_units=self.inputs.thermal_units,
            thermal_min_capacity=self.inputs.thermal_min_capacity,
        )
        self.c_link_pu_lower = modeling.add_c_link_pu_lower(
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
        self.c_min_down = modeling.add_c_min_down(
            model=self.model,
            u=self.status,
            w=self.shutdown,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
            TD=self.inputs.TD,
        )
        self.c_min_up = modeling.add_c_min_up(
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
        self.c_ramp_down = modeling.add_c_ramp_down(
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
        self.c_ramp_up = modeling.add_c_ramp_up(
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
            self.c_ref_node = modeling.add_c_ref_node(
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
                step_k=step_k,
                edges=self.inputs.edges,
                susceptance=self.inputs.susceptance,
            )
        elif self.inputs.dc_opf == "kirchhoff":
            self.c_kirchhoff = modeling.add_c_kirchhoff(
                model=self.model,
                flow=self.flow,
                timesteps=self.timesteps,
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
            self.c_link_spin = modeling.add_c_link_spin(
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
                step_k=step_k,
                thermal_units=self.inputs.thermal_units,
                spin_requirement=self.inputs.spin_requirement,
            )
        else:
            self.c_link_ppbar = modeling.add_c_link_ppbar(
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
        self.model = gp.Model(self.inputs.model_id)
        self.add_variables(step_k=step_k)
        self.set_objfunc(step_k=step_k)
        self.add_constraints(step_k=step_k, init_conds=init_conds)

        return PowerSystemModel(self.model)

    def _update_variables(self, step_k: int) -> None:
        """
        Update the lower/upper bounds of time-dependent variables based on
        the current timestep, itereration, and capacity dataframes.

        This method dynamically adjusts the upper bounds (capacity limits)
        for various types of variables in the optimization problem,
        ensuring they reflect the available capacity at the given time step
        within the simulation horizon.

        Variables updated include:

        - Thermal units:
            - `pthermal`: Thermal power output
            - `vpower`: Thermal unit commitment status (on/off)
            - `vpowerbar`: Thermal unit start-up status
        - Hydropower:
            - `phydro`: Hydropower output (if hydro_timestep is hourly)
        - Renewables:
            - `psolar`: Solar power output
            - `pwind`: Wind power output
        - Imports:
            - `pimp`: Import power flow
        - Flow variables:
            - `flow`: Power flow on transmission lines (updates both lower and upper bounds)

        The upper bounds are retrieved from the corresponding capacity dataframes
        (e.g., `thermal_derated_capacity`, `hydro_capacity`, etc.) based on
        the current time step (`step_k`) and the simulation horizon.

        Args:
            step_k: The current time step within the simulation horizon.

        """

        def _update_var_ub(
            variables: gp.tupledict,
            capacity_df: pd.DataFrame,
        ) -> None:
            """Update the upper bounds of the variables based on the capacity dataframes"""
            for v in variables.values():
                unit_g, t = get_unit_hour_from_varnam(v.VarName)
                capacity_value = capacity_df.loc[t + (step_k - 1) * 24, unit_g]
                # Check if capacity_value is a Series or DataFrame and use .iloc[0] if necessary
                if isinstance(capacity_value, (pd.Series, pd.DataFrame)):
                    capacity_value = capacity_value.iloc[0]

                v.ub = capacity_value

        def _update_flow_bounds(
            flow_variables: gp.tupledict,
            capacity_df: pd.DataFrame,
        ) -> None:
            """Update the lower and upper bounds of the flow variables based on the capacity dataframes"""
            for flow_variable in flow_variables.values():
                edge, t = get_edge_hour_from_varname(flow_variable.VarName)
                line_capacity = capacity_df.loc[t + (step_k - 1) * 24, edge]
                # Update the lower and upper bounds, respectively
                flow_variable.lb = -line_capacity * self.inputs.line_capacity_factor
                flow_variable.ub = line_capacity * self.inputs.line_capacity_factor

        # Update variable bounds
        thermal_unit_vars = [self.pthermal, self.vpower, self.vpowerbar]
        for var_dict in thermal_unit_vars:
            _update_var_ub(var_dict, self.inputs.thermal_derated_capacity)

        # Renewables and import
        variable_capacity_pairs = [
            (self.psolar, self.inputs.solar_capacity),
            (self.pwind, self.inputs.wind_capacity),
            (self.pimp, self.inputs.import_capacity),
        ]
        for var_dict, capacity_df in variable_capacity_pairs:
            _update_var_ub(var_dict, capacity_df)

        # Hydropower variable with *daily* timestep does not have an upper bound
        if self.inputs.hydro_timestep == "hourly":
            _update_var_ub(self.phydro, self.inputs.hydro_capacity)

        # Flow variables require updating both lower and upper bounds
        _update_flow_bounds(self.flow, self.inputs.line_capacity)

    def _update_objfunc(self, step_k: int) -> None:
        """Update the objective function with time-dependent terms."""
        rnw_import_expr = self._build_rnw_import_objfunc_terms(step_k=step_k)
        self.model.setObjective(
            self.thermal_fixed_expr
            + self.thermal_opex_expr
            + self.thermal_startup_expr
            + self.load_shortfall_penalty_expr
            + self.spin_shortfall_penalty_expr
            + rnw_import_expr
        )

    def _update_constraints(self, step_k, init_conds: dict) -> None:
        """Constraints to be updated include:
        - c_link_uvw_init: initial_u is from the previous iteration
        - c_link_pu_upper: thermal_derated_capacity is a timeseries
        - c_min_down_init: initial_min_off is from the previous iteration
        - c_min_up_init: initial_min_on is from the previous iteration
        - c_ramp_down_init: initial vpower and u is from the previous iteration
        - c_ramp_up_init: initial vpower is from the previous iteration
        - c_angle_diff: susceptance is a timeseries
        - c_kirchhoff: Susceptance is a timeseries
        - c_flow_balance: Electricity demand is a timeseries
        - c_hydro_capacity: Hydropower capacity is a timeseries
        - c_reserve_req: Spinning reserve requirement is based on the electricity demand

        """
        self.model.remove(self.c_link_uvw_init)
        self.c_link_uvw_init = modeling.add_c_link_uvw_init(
            model=self.model,
            u=self.status,
            v=self.startup,
            w=self.shutdown,
            initial_u=init_conds["initial_u"],
            thermal_units=self.inputs.thermal_units,
        )

        self.model.remove(self.c_link_pu_upper)
        self.c_link_pu_upper = modeling.add_c_link_pu_upper(
            model=self.model,
            pbar=self.vpowerbar,
            u=self.status,
            timesteps=self.timesteps,
            step_k=step_k,
            thermal_units=self.inputs.thermal_units,
            thermal_min_capacity=self.inputs.thermal_min_capacity,
            thermal_derated_capacity=self.inputs.thermal_derated_capacity,
        )

        self.model.remove(self.c_min_down_init)
        self.c_min_down_init = modeling.add_c_min_down_init(
            model=self.model,
            u=self.status,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
            initial_min_off=init_conds["initial_min_off"],
        )

        self.model.remove(self.c_min_up_init)
        self.c_min_up_init = modeling.add_c_min_up_init(
            model=self.model,
            u=self.status,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
            initial_min_on=init_conds["initial_min_on"],
        )

        self.model.remove(self.c_ramp_down_init)
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

        self.model.remove(self.c_ramp_up_init)
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

        if self.inputs.dc_opf == "voltage_angle":
            self.model.remove(self.c_angle_diff)
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
            # There might not be a cycle in the network
            if self.c_kirchhoff is not None:
                self.model.remove(self.c_kirchhoff)
                self.c_kirchhoff = modeling.add_c_kirchhoff(
                    model=self.model,
                    flow=self.flow,
                    timesteps=self.timesteps,
                    step_k=step_k,
                    edges=self.inputs.edges,
                    cycle_map=self.inputs.cycle_map,
                    susceptance=self.inputs.susceptance,
                )

        self.model.remove(self.c_flow_balance)
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
            step_k=step_k,
            inputs=self.inputs,
            nodes=self.inputs.nodes,
            node_edge=self.inputs.node_edge,
            node_generator=self.inputs.node_generator,
            demand_nodes=self.inputs.demand_nodes,
            demand=self.inputs.demand,
            line_loss_factor=self.inputs.line_loss_factor,
        )

        if self.inputs.hydro_timestep == "daily":
            self.model.remove(self.c_hydro_capacity)
            self.c_hydro_capacity = modeling.add_c_hydro_capacity(
                model=self.model,
                phydro=self.phydro,
                timesteps=self.timesteps,
                step_k=step_k,
                sim_horizon=self.inputs.sim_horizon,
                hydro_units=self.inputs.hydro_units,
                hydro_capacity=self.inputs.hydro_capacity,
            )

        # Reserve requirement
        self.model.remove(self.c_reserve_req)
        if self.inputs.use_spin_var:
            self.c_reserve_req = modeling.add_c_reserve_req_1(
                model=self.model,
                spin=self.spin,
                spin_shortfall=self.spin_shortfall,
                timesteps=self.timesteps,
                step_k=step_k,
                thermal_units=self.inputs.thermal_units,
                spin_requirement=self.inputs.spin_requirement,
            )
        else:
            self.c_reserve_req = modeling.add_c_reserve_req_2(
                model=self.model,
                pbar=self.vpowerbar,
                u=self.status,
                spin_shortfall=self.spin_shortfall,
                timesteps=self.timesteps,
                step_k=step_k,
                thermal_units=self.inputs.thermal_units,
                thermal_min_capacity=self.inputs.thermal_min_capacity,
                demand_nodes=self.inputs.demand_nodes,
                demand=self.inputs.demand,
                spin_requirement=self.inputs.spin_requirement,
            )

    def update(
        self,
        step_k: int,
        init_conds: dict[str, dict],
    ) -> gp.Model:
        """Update the model instead of creating a new one
        so we can perform warm start
        """
        self._update_variables(step_k=step_k)
        self._update_objfunc(step_k=step_k)
        self._update_constraints(step_k=step_k, init_conds=init_conds)
        self.model.update()

        return PowerSystemModel(self.model)

    def print_added_constraints(self):
        added_constrs = []
        not_added_constrs = []

        constraints_list = [
            "c_link_uvw_init",
            "c_link_uvw",
            "c_link_pthermal",
            "c_link_pu_lower",
            "c_link_pu_upper",
            "c_min_down_init",
            "c_min_up_init",
            "c_min_down",
            "c_min_up",
            "c_peak_down_bound",
            "c_peak_up_bound",
            "c_ramp_down_init",
            "c_ramp_up_init",
            "c_ramp_down",
            "c_ramp_up",
            "c_ref_node",
            "c_angle_diff",
            "c_kirchhoff",
            "c_flow_balance",
            "c_hydro_capacity",
            "c_link_spin",
            "c_link_ppbar",
            "c_reserve_req",
        ]

        for attr_name in constraints_list:
            if getattr(self, attr_name) is not None:
                added_constrs.append(attr_name)
            else:
                not_added_constrs.append(attr_name)

        log_message = "\nAdded constraints:\n"
        log_message += "\n".join(added_constrs)
        log_message += "\n\nNot added constraints:\n"
        log_message += "\n".join(not_added_constrs)

        logger.warning(log_message)
