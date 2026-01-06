"""hydro.py: Hydro unit builder. This includes hourly, daily, and weekly constraints for hydro units."""

from .basebuilder import ComponentBuilder

import gurobipy as gp

from ..input import SystemInput
from ..optim_model.variable_func import (
    add_var_with_variable_ub,
    update_var_with_variable_ub,
)
from ..optim_model.objfunc import get_marginal_cost_coeff
from ..optim_model.constraints import nondispatch_constr


class HydroUnitBuilder(ComponentBuilder):
    """Builder class for hydro units. If a hydro unit's hourly availability is provided,
    then the hydro unit's dispatch variables are limited by them. If a hydro unit's
    hourly availability is not provided, as in the case with daily/weekly hydro units,
    then the hydro unit's dispatch variables are limited by the contracted capacity.

    Variables
    ===========================
    - `phydro`: Hydropower output. Unit: MW.
    - `uhydro`: Hydropower unit status. Unit: binary (0 or 1). (optional)

    Fixed objective terms
    ===========================
    None

    Variable objective terms
    ===========================
    - Energy cost

    Constraints
    ===========================
    - Hourly/Daily/Weekly hydropower limits
    - Linking upper bounds of dispatch variables to unit status variables

    """

    def __init__(self, model: gp.Model, inputs: SystemInput):
        super().__init__(model, inputs)

        # Variables
        self.phydro = gp.tupledict()
        self.hourly_phydro = gp.tupledict()
        self.daily_phydro = gp.tupledict()
        self.weekly_phydro = gp.tupledict()

        self.uhydro = gp.tupledict()

        # Fixed objective terms
        self.total_fixed_objective_expr = gp.LinExpr()

        # Variable objective terms
        self.total_energy_cost_expr = gp.LinExpr()

        # Constraints
        self.c_hourly_hydro_ub = gp.tupledict()
        self.c_hourly_hydro_lb = gp.tupledict()
        self.c_hydro_limit_daily = gp.tupledict()
        self.c_hydro_limit_weekly = gp.tupledict()

        self.c_link_hydro_pu = gp.tupledict()

        self.c_hydro_ramp_up_init = gp.tupledict()
        self.c_hydro_ramp_up = gp.tupledict()
        self.c_hydro_ramp_down_init = gp.tupledict()
        self.c_hydro_ramp_down = gp.tupledict()
        self.c_hydro_ramp_cost_def = gp.tupledict()
        self.c_hydro_ramp_cost_def_init = gp.tupledict()

    def add_variables(self, step_k: int) -> None:
        """Add variables to the model for hydro units.

        Args:
            step_k (int): Current time step.
        """
        # --- Hourly hydropower
        self.hourly_phydro = add_var_with_variable_ub(
            model=self.model,
            varname="phydro",
            timesteps=self.timesteps,
            step_k=step_k,
            units=self.inputs.hydro_unit_node.keys(),
            capacity_df=self.inputs.hydro_capacity,
        )

        # --- Daily/weekly hydropower are limited by contracted capacity
        self.daily_phydro = self.model.addVars(
            self.inputs.daily_hydro_unit_node.keys(),
            self.timesteps,
            lb={
                (unit, t): self.inputs.hydro_contracted_capacity_min[unit]
                for unit in self.inputs.daily_hydro_unit_node.keys()
                for t in self.timesteps
            },
            ub={
                (unit, t): self.inputs.hydro_contracted_capacity[unit]
                for unit in self.inputs.daily_hydro_unit_node.keys()
                for t in self.timesteps
            },
            vtype=gp.GRB.CONTINUOUS,
            name="phydro",
        )

        self.weekly_phydro = self.model.addVars(
            self.inputs.weekly_hydro_unit_node.keys(),
            self.timesteps,
            lb={
                (unit, t): self.inputs.hydro_contracted_capacity_min[unit]
                for unit in self.inputs.weekly_hydro_unit_node.keys()
                for t in self.timesteps
            },
            ub={
                (unit, t): self.inputs.hydro_contracted_capacity[unit]
                for unit in self.inputs.weekly_hydro_unit_node.keys()
                for t in self.timesteps
            },
            vtype=gp.GRB.CONTINUOUS,
            name="phydro",
        )

        # Collect the dispatch variables (shallow copy)
        self.phydro.update(self.hourly_phydro)
        self.phydro.update(self.daily_phydro)
        self.phydro.update(self.weekly_phydro)

        if self.inputs.use_nondispatch_status_var:
            self.uhydro = self.model.addVars(
                self.inputs.hydro_units,
                self.timesteps,
                lb=0,
                vtype=gp.GRB.BINARY,
                name="uhydro",
            )

        # Ramp magnitude variables for ramping penalty
        # Defined for all hydro units and all timesteps
        self.hydro_ramp_up = self.model.addVars(
            self.inputs.hydro_units, self.timesteps, lb=0, vtype=gp.GRB.CONTINUOUS, name="hydro_ramp_up"
        )
        self.hydro_ramp_dn = self.model.addVars(
            self.inputs.hydro_units, self.timesteps, lb=0, vtype=gp.GRB.CONTINUOUS, name="hydro_ramp_dn"
        )


