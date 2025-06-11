"""energy_storage.py: Energy storage unit builder."""

from .basebuilder import ComponentBuilder

import gurobipy as gp

from ..input import SystemInput
from ..optim_model import (
    add_var_with_variable_ub,
    update_var_with_variable_ub,
)
from ..optim_model.objfunc import get_marginal_cost_coeff
from ..optim_model.constraints import energy_storage_constr


class EnergyStorageUnitBuilder(ComponentBuilder):
    """Builder class for energy storage units.

    Variables
    ===========================
    - `pcharge`: Power charging an energy storage system. Unit: MW.
    - `pdischarge`: Power discharging an energy storage system. Unit: MW.
    - `charge_state`: State of charge of an energy storage system. Unit: MWh.
    - `ucharge`: Indicator that an ESS is charging. Unitless.
    - `udischarge`: Indicator that an ESS is discharging. Unitless.

    Fixed objective terms
    ===========================
    None

    Variable objective terms
    ===========================
    - Energy cost

    Constraints
    ===========================
    - Linking upper bounds of dispatch variables to unit status variables

    """

    def __init__(self, model: gp.Model, inputs: SystemInput):
        super().__init__(model, inputs)

        # Variables
        self.pcharge = gp.tupledict()
        self.pdischarge = gp.tupledict()

        self.charge_state = gp.tupledict()
        self.ucharge = gp.tupledict()  # Charging indicator
        self.udischarge = gp.tupledict()  # Discharging indicator

        # Fixed objective terms
        self.total_fixed_objective_expr = gp.LinExpr()

        # Variable objective terms
        self.total_energy_cost_expr = gp.LinExpr()

        # Constraints
        # Constraints
        self.c_link_ess_charge = gp.tupledict()
        self.c_link_ess_dischage = gp.tupledict()
        self.c_link_ess_state = gp.tupledict()
        self.c_unit_ess_balance_init = gp.tupledict()
        self.c_unit_ess_balance = gp.tupledict()

    def add_variables(self, step_k: int) -> None:
        """
        Add energy storage variables to the model.

        Args:
            step_k (int): The current simulation step.

        Returns:
            None
        """

        # Variables with fixed upper bounds
        var_with_fixed_ub = [
            ("pcharge", self.inputs.ess_max_charge),
            ("pdischarge", self.inputs.ess_max_discharge),
        ]

        for varname, capacity_dict in var_with_fixed_ub:
            setattr(
                self,
                varname,
                self.model.addVars(
                    self.inputs.storage_units,
                    self.timesteps,
                    lb=0,
                    ub={
                        (unit, t): capacity_dict[unit]
                        for t in self.timesteps
                        for unit in self.inputs.storage_units
                    },
                    name=varname,
                ),
            )

        # Variables with time-dependent upper bounds
        self.charge_state = add_var_with_variable_ub(
            model=self.model,
            varname="charge_state",
            timesteps=self.timesteps,
            step_k=step_k,
            units=self.inputs.storage_units,
            capacity_df=self.inputs.ess_derated_capacity,
        )

        # Binary variables
        binary_variables = ["ucharge", "udischarge"]
        for varname in binary_variables:
            setattr(
                self,
                varname,
                self.model.addVars(
                    self.inputs.storage_units,
                    self.timesteps,
                    vtype=gp.GRB.BINARY,
                    name=varname,
                ),
            )

    def get_fixed_objective_terms(self) -> gp.LinExpr:
        """Energy storage units have no fixed objective terms."""
        return self.total_fixed_objective_expr

    def get_variable_objective_terms(self, step_k: int) -> gp.LinExpr:
        """Calculate the variable objective terms for energy storage units.

        Args:
            step_k (int): The current simulation step.

        Returns:
            gp.LinExpr: The variable objective terms.
        """
        # Energy cost is calculated based on the marginal cost of the units.
        self.total_energy_cost_expr = gp.LinExpr()
        energy_cost_coeffs = get_marginal_cost_coeff(
            step_k=step_k,
            timesteps=self.timesteps,
            units=self.inputs.storage_units,
            nondispatch_contracts=self.inputs.ess_contracts,
            contract_costs=self.inputs.contract_costs,
        )
        self.total_energy_cost_expr.add(self.pdischarge.prod(energy_cost_coeffs))
        return self.total_energy_cost_expr

    def add_constraints(self, step_k: int, init_conds: dict, **kwargs) -> None:
        """Add constraints to the model.

        Args:
            step_k (int): The current simulation step.
            init_conds (dict): Initial conditions for the model.

        Returns:
            None
        """
        self.c_link_ess_charge = energy_storage_constr.add_c_link_ess_charge(
            model=self.model,
            pcharge=self.pcharge,
            ucharge=self.ucharge,
            timesteps=self.timesteps,
            units=self.inputs.storage_units,
            max_charge=self.inputs.ess_max_charge,
        )

        self.c_link_ess_dischage = energy_storage_constr.add_c_link_ess_discharge(
            model=self.model,
            pdischarge=self.pdischarge,
            udischarge=self.udischarge,
            timesteps=self.timesteps,
            units=self.inputs.storage_units,
            max_discharge=self.inputs.ess_max_discharge,
        )

        self.c_link_ess_state = energy_storage_constr.add_c_link_ess_state(
            model=self.model,
            ucharge=self.ucharge,
            udischarge=self.udischarge,
            timesteps=self.timesteps,
            units=self.inputs.storage_units,
        )

        self.c_unit_ess_balance_init = (
            energy_storage_constr.add_c_unit_ess_balance_init(
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
        )

        self.c_unit_ess_balance = energy_storage_constr.add_c_unit_ess_balance(
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

    def update_variables(self, step_k: int) -> None:
        """Update the variables for energy storage units.

        Args:
            step_k (int): The current simulation step.

        Returns:
            None
        """
        update_var_with_variable_ub(
            variables=self.charge_state,
            step_k=step_k,
            capacity_df=self.inputs.ess_derated_capacity,
        )

    def update_constraints(self, step_k: int, init_conds: dict, **kwargs) -> None:
        """Update the constraints for energy storage units.

        Args:
            step_k (int): The current simulation step.
            init_conds (dict): Initial conditions for the model.

        Returns:
            None
        """
        self.model.remove(self.c_unit_ess_balance_init)
        self.c_unit_ess_balance_init = (
            energy_storage_constr.add_c_unit_ess_balance_init(
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
        )

    def get_variables(self) -> dict[str, gp.tupledict]:
        """Return all variables in the energy storage unit builder.

        Returns:
            dict[str, gp.tupledict]: A dictionary containing all variables in the builder.
        """
        return {
            "pcharge": self.pcharge,
            "pdischarge": self.pdischarge,
            "charge_state": self.charge_state,
            "ucharge": self.ucharge,
            "udischarge": self.udischarge,
        }
