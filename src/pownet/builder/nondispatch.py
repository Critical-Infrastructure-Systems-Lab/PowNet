"""nondispatch.py: Non-dispatchable (solar, wind, import) unit builder."""

from .basebuilder import ComponentBuilder

import gurobipy as gp

from ..input import SystemInput
from ..optim_model.variable_func import (
    add_var_with_variable_ub,
    update_var_with_variable_ub,
)
from ..optim_model.objfunc import get_marginal_cost_coeff
from ..optim_model.constraints import nondispatch_constr


class NonDispatchUnitBuilder(ComponentBuilder):
    """Builder class for solar, wind, and import units. The variables have
    time-dependent upper bounds, which is a time series of hourly availability
    (with respect to installed capacity). The hourly capacity constraints are
    enforced as contracted capacities, which are time-invariant. Of course, the contracted capacity
    must be less than or equal to the installed capacity. A user may choose to use
    status variables to indicate whether the unit is generating or not.

    Variables
    ===========================
    `psolar`: Solar generation
    `usolar`: Solar output indicator

    `pwind`: Wind generation
    `uwind`: Wind output indicator

    `pimp`: Import generation
    `uimp`: Import output indicator

    Fixed objective terms
    ===========================
    None

    Variable objective terms
    ===========================
    - Energy cost

    Constraints
    ===========================
    - Upper bounds of dispatch variables to contracted capacities
    - Linking upper bounds of dispatch variables to unit status variables

    """

    def __init__(self, model: gp.Model, inputs: SystemInput):
        super().__init__(model, inputs)

        # Variables
        self.psolar = gp.tupledict()
        self.usolar = gp.tupledict()

        self.pwind = gp.tupledict()
        self.uwind = gp.tupledict()

        self.pimp = gp.tupledict()  # import
        self.uimp = gp.tupledict()

        # Fixed objective terms
        self.total_fixed_objective = gp.LinExpr()

        # Variable objective terms
        self.total_energy_cost = gp.LinExpr()

        # Constraints
        self.c_hourly_solar_ub = gp.tupledict()
        self.c_hourly_wind_ub = gp.tupledict()
        self.c_hourly_import_ub = gp.tupledict()

        self.c_link_solar_pu = gp.tupledict()
        self.c_link_wind_pu = gp.tupledict()
        self.c_link_import_pu = gp.tupledict()

    def add_variables(self, step_k: int) -> None:
        """
        Add variables to the model.

        Args:
            step_k (int): The current simulation step.

        Returns:
            None
        """
        var_with_variable_ub = [
            (
                "psolar",
                self.inputs.solar_units,
                self.inputs.solar_capacity,
            ),
            (
                "pwind",
                self.inputs.wind_units,
                self.inputs.wind_capacity,
            ),
            (
                "pimp",
                self.inputs.import_units,
                self.inputs.import_capacity,
            ),
        ]

        for varname, units, capacity_df in var_with_variable_ub:
            setattr(
                self,
                varname,
                add_var_with_variable_ub(
                    model=self.model,
                    varname=varname,
                    timesteps=self.timesteps,
                    step_k=step_k,
                    units=units,
                    capacity_df=capacity_df,
                ),
            )

        if self.inputs.use_nondispatch_status_var:
            # Binary variables
            var_binary_tuples = [
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
                        vtype=gp.GRB.BINARY,
                        name=varname,
                    ),
                )

    def get_fixed_objective_terms(self) -> gp.LinExpr:
        """Non-dispatchable units have no fixed objective terms."""
        return self.total_fixed_objective

    def get_variable_objective_terms(self, step_k: int) -> gp.LinExpr:
        """Calculate the variable objective terms for non-dispatchable units.

        Args:
            step_k (int): The current simulation step.

        Returns:
            gp.LinExpr: The variable objective terms.
        """
        # Energy cost is calculated based on the marginal cost of the units.
        energy_cost_tuples = [
            (
                self.psolar,
                self.inputs.solar_units,
            ),
            (
                self.pwind,
                self.inputs.wind_units,
            ),
            (
                self.pimp,
                self.inputs.import_units,
            ),
        ]
        self.total_energy_cost = gp.LinExpr()
        for var_dict, units in energy_cost_tuples:
            energy_cost_coeffs = get_marginal_cost_coeff(
                step_k=step_k,
                timesteps=self.timesteps,
                units=units,
                nondispatch_contracts=self.inputs.nondispatch_contracts,
                contract_costs=self.inputs.contract_costs,
            )
            self.total_energy_cost.add(var_dict.prod(energy_cost_coeffs))

        return self.total_energy_cost

    def _add_unit_link_pu(self) -> None:
        """Add constraints to link the dispatch variable and the unit status variable.

        Args:
            None

        Returns:
            None
        """
        unit_params = {
            "solar": {
                "p": self.psolar,
                "u": self.usolar,
                "units": self.inputs.solar_units,
                "contracted_capacity_dict": self.inputs.solar_contracted_capacity,
            },
            "wind": {
                "p": self.pwind,
                "u": self.uwind,
                "units": self.inputs.wind_units,
                "contracted_capacity_dict": self.inputs.wind_contracted_capacity,
            },
            "import": {
                "p": self.pimp,
                "u": self.uimp,
                "units": self.inputs.import_units,
                "contracted_capacity_dict": self.inputs.import_contracted_capacity,
            },
        }
        for unit_type, params in unit_params.items():
            setattr(
                self,
                f"c_link_{unit_type}_pu",
                nondispatch_constr.add_c_link_unit_pu(
                    model=self.model,
                    pdispatch=params["p"],
                    u=params["u"],
                    unit_type=unit_type,
                    timesteps=self.timesteps,
                    units=params["units"],
                    contracted_capacity_dict=params["contracted_capacity_dict"],
                ),
            )

    def add_constraints(self, step_k: int, init_conds: dict, **kwargs) -> None:
        """Add constraints to the model.

        Args:
            step_k (int): The current simulation step.
            init_conds (dict): Initial conditions for the model.

        Returns:
            None
        """
        # Hourly upper bounds are contracted capacities
        hourly_ub_tuples = [
            (
                self.psolar,
                "solar",
                self.inputs.solar_units,
                self.inputs.solar_contracted_capacity,
            ),
            (
                self.pwind,
                "wind",
                self.inputs.wind_units,
                self.inputs.wind_contracted_capacity,
            ),
            (
                self.pimp,
                "import",
                self.inputs.import_units,
                self.inputs.import_contracted_capacity,
            ),
        ]
        for (
            pdispatch,
            unit_type,
            units,
            contracted_capacity_dict,
        ) in hourly_ub_tuples:
            setattr(
                self,
                f"c_hourly_{unit_type}_ub",
                nondispatch_constr.add_c_hourly_unit_ub(
                    model=self.model,
                    pdispatch=pdispatch,
                    unit_type=unit_type,
                    timesteps=self.timesteps,
                    units=units,
                    contracted_capacity_dict=contracted_capacity_dict,
                ),
            )

        # In case we want to use the status variables
        if self.inputs.use_nondispatch_status_var:
            self._add_unit_link_pu()

    def update_variables(self, step_k: int) -> None:
        """The variables have time-dependent upper bounds."""
        # Update the time-dependent upper bound of the variable
        var_tuples = [("psolar", "solar"), ("pwind", "wind"), ("pimp", "import")]

        for varname, unit_type in var_tuples:
            var = getattr(self, varname)
            update_var_with_variable_ub(
                variables=var,
                step_k=step_k,
                capacity_df=getattr(self.inputs, f"{unit_type}_capacity"),
            )

    def update_constraints(self, step_k: int, init_conds: dict, **kwargs) -> None:
        """Update the constraints for non-dispatchable units. Currently,
        this function does not update any constraints, but it is included for
        consistency with the base class.

        Args:
            step_k (int): The current simulation step.
            init_conds (dict): Initial conditions for the model.

        Returns:
            None
        """
        return

    def get_variables(self) -> dict[str, gp.tupledict]:
        """Return all variables in the builder.

        Returns:
            dict[str, gp.tupledict]: A dictionary containing all variables in the builder.
        """
        if self.inputs.use_nondispatch_status_var:
            return {
                "psolar": self.psolar,
                "usolar": self.usolar,
                "pwind": self.pwind,
                "uwind": self.uwind,
                "pimp": self.pimp,
                "uimp": self.uimp,
            }
        else:
            return {
                "psolar": self.psolar,
                "pwind": self.pwind,
                "pimp": self.pimp,
            }