#TODO add fixed ramping cost term to the objective
    def get_fixed_objective_terms(self) -> gp.LinExpr:
        """Hydropower units have no fixed objective terms."""
        return self.total_fixed_objective_expr

    def get_variable_objective_terms(self, step_k: int) -> gp.LinExpr:
        """Get variable objective terms for hydro units.

        Args:
            step_k (int): Current time step.

        Returns:
            gp.LinExpr: The variable objective terms for hydro units.
        """

        # --- Energy cost
        energy_cost_coeffs = get_marginal_cost_coeff(
            step_k=step_k,
            timesteps=self.timesteps,
            units=self.inputs.hydro_units,
            nondispatch_contracts=self.inputs.nondispatch_contracts,
            contract_costs=self.inputs.contract_costs,
        )
        self.total_energy_cost_expr = self.phydro.prod(energy_cost_coeffs)

        # Ramping penalty cost: Default to 0 if not provided
        ramp_pen = getattr(self.inputs, "hydro_ramp_penalty", {})
        ramp_pen = {u: float(ramp_pen.get(u, 0.0)) for u in self.inputs.hydro_units}

        ramp_cost_expr = gp.LinExpr()
        for u in self.inputs.hydro_units:
            if ramp_pen[u] == 0.0:
                continue
            for t in self.timesteps:
                ramp_cost_expr += ramp_pen[u] * (self.hydro_ramp_up[u, t] + self.hydro_ramp_dn[u, t])

        return self.total_energy_cost_expr + ramp_cost_expr

