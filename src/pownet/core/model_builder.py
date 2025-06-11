"""builder.py: This module contains the ModelBuilder class, which is responsible
for constructing and updating the optimization model for the power system.
"""

from ..input import SystemInput

from gurobipy import GRB
import gurobipy as gp

from ..optim_model import PowerSystemModel
from ..builder.thermal import ThermalUnitBuilder
from ..builder.hydro import HydroUnitBuilder
from ..builder.nondispatch import NonDispatchUnitBuilder
from ..builder.energy_storage import EnergyStorageUnitBuilder
from ..builder.system import SystemBuilder


class ModelBuilder:
    def __init__(self, inputs: SystemInput) -> None:
        self.inputs = inputs
        self.model: gp.Model = gp.Model(self.inputs.model_id)

        # Instantiate specialized builders, passing the model, inputs, and timesteps
        self.thermal_builder = ThermalUnitBuilder(self.model, self.inputs)
        self.hydro_builder = HydroUnitBuilder(self.model, self.inputs)
        self.nondispatch_builder = NonDispatchUnitBuilder(self.model, self.inputs)
        self.storage_builder = EnergyStorageUnitBuilder(self.model, self.inputs)
        self.system_builder = SystemBuilder(self.model, self.inputs)

        # Model attributes
        self.total_fixed_objective_expr = gp.LinExpr()

    def build(self, step_k: int, init_conds: dict[str, dict]) -> PowerSystemModel:
        """Build the initial optimization model by delegating to specialized builders."""

        ###########################################
        # Add variables
        ###########################################
        self.thermal_builder.add_variables(step_k=step_k)
        self.hydro_builder.add_variables(step_k=step_k)
        self.nondispatch_builder.add_variables(step_k=step_k)
        self.storage_builder.add_variables(step_k=step_k)
        self.system_builder.add_variables(step_k=step_k)

        ###########################################
        # Set Objective Function
        ###########################################

        # --- Add fixed objective terms
        self.total_fixed_objective_expr = (
            self.thermal_builder.get_fixed_objective_terms()
        )
        self.total_fixed_objective_expr += (
            self.hydro_builder.get_fixed_objective_terms()
        )
        self.total_fixed_objective_expr += (
            self.nondispatch_builder.get_fixed_objective_terms()
        )
        self.total_fixed_objective_expr += (
            self.storage_builder.get_fixed_objective_terms()
        )
        self.total_fixed_objective_expr += (
            self.system_builder.get_fixed_objective_terms()
        )

        # --- Add variable objective terms
        total_variable_objective_expr = (
            self.thermal_builder.get_variable_objective_terms(step_k=step_k)
        )
        total_variable_objective_expr += (
            self.hydro_builder.get_variable_objective_terms(step_k=step_k)
        )
        total_variable_objective_expr += (
            self.nondispatch_builder.get_variable_objective_terms(step_k=step_k)
        )
        total_variable_objective_expr += (
            self.storage_builder.get_variable_objective_terms(step_k=step_k)
        )
        total_variable_objective_expr += (
            self.system_builder.get_variable_objective_terms(step_k=step_k)
        )

        # --- Sum up all fixed and variable objective terms
        total_objective_expr = (
            self.total_fixed_objective_expr + total_variable_objective_expr
        )
        self.model.setObjective(total_objective_expr, sense=GRB.MINIMIZE)

        ###########################################
        # Add Constraints
        ###########################################
        self.thermal_builder.add_constraints(step_k=step_k, init_conds=init_conds)
        self.hydro_builder.add_constraints(step_k=step_k, init_conds=init_conds)
        self.nondispatch_builder.add_constraints(step_k=step_k, init_conds=init_conds)
        self.storage_builder.add_constraints(step_k=step_k, init_conds=init_conds)
        self.system_builder.add_constraints(
            step_k=step_k,
            init_conds=init_conds,
            spin_vars=self.thermal_builder.spin,
            vpowerbar_vars=self.thermal_builder.vpowerbar,
            thermal_status_vars=self.thermal_builder.status,
            pthermal=self.thermal_builder.pthermal,
            phydro=self.hydro_builder.phydro,
            psolar=self.nondispatch_builder.psolar,
            pwind=self.nondispatch_builder.pwind,
            pimp=self.nondispatch_builder.pimp,
            pcharge=self.storage_builder.pcharge,
            pdischarge=self.storage_builder.pdischarge,
            charge_state=self.storage_builder.charge_state,
        )

        self.model.update()
        return PowerSystemModel(self.model)

    def update(self, step_k: int, init_conds: dict[str, dict]) -> PowerSystemModel:
        """Update the existing model for a new step_k by delegating to specialized builders."""

        ###########################################
        # Update variables
        ###########################################
        self.thermal_builder.update_variables(step_k=step_k)
        self.hydro_builder.update_variables(step_k=step_k)
        self.nondispatch_builder.update_variables(step_k=step_k)
        self.storage_builder.update_variables(step_k=step_k)
        self.system_builder.update_variables(step_k=step_k)

        ###########################################
        # Update Objective Function
        ###########################################

        updated_objective_expr = self.total_fixed_objective_expr.copy()

        # Rebuild the objective as terms/coefficients that change with step_k
        updated_objective_expr += self.thermal_builder.get_variable_objective_terms(
            step_k=step_k
        )
        updated_objective_expr += self.hydro_builder.get_variable_objective_terms(
            step_k=step_k
        )
        updated_objective_expr += self.nondispatch_builder.get_variable_objective_terms(
            step_k=step_k
        )
        updated_objective_expr += self.storage_builder.get_variable_objective_terms(
            step_k=step_k
        )
        updated_objective_expr += self.system_builder.get_variable_objective_terms(
            step_k=step_k
        )
        self.model.setObjective(updated_objective_expr, sense=GRB.MINIMIZE)

        ###########################################
        # Update Constraints
        ###########################################
        # Builders will handle removing old and adding new/modified constraints
        self.thermal_builder.update_constraints(step_k=step_k, init_conds=init_conds)
        self.hydro_builder.update_constraints(step_k=step_k, init_conds=init_conds)
        self.nondispatch_builder.update_constraints(
            step_k=step_k, init_conds=init_conds
        )
        self.storage_builder.update_constraints(step_k=step_k, init_conds=init_conds)
        self.system_builder.update_constraints(
            step_k=step_k,
            init_conds=init_conds,
            spin_vars=self.thermal_builder.spin,
            vpowerbar_vars=self.thermal_builder.vpowerbar,
            thermal_status_vars=self.thermal_builder.status,
            pthermal=self.thermal_builder.pthermal,
            phydro=self.hydro_builder.phydro,
            psolar=self.nondispatch_builder.psolar,
            pwind=self.nondispatch_builder.pwind,
            pimp=self.nondispatch_builder.pimp,
            pcharge=self.storage_builder.pcharge,
            pdischarge=self.storage_builder.pdischarge,
            charge_state=self.storage_builder.charge_state,
        )

        self.model.update()
        return PowerSystemModel(self.model)

    def get_phydro(self) -> gp.tupledict:
        """Get the hydro power variable from the model."""
        return self.hydro_builder.phydro

    def update_daily_hydropower_capacity(
        self, step_k: int, new_capacity: dict[tuple[str, int], float]
    ) -> PowerSystemModel:
        """Update the daily hydro capacity in the model."""
        self.hydro_builder.update_daily_hydropower_capacity(step_k, new_capacity)
        self.model.update()
        return PowerSystemModel(self.model)
