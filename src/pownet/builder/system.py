"""system.py: Power system builder."""

import math

import gurobipy as gp

from .basebuilder import ComponentBuilder
from ..input import SystemInput
from ..optim_model import (
    get_thermal_opex_coeff,
    update_flow_vars,
    add_var_with_variable_ub,
    update_var_with_variable_ub,
    get_marginal_cost_coeff,
)
from ..optim_model.constraints import (
    system_constr,
)


class SystemBuilder(ComponentBuilder):
    """Builder class for the power system, dealing with system-wide variables and constraints.

    Variables
    ===========================

    Node-specific variables:
    ---------------------------
    - `pos_pmismatch`: Positive power mismatch at a node. Unit: MW.
    - `neg_pmismatch`: Negative power mismatch at a node. Unit: MW.
    - `theta`: Voltage angle at a node. Unit: Radians.

    Flow variables:
    ---------------------------
    - `flow`: Power flow on transmission lines. Unit: MW/hr.

    System variables:
    ---------------------------
    - `spin_shortfall`: Spinning reserve shortfall (system-wide). Unit: MW.

    Fixed objective terms
    ===========================
    - load shortfall penalty
    - load curtailment penalty
    - spinning shortfall reserve penalty

    Variable objective terms
    ===========================
    - Must-take curtailment penalty

    Constraints
    ===========================
    - Spinning reserve constraints
    - Power flow balance constraints
    - DC-OPF constraints
    - Definition of curtailment variables

    """

    def __init__(self, model: gp.Model, inputs: SystemInput):
        super().__init__(model, inputs)

        # --- Variables ---
        self.pos_pmismatch = gp.tupledict()
        self.neg_pmismatch = gp.tupledict()

        self.spin_shortfall = gp.tupledict()

        self.flow_fwd = gp.tupledict()
        self.flow_bwd = gp.tupledict()
        self.theta = gp.tupledict()

        # Curtailment variables
        self.pthermal_curtail = gp.tupledict()
        self.phydro_curtail = gp.tupledict()
        self.psolar_curtail = gp.tupledict()
        self.pwind_curtail = gp.tupledict()
        self.pimp_curtail = gp.tupledict()

        # --- Objective terms ---
        # Fixed objective terms
        self.load_shortfall_penalty_expr = gp.LinExpr()
        self.load_curtail_penalty_expr = gp.LinExpr()
        self.spin_shortfall_penalty_expr = gp.LinExpr()

        # Variable objective terms
        self.must_take_curtail_penalty_expr = gp.LinExpr()

        # --- Constraints ---
        # Spinning reserve constraints
        self.c_link_spin = gp.tupledict()
        self.c_link_ppbar = gp.tupledict()
        self.c_reserve_req = gp.tupledict()

        # Power flow constraints
        self.c_flow_balance = gp.tupledict()

        # DC-OPF constraints
        self.c_ref_node = gp.tupledict()
        self.c_angle_diff = gp.tupledict()
        self.c_kirchhoff = gp.tupledict()

        # Curtailment constraints
        self.c_thermal_curtail = gp.tupledict()
        self.c_hydro_curtail_ess = gp.tupledict()
        self.c_solar_curtail_ess = gp.tupledict()
        self.c_wind_curtail_ess = gp.tupledict()
        self.c_import_curtail_ess = gp.tupledict()

        self.c_daily_hydro_curtail_ess = gp.tupledict()
        self.c_weekly_hydro_curtail_ess = gp.tupledict()

    def add_variables(self, step_k: int) -> None:

        ##############################################
        # Variables with fixed upper bounds
        ##############################################

        # --- Power Mismatch (pmismatch) ---
        self.pos_pmismatch = self.model.addVars(
            self.inputs.nodes,
            self.timesteps,
            lb=0,
            vtype=gp.GRB.CONTINUOUS,
            name="pos_pmismatch",
        )

        self.neg_pmismatch = self.model.addVars(
            self.inputs.nodes,
            self.timesteps,
            lb=0,
            vtype=gp.GRB.CONTINUOUS,
            name="neg_pmismatch",
        )

        # --- System-wide spinning reserve shortfall
        self.spin_shortfall = self.model.addVars(
            self.timesteps,
            name="spin_shortfall",
        )

        # --- Curtailment variables of non-dispatchables ---

        var_with_fixed_ub_tuples = [
            (
                "phydro_curtail",
                self.inputs.hydro_units,
                self.inputs.hydro_max_capacity,
            ),
            (
                "psolar_curtail",
                self.inputs.solar_units,
                self.inputs.solar_max_capacity,
            ),
            (
                "pwind_curtail",
                self.inputs.wind_units,
                self.inputs.wind_max_capacity,
            ),
            (
                "pimp_curtail",
                self.inputs.import_units,
                self.inputs.import_max_capacity,
            ),
        ]
        for varname, unit_type, ub in var_with_fixed_ub_tuples:
            setattr(
                self,
                varname,
                self.model.addVars(
                    unit_type,
                    self.timesteps,
                    lb=0,
                    ub=ub,
                    vtype=gp.GRB.CONTINUOUS,
                    name=varname,
                ),
            )

        # --- Voltage Angle (theta) ---
        # Represents the voltage angle at each bus (node) for each time period.
        # Unit: Radians.
        # The voltage angle difference between two buses drives power flow in DC-OPF.
        # One bus is typically chosen as the reference bus with its angle fixed (e.g., to 0),
        # and other angles are relative to this reference.

        # NOTE on Bounds:
        # Theoretical bounds are [-pi, pi]. In DC-OPF, angle differences are assumed to be small.
        # Some studies use tighter bounds like [-pi/2, pi/2] or even stricter ones to
        # reflect this assumption or to aid solver performance. The [-pi, pi] range is a
        # valid, albeit potentially loose, starting point if not otherwise constrained.

        # Implement only when the voltage angle formulation is chosen.
        if self.inputs.dc_opf == "voltage_angle":
            self.theta = self.model.addVars(
                self.inputs.nodes,
                self.timesteps,
                lb=-math.pi,
                ub=math.pi,
                vtype=gp.GRB.CONTINUOUS,
                name="theta",
            )

        #############################################
        # Variables with time-dependent upper bounds
        #############################################
        # --- Power Flow (flow) ---
        # Represents the active power flow on each transmission line (edge) for each time period.
        # Unit: MW (Megawatts).
        # The bounds are determined by the line's thermal capacity, potentially adjusted by a capacity factor.

        hours_per_step = 24  # for rolling horizon or len(timesteps) for block horizon
        self.flow_fwd = self.model.addVars(
            self.inputs.edges,
            self.timesteps,
            lb=0,
            ub={
                (source, sink, t): self.inputs.line_capacity_factor
                * self.inputs.line_capacity.loc[
                    t + (step_k - 1) * hours_per_step, (source, sink)
                ]
                for t in self.timesteps
                for source, sink in self.inputs.edges
            },
            vtype=gp.GRB.CONTINUOUS,
            name="flow_fwd",
        )

        # The backward flow shares the same indexing, so
        # be careful when formulating the power flow balance constraints.
        self.flow_bwd = self.model.addVars(
            self.inputs.edges,
            self.timesteps,
            lb=0,
            ub={
                (source, sink, t): self.inputs.line_capacity_factor
                * self.inputs.line_capacity.loc[
                    t + (step_k - 1) * hours_per_step, (source, sink)
                ]
                for t in self.timesteps
                for source, sink in self.inputs.edges
            },
            vtype=gp.GRB.CONTINUOUS,
            name="flow_bwd",
        )

        # Curtailment variables
        var_with_variable_ub_tuples = [
            (
                "pthermal_curtail",
                self.inputs.thermal_must_take_units,
                self.inputs.thermal_derated_capacity,
            )
        ]
        for varname, unit_type, capacity_df in var_with_variable_ub_tuples:
            setattr(
                self,
                varname,
                add_var_with_variable_ub(
                    model=self.model,
                    varname=varname,
                    timesteps=self.timesteps,
                    step_k=step_k,
                    units=unit_type,
                    capacity_df=capacity_df,
                ),
            )

    def get_fixed_objective_terms(self) -> gp.LinExpr:
        """Get the fixed objective terms for the system builder.
        This method calculates the fixed objective terms based on the penalties for load shortfall,
        load curtailment, and spinning reserve shortfall.
        The penalties are multiplied by their respective factors defined in the inputs.

        Args:
            None

        Returns:
            gp.LinExpr: The fixed objective terms for the system builder.
        """

        self.load_shortfall_penalty_expr = (
            self.inputs.load_shortfall_penalty_factor * gp.quicksum(self.pos_pmismatch)
        )

        self.load_curtail_penalty_expr = (
            self.inputs.load_curtail_penalty_factor * gp.quicksum(self.neg_pmismatch)
        )

        self.spin_shortfall_penalty_expr = (
            self.inputs.spin_shortfall_penalty_factor * gp.quicksum(self.spin_shortfall)
        )

        return (
            self.load_shortfall_penalty_expr
            + self.load_curtail_penalty_expr
            + self.spin_shortfall_penalty_expr
        )

    def get_variable_objective_terms(
        self, step_k: int, curtail_cost_factor: float = 1.0
    ) -> gp.LinExpr:
        """Get the variable objective terms for the system builder. Specifically, this method
         calculates the curtailment penalties for must-take units.

        Args:
            step_k (int): The current simulation step.

        Returns:
            gp.LinExpr: An empty linear expression, as there are no variable objective terms defined.
        """
        self.must_take_curtail_penalty_expr = gp.LinExpr()

        # Thermal unit curtailment penalty
        thermal_coeffs = get_thermal_opex_coeff(
            step_k=step_k,
            timesteps=self.timesteps,
            thermal_units=self.inputs.thermal_must_take_units,
            thermal_opex=self.inputs.thermal_opex,
            fuel_contracts=self.inputs.fuel_contracts,
            contract_costs=self.inputs.contract_costs,
            thermal_heat_rate=self.inputs.thermal_heat_rate,
        )
        self.must_take_curtail_penalty_expr += (
            curtail_cost_factor * self.pthermal_curtail.prod(thermal_coeffs)
        )

        # Hourly hydro curtailment penalty
        hourly_hydro_coeffs = get_marginal_cost_coeff(
            step_k=step_k,
            timesteps=self.timesteps,
            units=self.inputs.hydro_must_take_units,
            nondispatch_contracts=self.inputs.nondispatch_contracts,
            contract_costs=self.inputs.contract_costs,
        )
        self.must_take_curtail_penalty_expr += (
            curtail_cost_factor * self.phydro_curtail.prod(hourly_hydro_coeffs)
        )

        # Daily hydro curtailment penalty
        daily_hydro_coeffs = get_marginal_cost_coeff(
            step_k=step_k,
            timesteps=self.timesteps,
            units=self.inputs.daily_hydro_must_take_units,
            nondispatch_contracts=self.inputs.nondispatch_contracts,
            contract_costs=self.inputs.contract_costs,
        )
        self.must_take_curtail_penalty_expr += (
            curtail_cost_factor
            * self.c_daily_hydro_curtail_ess.prod(daily_hydro_coeffs)
        )

        # Weekly hydro curtailment penalty
        weekly_hydro_coeffs = get_marginal_cost_coeff(
            step_k=step_k,
            timesteps=self.timesteps,
            units=self.inputs.weekly_hydro_must_take_units,
            nondispatch_contracts=self.inputs.nondispatch_contracts,
            contract_costs=self.inputs.contract_costs,
        )
        self.must_take_curtail_penalty_expr += (
            curtail_cost_factor
            * self.c_weekly_hydro_curtail_ess.prod(weekly_hydro_coeffs)
        )

        # Solar, wind, and import curtailment penalties
        nondispatch_tuples = [
            (
                self.psolar_curtail,
                self.inputs.solar_must_take_units,
                self.inputs.nondispatch_contracts,
            ),
            (
                self.pwind_curtail,
                self.inputs.wind_must_take_units,
                self.inputs.nondispatch_contracts,
            ),
            (
                self.pimp_curtail,
                self.inputs.import_must_take_units,
                self.inputs.nondispatch_contracts,
            ),
        ]
        for var_dict, units, contracts in nondispatch_tuples:
            nondispatch_penalty_cost_coeffs = get_marginal_cost_coeff(
                step_k=step_k,
                timesteps=self.timesteps,
                units=units,
                nondispatch_contracts=contracts,
                contract_costs=self.inputs.contract_costs,
            )
            self.must_take_curtail_penalty_expr += curtail_cost_factor * var_dict.prod(
                nondispatch_penalty_cost_coeffs
            )

        return self.must_take_curtail_penalty_expr

    def _add_nondispatchable_unit_curtailment(
        self,
        phydro: gp.tupledict,
        psolar: gp.tupledict,
        pwind: gp.tupledict,
        pimp: gp.tupledict,
        pcharge: gp.tupledict,
        step_k: int,
    ) -> None:
        """Set curtailment constraints for non-dispatchable units (solar, wind, import) with ESS.

        Args:
            phydro (gp.tupledict): Hydro power dispatch variable.
            psolar (gp.tupledict): Solar power dispatch variable.
            pwind (gp.tupledict): Wind power dispatch variable.
            pimp (gp.tupledict): Import power dispatch variable.
            pcharge (gp.tupledict): Power charge variable.
            step_k (int): Current simulation step.

        Returns:
            None
        """
        unit_types_with_ess = {
            "hydro": {
                "pdispatch": phydro,
                "pcurtail": self.phydro_curtail,
                "pcharge": pcharge,
                "units": self.inputs.hydro_must_take_units,
                "capacity_df": self.inputs.hydro_capacity,
                "ess_attached": self.inputs.ess_hydro_units,
            },
            "solar": {
                "pdispatch": psolar,
                "pcurtail": self.psolar_curtail,
                "pcharge": pcharge,
                "units": self.inputs.solar_must_take_units,
                "capacity_df": self.inputs.solar_capacity,
                "ess_attached": self.inputs.ess_solar_units,
            },
            "wind": {
                "pdispatch": pwind,
                "pcurtail": self.pwind_curtail,
                "pcharge": pcharge,
                "units": self.inputs.wind_must_take_units,
                "capacity_df": self.inputs.wind_capacity,
                "ess_attached": self.inputs.ess_wind_units,
            },
            "import": {
                "pdispatch": pimp,
                "pcurtail": self.pimp_curtail,
                "pcharge": pcharge,
                "units": self.inputs.import_must_take_units,
                "capacity_df": self.inputs.import_capacity,
                "ess_attached": {},  # No ESS attached to import sources
            },
        }

        for unit_type, params in unit_types_with_ess.items():
            setattr(
                self,
                f"c_{unit_type}_curtail_ess",
                system_constr.add_c_unit_curtail_ess(
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

    def add_constraints(self, step_k: int, init_conds: dict, **kwargs) -> None:

        # Thermal-unit specific variables
        spin_vars = kwargs.get("spin_vars", None)
        vpowerbar_vars = kwargs.get("vpowerbar_vars", None)
        thermal_status_vars = kwargs.get("thermal_status_vars", None)

        # Power variables
        pthermal = kwargs.get("pthermal", None)
        phydro = kwargs.get("phydro", None)
        psolar = kwargs.get("psolar", None)
        pwind = kwargs.get("pwind", None)
        pimp = kwargs.get("pimp", None)

        pcharge = kwargs.get("pcharge", None)
        pdischarge = kwargs.get("pdischarge", None)
        charge_state = kwargs.get("charge_state", None)

        # --- Spinning reserve constraints ---
        if self.inputs.use_spin_var:
            self.c_reserve_req = system_constr.add_c_reserve_req_1(
                model=self.model,
                spin=spin_vars,
                charge_state=charge_state,
                spin_shortfall=self.spin_shortfall,
                timesteps=self.timesteps,
                step_k=step_k,
                thermal_units=self.inputs.thermal_units,
                storage_units=self.inputs.storage_units,
                spin_requirement=self.inputs.spin_requirement,
            )
        else:
            self.c_reserve_req = system_constr.add_c_reserve_req_2(
                model=self.model,
                pbar=vpowerbar_vars,
                u=thermal_status_vars,
                charge_state=charge_state,
                spin_shortfall=self.spin_shortfall,
                timesteps=self.timesteps,
                step_k=step_k,
                thermal_units=self.inputs.thermal_units,
                thermal_min_capacity=self.inputs.thermal_min_capacity,
                storage_units=self.inputs.storage_units,
                total_demand=self.inputs.total_demand,
                spin_requirement=self.inputs.spin_requirement,
            )

        # --- Power flow balance constraints ---
        self.c_flow_balance = system_constr.add_c_flow_balance(
            model=self.model,
            pthermal=pthermal,
            phydro=phydro,
            psolar=psolar,
            pwind=pwind,
            pimp=pimp,
            pcharge=pcharge,
            pdis=pdischarge,
            pos_pmismatch=self.pos_pmismatch,
            neg_pmismatch=self.neg_pmismatch,
            flow_fwd=self.flow_fwd,
            flow_bwd=self.flow_bwd,
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
            ess_charge_units=self.inputs.ess_substation_units,
            ess_discharge_units=self.inputs.ess_attach_unit,
            demand=self.inputs.demand,
            demand_nodes=self.inputs.demand_nodes,
            gen_loss_factor=self.inputs.gen_loss_factor,
            line_loss_factor=self.inputs.line_loss_factor,
        )

        # --- DC-OPF constraints ---
        if self.inputs.dc_opf == "voltage_angle":
            self.c_ref_node = system_constr.add_c_ref_node(
                model=self.model,
                theta=self.theta,
                timesteps=self.timesteps,
                max_demand_node=self.inputs.max_demand_node,
            )
            self.c_angle_diff = system_constr.add_c_angle_diff(
                model=self.model,
                flow_fwd=self.flow_fwd,
                flow_bwd=self.flow_bwd,
                theta=self.theta,
                timesteps=self.timesteps,
                step_k=step_k,
                edges=self.inputs.edges,
                susceptance=self.inputs.susceptance,
            )

        elif self.inputs.dc_opf == "kirchhoff":
            self.c_kirchhoff = system_constr.add_c_kirchhoff(
                model=self.model,
                flow_fwd=self.flow_fwd,
                flow_bwd=self.flow_bwd,
                timesteps=self.timesteps,
                step_k=step_k,
                edges=self.inputs.edges,
                cycle_map=self.inputs.cycle_map,
                susceptance=self.inputs.susceptance,
            )
        else:
            raise ValueError(f"Invalid DC-OPF parameter: {self.inputs.dc_opf}.")

        # --- Curtailment constraints ---
        self.c_thermal_curtail = system_constr.add_c_thermal_curtail_ess(
            model=self.model,
            pthermal=pthermal,
            pthermal_curtail=self.pthermal_curtail,
            pcharge=pcharge,
            timesteps=self.timesteps,
            step_k=step_k,
            thermal_derated_capacity=self.inputs.thermal_derated_capacity,
            thermal_must_take_units=self.inputs.thermal_must_take_units,
            ess_attached=self.inputs.ess_thermal_units,
        )

        # Non-dispatchable units (hydro, solar, wind, import)
        self._add_nondispatchable_unit_curtailment(
            phydro=phydro,
            psolar=psolar,
            pwind=pwind,
            pimp=pimp,
            pcharge=pcharge,
            step_k=step_k,
        )

        # Daily hydropower. Hourly is added later
        self.c_daily_hydro_curtail_ess = system_constr.add_c_unit_curtail_ess_daily(
            model=self.model,
            pdispatch=phydro,
            pcurtail=self.phydro_curtail,
            pcharge=pcharge,
            unit_type="hydro",
            sim_horizon=self.inputs.sim_horizon,
            step_k=step_k,
            units=self.inputs.daily_hydro_must_take_units,
            capacity_df=self.inputs.daily_hydro_capacity,
            ess_attached=self.inputs.ess_daily_hydro_units,
        )

    def update_variables(self, step_k: int) -> None:
        """Update the time-dependent upper bounds of the flow variables.

        Args:
            step_k (int): The current simulation step.

        Returns:
            None
        """
        update_flow_vars(
            flow_variables=self.flow_fwd,
            step_k=step_k,
            capacity_df=self.inputs.line_capacity,
            line_capacity_factor=self.inputs.line_capacity_factor,
        )
        update_flow_vars(
            flow_variables=self.flow_bwd,
            step_k=step_k,
            capacity_df=self.inputs.line_capacity,
            line_capacity_factor=self.inputs.line_capacity_factor,
        )

        thermal_unit_vars = [
            self.pthermal_curtail,
        ]
        for var_dict in thermal_unit_vars:
            update_var_with_variable_ub(
                var_dict, step_k, self.inputs.thermal_derated_capacity
            )

    def update_constraints(self, step_k: int, init_conds: dict, **kwargs) -> None:
        # Thermal-unit specific variables
        spin_vars = kwargs.get("spin_vars", None)
        vpowerbar_vars = kwargs.get("vpowerbar_vars", None)
        thermal_status_vars = kwargs.get("thermal_status_vars", None)

        # Power variables
        pthermal = kwargs.get("pthermal", None)
        phydro = kwargs.get("phydro", None)
        psolar = kwargs.get("psolar", None)
        pwind = kwargs.get("pwind", None)
        pimp = kwargs.get("pimp", None)

        pcharge = kwargs.get("pcharge", None)
        pdischarge = kwargs.get("pdischarge", None)
        charge_state = kwargs.get("charge_state", None)

        # --- Spinning reserve constraints ---
        self.model.remove(self.c_reserve_req)
        if self.inputs.use_spin_var:
            self.c_reserve_req = system_constr.add_c_reserve_req_1(
                model=self.model,
                spin=spin_vars,
                charge_state=charge_state,
                spin_shortfall=self.spin_shortfall,
                timesteps=self.timesteps,
                step_k=step_k,
                thermal_units=self.inputs.thermal_units,
                storage_units=self.inputs.storage_units,
                spin_requirement=self.inputs.spin_requirement,
            )
        else:
            self.c_reserve_req = system_constr.add_c_reserve_req_2(
                model=self.model,
                pbar=vpowerbar_vars,
                u=thermal_status_vars,
                charge_state=charge_state,
                spin_shortfall=self.spin_shortfall,
                timesteps=self.timesteps,
                step_k=step_k,
                thermal_units=self.inputs.thermal_units,
                thermal_min_capacity=self.inputs.thermal_min_capacity,
                storage_units=self.inputs.storage_units,
                total_demand=self.inputs.total_demand,
                spin_requirement=self.inputs.spin_requirement,
            )

        # --- Power flow balance constraints ---
        self.model.remove(self.c_flow_balance)
        self.c_flow_balance = system_constr.add_c_flow_balance(
            model=self.model,
            pthermal=pthermal,
            phydro=phydro,
            psolar=psolar,
            pwind=pwind,
            pimp=pimp,
            pcharge=pcharge,
            pdis=pdischarge,
            pos_pmismatch=self.pos_pmismatch,
            neg_pmismatch=self.neg_pmismatch,
            flow_fwd=self.flow_fwd,
            flow_bwd=self.flow_bwd,
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
            ess_charge_units=self.inputs.ess_substation_units,
            ess_discharge_units=self.inputs.ess_attach_unit,
            demand=self.inputs.demand,
            demand_nodes=self.inputs.demand_nodes,
            gen_loss_factor=self.inputs.gen_loss_factor,
            line_loss_factor=self.inputs.line_loss_factor,
        )

        # --- DC-OPF constraints ---

        if self.inputs.dc_opf == "voltage_angle":
            self.model.remove(self.c_angle_diff)
            self.c_angle_diff = system_constr.add_c_angle_diff(
                model=self.model,
                flow_fwd=self.flow_fwd,
                flow_bwd=self.flow_bwd,
                theta=self.theta,
                timesteps=self.timesteps,
                step_k=step_k,
                edges=self.inputs.edges,
                susceptance=self.inputs.susceptance,
            )

        elif self.inputs.dc_opf == "kirchhoff":
            # A simple network might not have any cycles
            if self.c_kirchhoff:
                self.model.remove(self.c_kirchhoff)
                self.c_kirchhoff = system_constr.add_c_kirchhoff(
                    model=self.model,
                    flow_fwd=self.flow_fwd,
                    flow_bwd=self.flow_bwd,
                    timesteps=self.timesteps,
                    step_k=step_k,
                    edges=self.inputs.edges,
                    cycle_map=self.inputs.cycle_map,
                    susceptance=self.inputs.susceptance,
                )

        # --- Curtailment constraints ---

        # Thermal units
        self.model.remove(self.c_thermal_curtail)
        self.c_thermal_curtail = system_constr.add_c_thermal_curtail_ess(
            model=self.model,
            pthermal=pthermal,
            pthermal_curtail=self.pthermal_curtail,
            pcharge=pcharge,
            timesteps=self.timesteps,
            step_k=step_k,
            thermal_derated_capacity=self.inputs.thermal_derated_capacity,
            thermal_must_take_units=self.inputs.thermal_must_take_units,
            ess_attached=self.inputs.ess_thermal_units,
        )

        # Non-dispatchable units
        self.model.remove(self.c_hydro_curtail_ess)
        self.model.remove(self.c_solar_curtail_ess)
        self.model.remove(self.c_wind_curtail_ess)
        self.model.remove(self.c_import_curtail_ess)
        self._add_nondispatchable_unit_curtailment(
            phydro=phydro,
            psolar=psolar,
            pwind=pwind,
            pimp=pimp,
            pcharge=pcharge,
            step_k=step_k,
        )

        # Daily hydropower units
        self.model.remove(self.c_daily_hydro_curtail_ess)
        self.c_daily_hydro_curtail_ess = system_constr.add_c_unit_curtail_ess_daily(
            model=self.model,
            pdispatch=phydro,
            pcurtail=self.phydro_curtail,
            pcharge=pcharge,
            unit_type="hydro",
            sim_horizon=self.inputs.sim_horizon,
            step_k=step_k,
            units=self.inputs.daily_hydro_must_take_units,
            capacity_df=self.inputs.daily_hydro_capacity,
            ess_attached=self.inputs.ess_daily_hydro_units,
        )

    def get_variables(self) -> dict[str, gp.tupledict]:
        """Get the variables of the system builder.

        Returns:
            dict[str, gp.tupledict]: A dictionary containing the variables of the system builder.
        """
        return {
            "pos_pmismatch": self.pos_pmismatch,
            "neg_pmismatch": self.neg_pmismatch,
            "spin_shortfall": self.spin_shortfall,
            "flow_fwd": self.flow_fwd,
            "flow_bwd": self.flow_bwd,
            "theta": self.theta,
        }