# TODO check if you can just add the ramp constr here
    def add_constraints(self, step_k: int, init_conds: dict, **kwargs) -> None:
        # Hourly upper bound
        # Limited by contracted capacity
        self.c_hourly_hydro_ub = nondispatch_constr.add_c_hourly_unit_ub(
            model=self.model,
            pdispatch=self.hourly_phydro,
            unit_type="hydro",
            timesteps=self.timesteps,
            units=self.inputs.hydro_unit_node.keys(),
            contracted_capacity_dict=self.inputs.hydro_contracted_capacity,
        )

        self.c_hourly_hydro_lb = nondispatch_constr.add_c_hourly_unit_lb(
            model=self.model,
            pdispatch=self.hourly_phydro,
            unit_type="hydro",
            timesteps=self.timesteps,
            units=self.inputs.hydro_unit_node.keys(),
            contracted_capacity_min_dict=self.inputs.hydro_contracted_capacity_min,
        )

        # Daily upper bound
        self.c_hydro_limit_daily = nondispatch_constr.add_c_hydro_limit_daily(
            model=self.model,
            phydro=self.phydro,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            hydro_units=self.inputs.daily_hydro_unit_node.keys(),
            hydro_capacity=self.inputs.daily_hydro_capacity,
        )

        # Weekly upper bounds
        self.c_hydro_limit_weekly = nondispatch_constr.add_c_hydro_limit_weekly(
            model=self.model,
            phydro=self.phydro,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            hydro_units=self.inputs.weekly_hydro_unit_node.keys(),
            hydro_capacity=self.inputs.weekly_hydro_capacity,
        )

        if not self.inputs.hydro_min_capacity.empty:
            self.c_hydro_limit_weekly_lb = nondispatch_constr.add_c_hydro_limit_weekly_lb(
                model=self.model,
                phydro=self.phydro,
                step_k=step_k,
                sim_horizon=self.inputs.sim_horizon,
                hydro_units=self.inputs.weekly_hydro_unit_node.keys(),
                hydro_capacity_min=self.inputs.hydro_min_capacity,
            )

        if self.inputs.use_nondispatch_status_var:
            self.c_link_hydro_pu = nondispatch_constr.add_c_link_unit_pu(
                model=self.model,
                pdispatch=self.phydro,
                u=self.uhydro,
                unit_type="hydro",
                timesteps=self.timesteps,
                units=self.inputs.hydro_units,
                contracted_capacity_dict=self.inputs.hydro_contracted_capacity,
            )

        # Hydro ramping constraints
        self.c_hydro_ramp_up_init = nondispatch_constr.add_c_hydro_ramp_up_init(
            model=self.model,
            phydro=self.phydro,
            hydro_units=self.inputs.hydro_units,
            initial_phydro=init_conds.get("initial_phydro", {}),
            hydro_RU=self.inputs.hydro_RU,
        )

        self.c_hydro_ramp_up = nondispatch_constr.add_c_hydro_ramp_up(
            model=self.model,
            phydro=self.phydro,
            sim_horizon=self.inputs.sim_horizon,
            hydro_units=self.inputs.hydro_units,
            hydro_RU=self.inputs.hydro_RU,
        )

        self.c_hydro_ramp_down_init = nondispatch_constr.add_c_hydro_ramp_down_init(
            model=self.model,
            phydro=self.phydro,
            hydro_units=self.inputs.hydro_units,
            initial_phydro=init_conds.get("initial_phydro", {}),
            hydro_RD=self.inputs.hydro_RD,
        )

        self.c_hydro_ramp_down = nondispatch_constr.add_c_hydro_ramp_down(
            model=self.model,
            phydro=self.phydro,
            sim_horizon=self.inputs.sim_horizon,
            hydro_units=self.inputs.hydro_units,
            hydro_RD=self.inputs.hydro_RD,
        )

        # Ramp magnitude definitions for ramping penalty
        # t=1 uses initial_phydro, t>1 uses phydro[t-1]
        init_phydro = init_conds.get("initial_phydro", {})
        safe_init = {u: float(init_phydro.get(u, 0.0)) for u in self.inputs.hydro_units}

        # t=1
        self.c_hydro_ramp_cost_def_init = self.model.addConstrs(
            (self.hydro_ramp_up[u, 1] >= self.phydro[u, 1] - safe_init[u] for u in self.inputs.hydro_units),
            name="hydro_ramp_cost_def_up_init",
        )
        self.c_hydro_ramp_cost_def_init.update(
            self.model.addConstrs(
                (self.hydro_ramp_dn[u, 1] >= safe_init[u] - self.phydro[u, 1] for u in self.inputs.hydro_units),
                name="hydro_ramp_cost_def_dn_init",
            )
        )

        # t>=2
        self.c_hydro_ramp_cost_def = self.model.addConstrs(
            (self.hydro_ramp_up[u, t] >= self.phydro[u, t] - self.phydro[u, t - 1]
             for u in self.inputs.hydro_units for t in range(2, self.inputs.sim_horizon + 1)),
            name="hydro_ramp_cost_def_up",
        )
        self.c_hydro_ramp_cost_def.update(
            self.model.addConstrs(
                (self.hydro_ramp_dn[u, t] >= self.phydro[u, t - 1] - self.phydro[u, t]
                 for u in self.inputs.hydro_units for t in range(2, self.inputs.sim_horizon + 1)),
                name="hydro_ramp_cost_def_dn",
            )
        )

    def update_variables(self, step_k: int) -> None:
        "Some hydropower units have hourly upper bounds."
        # Update the time-dependent upper bound of the variable
        update_var_with_variable_ub(
            variables=self.hourly_phydro,
            step_k=step_k,
            capacity_df=self.inputs.hydro_capacity,
        )


    def update_constraints(self, step_k: int, init_conds: dict, **kwargs) -> None:
        """Update constraints for hydro units.
        Args:
            step_k (int): Current time step.
            init_conds (dict): Initial conditions for the model.

        Returns:
            None
        """

        self.model.remove(self.c_hydro_limit_daily)
        self.c_hydro_limit_daily = nondispatch_constr.add_c_hydro_limit_daily(
            model=self.model,
            phydro=self.phydro,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            hydro_units=self.inputs.daily_hydro_unit_node.keys(),
            hydro_capacity=self.inputs.daily_hydro_capacity,
        )

        self.model.remove(self.c_hydro_limit_weekly)
        self.c_hydro_limit_weekly = nondispatch_constr.add_c_hydro_limit_weekly(
            model=self.model,
            phydro=self.phydro,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            hydro_units=self.inputs.weekly_hydro_unit_node.keys(),
            hydro_capacity=self.inputs.weekly_hydro_capacity,
            # hydro_capacity_min=self.inputs.hydro_min_capacity,
        )

        if not self.inputs.hydro_min_capacity.empty:
            self.model.remove(self.c_hydro_limit_weekly_lb)
            self.c_hydro_limit_weekly_lb = nondispatch_constr.add_c_hydro_limit_weekly_lb(
                model=self.model,
                phydro=self.phydro,
                step_k=step_k,
                sim_horizon=self.inputs.sim_horizon,
                hydro_units=self.inputs.weekly_hydro_unit_node.keys(),
                hydro_capacity_min=self.inputs.hydro_min_capacity,
            )

        # Remove old ramping constraints
        self.model.remove(self.c_hydro_ramp_up_init)
        self.model.remove(self.c_hydro_ramp_down_init)

        if self.c_hydro_ramp_cost_def_init:
            self.model.remove(self.c_hydro_ramp_cost_def_init)

        init_phydro = init_conds.get("initial_phydro", {})
        safe_init = {u: float(init_phydro.get(u, 0.0)) for u in self.inputs.hydro_units}

        self.c_hydro_ramp_cost_def_init = self.model.addConstrs(
            (self.hydro_ramp_up[u, 1] >= self.phydro[u, 1] - safe_init[u] for u in self.inputs.hydro_units),
            name="hydro_ramp_cost_def_up_init",
        )
        self.c_hydro_ramp_cost_def_init.update(
            self.model.addConstrs(
                (self.hydro_ramp_dn[u, 1] >= safe_init[u] - self.phydro[u, 1] for u in self.inputs.hydro_units),
                name="hydro_ramp_cost_def_dn_init",
            )
        )

    def update_daily_hydropower_capacity(
        self, step_k: int, new_capacity: dict[tuple[str, int], float]
    ) -> None:
        self.model.remove(self.c_hydro_limit_daily)
        self.c_hydro_limit_daily = nondispatch_constr.add_c_hydro_limit_daily_dict(
            model=self.model,
            phydro=self.phydro,
            step_k=step_k,
            sim_horizon=self.inputs.sim_horizon,
            hydro_units=self.inputs.daily_hydro_unit_node.keys(),
            hydro_capacity_dict=new_capacity,
        )

    def get_variables(self) -> dict[str, gp.tupledict]:
        """Get hydro unit variables.

        Returns:
            dict: Dictionary of hydro unit variables.
        """
        return {
            "phydro": self.phydro,
            "uhydro": self.uhydro,
        }
