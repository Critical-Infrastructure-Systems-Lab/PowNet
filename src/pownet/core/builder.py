""" builder.py: ModelBuilder class builds and updates the unit commitment problem.
"""

from .input import SystemInput

from gurobipy import GRB
import gurobipy as gp
import pandas as pd

import pownet.modeling as modeling
from pownet.data_utils import get_unit_hour_from_varnam, get_edge_hour_from_varname


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
        self.model: gp.Model = gp.Model(self.inputs.model_id)

        # Variables
        # Thermal units
        self.pthermal = gp.tupledict()
        self.status = gp.tupledict()
        self.startup = gp.tupledict()
        self.shutdown = gp.tupledict()
        self.vpower = gp.tupledict()
        self.vpowerbar = gp.tupledict()
        self.spin = gp.tupledict()
        self.pthermal_curtail = gp.tupledict()  # for must-take units

        # Energy storage
        self.pcharge = gp.tupledict()
        self.pdischarge = gp.tupledict()
        self.pdischarge_shortfall = gp.tupledict()

        self.charge_state = gp.tupledict()  # State of charge
        self.ucharge = gp.tupledict()  # Charging indicator
        self.udischarge = gp.tupledict()  # Discharging indicator

        # Renewable energy and import sources
        self.phydro = gp.tupledict()
        self.phydro_curtail = gp.tupledict()
        self.uhydro = gp.tupledict()

        self.psolar = gp.tupledict()
        self.psolar_curtail = gp.tupledict()
        self.usolar = gp.tupledict()

        self.pwind = gp.tupledict()
        self.pwind_curtail = gp.tupledict()
        self.uwind = gp.tupledict()

        self.pimp = gp.tupledict()  # import
        self.pimp_curtail = gp.tupledict()
        self.uimp = gp.tupledict()

        # Node variables
        self.pos_pmismatch = gp.tupledict()
        self.neg_pmismatch = gp.tupledict()

        # Energy-flow variables
        self.flow = gp.tupledict()
        self.theta = gp.tupledict()

        # System-wide variables
        self.spin_shortfall = gp.tupledict()

        # Time-independent terms in the objective function
        self.thermal_fixed_expr = gp.LinExpr()
        self.thermal_opex_expr = gp.LinExpr()
        self.thermal_startup_expr = gp.LinExpr()
        self.thermal_curtail_expr = gp.LinExpr()

        self.load_shortfall_penalty_expr = gp.LinExpr()
        self.spin_shortfall_penalty_expr = gp.LinExpr()
        self.pdischarge_shortfall_penalty_expr = gp.LinExpr()

        # Thermal unit constraints
        self.c_link_uvw_init = gp.tupledict()
        self.c_link_uvw = gp.tupledict()
        self.c_link_pthermal = gp.tupledict()
        self.c_link_pu_lower = gp.tupledict()
        self.c_link_pu_upper = gp.tupledict()
        self.c_min_down_init = gp.tupledict()
        self.c_min_up_init = gp.tupledict()
        self.c_min_down = gp.tupledict()
        self.c_min_up = gp.tupledict()
        self.c_peak_down_bound = gp.tupledict()
        self.c_peak_up_bound = gp.tupledict()
        self.c_ramp_down_init = gp.tupledict()
        self.c_ramp_up_init = gp.tupledict()
        self.c_ramp_down = gp.tupledict()
        self.c_ramp_up = gp.tupledict()
        self.c_link_spin = gp.tupledict()
        self.c_link_ppbar = gp.tupledict()
        self.c_thermal_curtail = gp.tupledict()

        # System-wide constraints
        self.c_ref_node = gp.tupledict()
        self.c_angle_diff = gp.tupledict()
        self.c_kirchhoff = gp.tupledict()
        self.c_flow_balance = gp.tupledict()
        self.c_reserve_req = gp.tupledict()

        self.c_hydro_curtail_ess = gp.tupledict()
        self.c_daily_hydro_curtail_ess = gp.tupledict()
        self.c_solar_curtail_ess = gp.tupledict()
        self.c_wind_curtail_ess = gp.tupledict()
        self.c_import_curtail_ess = gp.tupledict()

        # These constraints act as the upper bound
        # and provides indicators if the unit is online
        self.c_link_hydro_pu = gp.tupledict()
        self.c_link_daily_hydro_pu = gp.tupledict()
        self.c_link_solar_pu = gp.tupledict()
        self.c_link_wind_pu = gp.tupledict()
        self.c_link_import_pu = gp.tupledict()

        self.c_hydro_limit_daily = gp.tupledict()

        # Energy storage constraints
        self.c_link_ess_charge = gp.tupledict()
        self.c_link_discharge = gp.tupledict()
        self.c_link_ess_state = gp.tupledict()
        self.c_unit_ess_balance_init = gp.tupledict()
        self.c_unit_ess_balance = gp.tupledict()

    def add_variables(self, step_k: int) -> None:
        """Add variables to the model.

        Thermal-unit variables:
        -----------------
        - `pthermal`: Power output by a thermal unit (also called dispatch). Unit: MW.
        - `vpower`: Power output *ABOVE* the minimum capacity of a thermal unit. Unit: MW.
        - `vpowerbar`: Maximum power output *ABOVE* the minimum capacity of a thermal unit. Unit: MW.
        - `status`: Indicator of online status. On = 1 and off = 0. Unitless.
        - `startup`: Indicator if a unit is shutting down. Unitless.
        - `shutdown`: Indicator if a unit is starting up. Unitless.
        - `spin` (optional): Spinning reserve. Unit: MW.
        - `pthermal_curtail`: Curtailed power output by a thermal unit. Unit: MW.

        Energy-storage variables:
        -----------------
        - `pcharge`: Power charging an energy storage system. Unit: MW.
        - `pdischarge`: Power discharging an energy storage system. Unit: MW.
        - `pdischarge_shortfall`: Shortfall in discharging power. Unit: MW.
        - `charge_state`: State of charge of an energy storage system. Unit: MWh.
        - `ucharge`: Indicator that an ESS is charging. Unitless.
        - `udischarge`: Indicator that an ESS is discharging. Unitless.

        Renewable energy and import variables:
        -----------------
        - `phydro`: Hydropower output. Unit: MW.
        - `psolar`: Solar power output. Unit: MW.
        - `pwind`: Wind power output. Unit: MW.
        - `pimp`: Import power output. Unit: MW.
        - `phydro_curtail`: Curtailed hydropower output. Unit: MW.
        - `psolar_curtail`: Curtailed solar power output. Unit: MW.
        - `pwind_curtail`: Curtailed wind power output. Unit: MW.
        - `pimp_curtail`: Curtailed import power output. Unit: MW.

        Node variables:
        -----------------
        - `pos_pmismatch`: Positive power mismatch. Unit: MW.
        - `neg_pmismatch`: Negative power mismatch. Unit: MW.
        - `theta`: Voltage angle. Unit: Radians.

        Flow variables:
        -----------------
        - `flow`: Power flow on transmission lines. Unit: MW/hr.

        System variables:
        -----------------
        - `spin_shortfall`: Spinning reserve shortfall. Unit: MW.

        Args:
            step_k: The current step of the simulation.

        Returns:
            None

        """
        ################################
        # Variables with fixed upper bounds
        ################################
        var_with_u_tuples = [
            ("phydro", self.inputs.hydro_units, self.inputs.hydro_contracted_capacity),
            (
                "phydro_curtail",
                self.inputs.hydro_units,
                self.inputs.hydro_max_capacity,
            ),
            ("psolar", self.inputs.solar_units, self.inputs.solar_contracted_capacity),
            (
                "psolar_curtail",
                self.inputs.solar_units,
                self.inputs.solar_max_capacity,
            ),
            ("pwind", self.inputs.wind_units, self.inputs.wind_contracted_capacity),
            (
                "pwind_curtail",
                self.inputs.wind_units,
                self.inputs.wind_max_capacity,
            ),
            ("pimp", self.inputs.import_units, self.inputs.import_contracted_capacity),
            (
                "pimp_curtail",
                self.inputs.import_units,
                self.inputs.import_max_capacity,
            ),
            ("pcharge", self.inputs.storage_units, self.inputs.ess_max_charge),
            ("pdischarge", self.inputs.storage_units, self.inputs.ess_max_discharge),
            (
                "pdischarge_shortfall",
                self.inputs.storage_units,
                self.inputs.ess_max_discharge,
            ),
        ]

        for varname, units, capacity_dict in var_with_u_tuples:
            setattr(
                self,
                f"{varname}",
                self.model.addVars(
                    units,
                    self.timesteps,
                    lb=0,
                    ub={
                        (unit, t): capacity_dict[unit]
                        for t in self.timesteps
                        for unit in units
                    },
                    name=varname,
                ),
            )

        ################################
        # Variables with variable upper bounds
        ################################

        var_with_variable_ub_tuples = [
            ("pthermal", "thermal_units", self.inputs.thermal_derated_capacity),
            ("vpower", "thermal_units", self.inputs.thermal_derated_capacity),
            ["vpowerbar", "thermal_units", self.inputs.thermal_derated_capacity],
            (
                "pthermal_curtail",
                "thermal_must_take_units",
                self.inputs.thermal_derated_capacity,
            ),
            ("charge_state", "storage_units", self.inputs.ess_derated_capacity),
        ]

        for varname, unit_type, capacity_df in var_with_variable_ub_tuples:
            # Update the self attribute directly
            setattr(
                self,
                varname,
                modeling.add_var_with_variable_ub(
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
        # Binary variables
        ################################
        var_binary_tuples = [
            ("status", "thermal_units"),
            ("startup", "thermal_units"),
            ("shutdown", "thermal_units"),
            ("ucharge", "storage_units"),
            ("udischarge", "storage_units"),
            ("uhydro", "hydro_units"),
            ("usolar", "solar_units"),
            ("uwind", "wind_units"),
            ("uimp", "import_units"),
        ]
        for varname, unit_type in var_binary_tuples:
            setattr(
                self,
                varname,
                self.model.addVars(
                    getattr(self.inputs, unit_type),
                    self.timesteps,
                    vtype=GRB.BINARY,
                    name=varname,
                ),
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

    def _build_rnw_import_storage_objfunc_terms(self, step_k: int) -> gp.LinExpr:
        """Build the objective function for renewable energy and import sources."""
        variable_unit_contracts_tuple = [
            (self.phydro, self.inputs.hydro_units, self.inputs.nondispatch_contracts),
            # hourly hydro
            (
                self.phydro_curtail,
                self.inputs.hydro_must_take_units,
                self.inputs.nondispatch_contracts,
            ),
            # Daily hydro
            (
                self.phydro_curtail,
                self.inputs.daily_hydro_must_take_units,
                self.inputs.nondispatch_contracts,
            ),
            (self.psolar, self.inputs.solar_units, self.inputs.nondispatch_contracts),
            (
                self.psolar_curtail,
                self.inputs.solar_must_take_units,
                self.inputs.nondispatch_contracts,
            ),
            (self.pwind, self.inputs.wind_units, self.inputs.nondispatch_contracts),
            (
                self.pwind_curtail,
                self.inputs.wind_must_take_units,
                self.inputs.nondispatch_contracts,
            ),
            (self.pimp, self.inputs.import_units, self.inputs.nondispatch_contracts),
            (
                self.pimp_curtail,
                self.inputs.import_must_take_units,
                self.inputs.nondispatch_contracts,
            ),
            (self.pdischarge, self.inputs.storage_units, self.inputs.ess_contracts),
        ]

        rnw_import_storage_expr = gp.LinExpr()
        for var_dict, units, contracts in variable_unit_contracts_tuple:
            cost_coeffs = modeling.get_marginal_cost_coeff(
                step_k=step_k,
                timesteps=self.timesteps,
                units=units,
                nondispatch_contracts=contracts,
                contract_costs=self.inputs.contract_costs,
            )
            rnw_import_storage_expr.add(var_dict.prod(cost_coeffs))
        return rnw_import_storage_expr

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

        thermal_opex_coeffs = modeling.get_thermal_opex_coeff(
            step_k=step_k,
            timesteps=self.timesteps,
            thermal_units=self.inputs.thermal_units,
            thermal_opex=self.inputs.thermal_opex,
            fuel_contracts=self.inputs.fuel_contracts,
            contract_costs=self.inputs.contract_costs,
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

        # Curtailment cost is the same as the OPEX cost
        self.thermal_curtail_expr = self.pthermal_curtail.prod(thermal_opex_coeffs)

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

        # Penalize discharge shortfall
        self.pdischarge_shortfall_penalty_expr = (
            self.inputs.ess_discharge_shortfall_penalty_factor
            * gp.quicksum(self.pdischarge_shortfall)
        )

        ################################
        # Renewable energy, import sources, and energy storage
        ################################
        rnw_import_expr = self._build_rnw_import_storage_objfunc_terms(step_k=step_k)

        ################################
        # Set the objective function
        ################################

        self.model.setObjective(
            (
                self.thermal_fixed_expr
                + self.thermal_opex_expr
                + self.thermal_startup_expr
                + self.thermal_curtail_expr
                + self.load_shortfall_penalty_expr
                + self.spin_shortfall_penalty_expr
                + self.pdischarge_shortfall_penalty_expr
                + rnw_import_expr
            ),
            sense=GRB.MINIMIZE,
        )

        self.model.update()

    def _add_hourly_hydropower_constraints(self, step_k: int) -> None:
        self.c_link_hydro_pu = modeling.add_c_link_unit_pu(
            model=self.model,
            pdispatch=self.phydro,
            u=self.uhydro,
            unit_type="hydro",
            timesteps=self.timesteps,
            step_k=step_k,
            units=self.inputs.hydro_unit_node.keys(),
            capacity_df=self.inputs.hydro_capacity,
        )
        self.c_hydro_curtail_ess = modeling.add_c_unit_curtail_ess(
            model=self.model,
            pdispatch=self.phydro,
            pcurtail=self.phydro_curtail,
            pcharge=self.pcharge,
            unit_type="hydro",
            timesteps=self.timesteps,
            step_k=step_k,
            units=self.inputs.hydro_unit_node.keys(),
            capacity_df=self.inputs.hydro_capacity,
            ess_attached=self.inputs.ess_hydro_units,
        )

    def _add_daily_hydropower_constraints(self, step_k: int) -> None:
        # (1) Define the daily upper bound.
        self.c_hydro_limit_daily = modeling.add_c_hydro_limit_daily(
            model=self.model,
            phydro=self.phydro,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            hydro_units=self.inputs.daily_hydro_unit_node.keys(),
            hydro_capacity=self.inputs.daily_hydro_capacity,
        )
        # (2) The curtailment is enforced for the day and not the hour.
        self.c_daily_hydro_curtail_ess = modeling.add_c_unit_curtail_ess_daily(
            model=self.model,
            pdispatch=self.phydro,
            pcurtail=self.phydro_curtail,
            pcharge=self.pcharge,
            unit_type="hydro",
            sim_horizon=self.inputs.sim_horizon,
            step_k=step_k,
            units=self.inputs.daily_hydro_unit_node.keys(),
            capacity_df=self.inputs.daily_hydro_capacity,
            ess_attached=self.inputs.ess_daily_hydro_units,
        )

    def _add_hydropower_constraints(self, step_k: int) -> None:

        self._add_hourly_hydropower_constraints(step_k=step_k)

        self._add_daily_hydropower_constraints(step_k=step_k)
        # With daily formulation, each hour is still limited by turbine capacity
        # Not updated every step_k
        self.c_link_daily_hydro_pu = modeling.add_c_link_unit_pu_constant(
            model=self.model,
            pdispatch=self.phydro,
            u=self.uhydro,
            unit_type="hydro",
            timesteps=self.timesteps,
            units=self.inputs.daily_hydro_unit_node.keys(),
            contracted_capacity=self.inputs.hydro_contracted_capacity,
        )

    def _update_hydropower_constraints(self, step_k: int) -> None:
        # Hourly constraints
        self.model.remove(self.c_link_hydro_pu)
        self.model.remove(self.c_hydro_curtail_ess)
        self._add_hourly_hydropower_constraints(step_k=step_k)

        self.model.remove(self.c_hydro_limit_daily)
        self.model.remove(self.c_daily_hydro_curtail_ess)
        self._add_daily_hydropower_constraints(step_k=step_k)

    def _add_unit_link_pu(self, step_k: int) -> None:
        # Define parameters
        unit_params = {
            "solar": {
                "p": self.psolar,
                "u": self.usolar,
                "units": self.inputs.solar_units,
                "capacity_df": self.inputs.solar_capacity,
            },
            "wind": {
                "p": self.pwind,
                "u": self.uwind,
                "units": self.inputs.wind_units,
                "capacity_df": self.inputs.wind_capacity,
            },
            "import": {
                "p": self.pimp,
                "u": self.uimp,
                "units": self.inputs.import_units,
                "capacity_df": self.inputs.import_capacity,
            },
        }
        for unit_type, params in unit_params.items():
            setattr(
                self,
                f"c_link_{unit_type}_pu",
                modeling.add_c_link_unit_pu(
                    model=self.model,
                    pdispatch=params["p"],
                    u=params["u"],
                    unit_type=unit_type,
                    timesteps=self.timesteps,
                    step_k=step_k,
                    units=params["units"],
                    capacity_df=params["capacity_df"],
                ),
            )

    def _add_curtail_ess_constraints(self, step_k: int) -> None:
        # Not implementing ESS for thermal units
        unit_types_with_ess = {
            "solar": {
                "pdispatch": self.psolar,
                "pcurtail": self.psolar_curtail,
                "pcharge": self.pcharge,
                "units": self.inputs.solar_units,
                "capacity_df": self.inputs.solar_capacity,
                "ess_attached": self.inputs.ess_solar_units,
            },
            "wind": {
                "pdispatch": self.pwind,
                "pcurtail": self.pwind_curtail,
                "pcharge": self.pcharge,
                "units": self.inputs.wind_units,
                "capacity_df": self.inputs.wind_capacity,
                "ess_attached": self.inputs.ess_wind_units,
            },
            "import": {
                "pdispatch": self.pimp,
                "pcurtail": self.pimp_curtail,
                "pcharge": self.pcharge,
                "units": self.inputs.import_units,
                "capacity_df": self.inputs.import_capacity,
                "ess_attached": {},  # No ESS attached to import sources
            },
        }

        for unit_type, params in unit_types_with_ess.items():
            setattr(
                self,
                f"c_{unit_type}_curtail_ess",
                modeling.add_c_unit_curtail_ess(
                    model=self.model,
                    pdispatch=params["pdispatch"],
                    pcurtail=params["pcurtail"],
                    pcharge=params["pcharge"],
                    unit_type=unit_type,
                    timesteps=self.timesteps,
                    step_k=step_k,
                    units=params["units"],
                    capacity_df=params["capacity_df"],
                    ess_attached=params["ess_attached"],
                ),
            )

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
        self.c_thermal_curtail = modeling.add_c_thermal_curtail(
            model=self.model,
            pthermal=self.pthermal,
            pthermal_curtail=self.pthermal_curtail,
            pcharge=self.pcharge,
            timesteps=self.timesteps,
            step_k=step_k,
            thermal_derated_capacity=self.inputs.thermal_derated_capacity,
            thermal_must_take_units=self.inputs.thermal_must_take_units,
            ess_attached=self.inputs.ess_thermal_units,
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
        # Energy-storage constraints
        ################################

        self.c_link_ess_charge = modeling.add_c_link_ess_charge(
            model=self.model,
            pcharge=self.pcharge,
            ucharge=self.ucharge,
            timesteps=self.timesteps,
            units=self.inputs.storage_units,
            max_charge=self.inputs.ess_max_charge,
        )

        self.c_link_ess_dischage = modeling.add_c_link_ess_discharge(
            model=self.model,
            pdischarge=self.pdischarge,
            udischarge=self.udischarge,
            timesteps=self.timesteps,
            units=self.inputs.storage_units,
            max_discharge=self.inputs.ess_max_discharge,
        )

        self.c_link_ess_state = modeling.add_c_link_ess_state(
            model=self.model,
            ucharge=self.ucharge,
            udischarge=self.udischarge,
            timesteps=self.timesteps,
            units=self.inputs.storage_units,
        )

        self.c_unit_ess_balance_init = modeling.add_c_unit_ess_balance_init(
            model=self.model,
            pcharge=self.pcharge,
            pdischarge=self.pdischarge,
            charge_state=self.charge_state,
            units=self.inputs.storage_units,
            charge_state_init=init_conds["initial_charge_state"],
            charge_efficiency=self.inputs.ess_charge_efficiency,
            discharge_efficiency=self.inputs.ess_discharge_efficiency,
            self_discharge_rate=self.inputs.ess_self_discharge_rate,
        )

        self.c_unit_ess_balance = modeling.add_c_unit_ess_balance(
            model=self.model,
            pcharge=self.pcharge,
            pdischarge=self.pdischarge,
            charge_state=self.charge_state,
            units=self.inputs.storage_units,
            sim_horizon=self.inputs.sim_horizon,
            charge_efficiency=self.inputs.ess_charge_efficiency,
            discharge_efficiency=self.inputs.ess_discharge_efficiency,
            self_discharge_rate=self.inputs.ess_self_discharge_rate,
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
            pcharge=self.pcharge,
            pdis=self.pdischarge,
            pos_pmismatch=self.pos_pmismatch,
            neg_pmismatch=self.neg_pmismatch,
            flow=self.flow,
            timesteps=self.timesteps,
            step_k=step_k,
            thermal_units=self.inputs.thermal_units,
            hydro_units=self.inputs.hydro_units,
            solar_units=self.inputs.solar_units,
            wind_units=self.inputs.wind_units,
            import_units=self.inputs.import_units,
            nodes=self.inputs.nodes,
            node_edge=self.inputs.node_edge,
            node_generator=self.inputs.node_generator,
            charge_storage=self.inputs.ess_substation_units,
            discharge_storage=self.inputs.ess_attach_unit,
            demand_nodes=self.inputs.demand_nodes,
            demand=self.inputs.demand,
            line_loss_factor=self.inputs.line_loss_factor,
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

        ################################
        # Non-dispatchables
        ################################

        # Energy storage
        self._add_curtail_ess_constraints(step_k)

        # Solar, wind, and import
        self._add_unit_link_pu(step_k)

        # Hydropower
        self._add_hydropower_constraints(step_k)

        # Update the model just in case we want to check model structure
        self.model.update()

    def build(
        self,
        step_k: int,
        init_conds: dict[str, dict],
    ) -> modeling.PowerSystemModel:
        """Build the model for the unit commitment problem."""
        self.add_variables(step_k=step_k)
        self.set_objfunc(step_k=step_k)
        self.add_constraints(step_k=step_k, init_conds=init_conds)
        return modeling.PowerSystemModel(self.model)

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
            - `pthermal_curtail`: Curtailed thermal power output
        - Energy storage:
            - `charge_state`: State of charge
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
        thermal_unit_vars = [
            self.pthermal,
            self.vpower,
            self.vpowerbar,
            self.pthermal_curtail,
        ]
        for var_dict in thermal_unit_vars:
            _update_var_ub(var_dict, self.inputs.thermal_derated_capacity)

        # Energy storage, renewables and import
        variable_capacity_pairs = [
            (self.charge_state, self.inputs.ess_derated_capacity),
        ]
        for var_dict, capacity_df in variable_capacity_pairs:
            _update_var_ub(var_dict, capacity_df)

        # Flow variables require updating both lower and upper bounds
        _update_flow_bounds(self.flow, self.inputs.line_capacity)

    def _update_objfunc(self, step_k: int) -> None:
        """Update the objective function with time-dependent terms."""
        rnw_import_storage_expr = self._build_rnw_import_storage_objfunc_terms(
            step_k=step_k
        )
        self.model.setObjective(
            self.thermal_fixed_expr
            + self.thermal_opex_expr
            + self.thermal_startup_expr
            + self.thermal_curtail_expr
            + self.load_shortfall_penalty_expr
            + self.spin_shortfall_penalty_expr
            + self.pdischarge_shortfall_penalty_expr
            + rnw_import_storage_expr
        )

    def _update_constraints(self, step_k, init_conds: dict) -> None:
        """Constraints to be updated include:

        *Thermal units*
        - c_link_uvw_init: initial_u is from the previous iteration
        - c_link_pu_upper: thermal_derated_capacity is a timeseries
        - c_min_down_init: initial_min_off is from the previous iteration
        - c_min_up_init: initial_min_on is from the previous iteration
        - c_ramp_down_init: initial vpower and u is from the previous iteration
        - c_ramp_up_init: initial vpower is from the previous iteration

        *System-wide*
        - c_angle_diff: susceptance is a timeseries
        - c_kirchhoff: Susceptance is a timeseries
        - c_flow_balance: Electricity demand is a timeseries
        - c_reserve_req: Spinning reserve requirement is based on the electricity demand

        *Upper bound of renewable units*
        - c_link_hydro_pu: Hydropower capacity is a timeseries
        - c_link_solar_pu: Solar capacity is a timeseries
        - c_link_wind_pu: Wind capacity is a timeseries
        - c_link_import_pu: Import capacity is a timeseries

        - c_hydro_limit_daily: Hydropower capacity is a timeseries

        *Curtailment*
        - c_hydro_curtail_ess: Hydropower capacity is a timeseries
        - c_daily_hydro_curtail_ess: Daily hydropower capacity is a timeseries
        - c_solar_curtail_ess: Solar capacity is a timeseries
        - c_wind_curtail_ess: Wind capacity is a timeseries
        - c_import_curtail_ess: Import capacity is a timeseries

        *Energy storage units*
        - c_unit_ess_balance_init: initial condition changes

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

        self.model.remove(self.c_thermal_curtail)
        self.c_thermal_curtail = modeling.add_c_thermal_curtail(
            model=self.model,
            pthermal=self.pthermal,
            pthermal_curtail=self.pthermal_curtail,
            pcharge=self.pcharge,
            timesteps=self.timesteps,
            step_k=step_k,
            thermal_derated_capacity=self.inputs.thermal_derated_capacity,
            thermal_must_take_units=self.inputs.thermal_must_take_units,
            ess_attached=self.inputs.ess_thermal_units,
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
            pcharge=self.pcharge,
            pdis=self.pdischarge,
            pos_pmismatch=self.pos_pmismatch,
            neg_pmismatch=self.neg_pmismatch,
            flow=self.flow,
            timesteps=self.timesteps,
            step_k=step_k,
            thermal_units=self.inputs.thermal_units,
            hydro_units=self.inputs.hydro_units,
            solar_units=self.inputs.solar_units,
            wind_units=self.inputs.wind_units,
            import_units=self.inputs.import_units,
            nodes=self.inputs.nodes,
            node_edge=self.inputs.node_edge,
            node_generator=self.inputs.node_generator,
            charge_storage=self.inputs.ess_substation_units,
            discharge_storage=self.inputs.ess_attach_unit,
            demand_nodes=self.inputs.demand_nodes,
            demand=self.inputs.demand,
            line_loss_factor=self.inputs.line_loss_factor,
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

        # Renewables curtailment
        self.model.remove(self.c_solar_curtail_ess)
        self.model.remove(self.c_wind_curtail_ess)
        self.model.remove(self.c_import_curtail_ess)
        self._add_curtail_ess_constraints(step_k)

        # Solar, wind, import link p and u.
        self.model.remove(self.c_link_solar_pu)
        self.model.remove(self.c_link_wind_pu)
        self.model.remove(self.c_link_import_pu)
        self._add_unit_link_pu(step_k)

        # Hydropower
        self._update_hydropower_constraints(step_k)

        # Flow balance
        self.model.remove(self.c_unit_ess_balance_init)
        self.c_unit_ess_balance_init = modeling.add_c_unit_ess_balance_init(
            model=self.model,
            pcharge=self.pcharge,
            pdischarge=self.pdischarge,
            charge_state=self.charge_state,
            units=self.inputs.storage_units,
            charge_state_init=init_conds["initial_charge_state"],
            charge_efficiency=self.inputs.ess_charge_efficiency,
            discharge_efficiency=self.inputs.ess_discharge_efficiency,
            self_discharge_rate=self.inputs.ess_self_discharge_rate,
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
        return modeling.PowerSystemModel(self.model)
