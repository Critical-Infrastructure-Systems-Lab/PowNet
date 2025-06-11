"""thermal_unit.py: Thermal unit builder."""

from .basebuilder import ComponentBuilder

import gurobipy as gp
import pandas as pd

from ..input import SystemInput
from ..optim_model import (
    add_var_with_variable_ub,
    update_var_with_variable_ub,
    get_thermal_fixed_coeff,
    get_thermal_startup_coeff,
    get_thermal_opex_coeff,
)
from ..optim_model.constraints import thermal_unit_constr


class ThermalUnitBuilder(ComponentBuilder):
    """Builder class for thermal units. The formulation uses 3 binary variables to
    represent the startup, shutdown, and spinning reserve status of each unit.

    Variables
    ===========================
    - `pthermal`: Power output by a thermal unit (also called dispatch). Unit: MW.
    - `vpower`: Power output *ABOVE* the minimum capacity of a thermal unit. Unit: MW.
    - `vpowerbar`: Maximum power output *ABOVE* the minimum capacity of a thermal unit. Unit: MW.
    - `status`: Indicator of online status. On = 1 and off = 0. Unitless.
    - `startup`: Indicator if a unit is shutting down. Unitless.
    - `shutdown`: Indicator if a unit is starting up. Unitless.
    - `spin` (optional): Spinning reserve can be modeled with or without this variable. Unit: MW.

    Fixed objective terms
    ===========================
    - Fixed-cost per rated capacity
    - Startup cost per rated capacity

    Variable objective terms
    ===========================
    - Fuel cost

    Constraints
    ===========================
    - Logical constraints linking variables
    - Minimum up/down time constraints
    - Ramping constraints
    - Assume the start up/down rates are equal to the ramping rates

    """

    def __init__(self, model: gp.Model, inputs: SystemInput) -> None:
        super().__init__(model, inputs)
        self.thermal_units: list[str] = inputs.thermal_units

        self.thermal_rated_capacity: dict[str, float] = inputs.thermal_rated_capacity
        self.thermal_derated_capacity: pd.DataFrame = inputs.thermal_derated_capacity
        self.thermal_min_capacity: dict[str, float] = inputs.thermal_min_capacity

        # Variables
        self.pthermal = gp.tupledict()
        self.vpower = gp.tupledict()
        self.vpowerbar = gp.tupledict()

        self.status = gp.tupledict()
        self.startup = gp.tupledict()
        self.shutdown = gp.tupledict()

        self.spin = gp.tupledict()

        # Fixed objective terms in the objective function
        self.thermal_fixed_expr = gp.LinExpr()
        self.thermal_startup_expr = gp.LinExpr()

        # Time-dependent terms in the objective function
        self.thermal_opex_expr = gp.LinExpr()

        # Constraints
        self.c_link_uvw_init = gp.tupledict()
        self.c_link_uvw = gp.tupledict()
        self.c_link_pthermal = gp.tupledict()
        # self.c_link_pu_lower = gp.tupledict() # Redundant with c_link_pthermal
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

        # The following constraints are mutually exclusive
        self.c_link_spin = gp.tupledict()
        self.c_link_ppbar = gp.tupledict()

    def add_variables(self, step_k: int) -> None:
        """
        Add variables to the model.

        Args:
            step_k (int): The current simulation step.

        Returns:
            None
        """
        # Variables with time-dependent upper bounds
        var_with_variable_ub_list = ["pthermal", "vpower", "vpowerbar"]
        for varname in var_with_variable_ub_list:
            setattr(
                self,
                varname,
                add_var_with_variable_ub(
                    model=self.model,
                    varname=varname,
                    timesteps=self.timesteps,
                    step_k=step_k,
                    units=self.thermal_units,
                    capacity_df=self.thermal_derated_capacity,
                ),
            )

        # Binary variables
        var_binary_list = ["status", "startup", "shutdown"]
        for varname in var_binary_list:
            setattr(
                self,
                varname,
                self.model.addVars(
                    self.thermal_units,
                    self.timesteps,
                    vtype=gp.GRB.BINARY,
                    name=varname,
                ),
            )

        # Spinning reserve variable
        if self.inputs.use_spin_var:
            self.spin = self.model.addVars(
                self.thermal_units,
                self.timesteps,
                name="spin",
            )

    def get_fixed_objective_terms(self) -> gp.LinExpr:
        """
        Get the fixed objective terms for the thermal units. This includes
        the fixed cost per rated capacity and the startup cost per rated capacity.

        Returns:
            gp.LinExpr: The fixed objective terms.
        """
        thermal_fixed_coeffs = get_thermal_fixed_coeff(
            timesteps=self.timesteps,
            thermal_units=self.thermal_units,
            thermal_fixed_cost=self.inputs.thermal_fixed_cost,
            thermal_rated_capacity=self.thermal_rated_capacity,
        )
        thermal_startup_coeffs = get_thermal_startup_coeff(
            timesteps=self.timesteps,
            thermal_units=self.thermal_units,
            thermal_startup_cost=self.inputs.thermal_startup_cost,
            thermal_rated_capacity=self.thermal_rated_capacity,
        )

        # Create the expressions
        self.thermal_fixed_expr = self.status.prod(thermal_fixed_coeffs)
        self.thermal_startup_expr = self.startup.prod(thermal_startup_coeffs)

        return self.thermal_fixed_expr + self.thermal_startup_expr

    def get_variable_objective_terms(
        self,
        step_k: int,
    ) -> gp.LinExpr:
        """
        Get the time-dependent objective terms for the thermal units. This includes
        the OPEX cost.

        Args:
            step_k (int): The current simulation step.

        Returns:
            gp.LinExpr: The variable objective terms.
        """
        thermal_opex_coeffs = get_thermal_opex_coeff(
            step_k=step_k,
            timesteps=self.timesteps,
            thermal_units=self.thermal_units,
            thermal_opex=self.inputs.thermal_opex,
            fuel_contracts=self.inputs.fuel_contracts,
            contract_costs=self.inputs.contract_costs,
            thermal_heat_rate=self.inputs.thermal_heat_rate,
        )
        self.thermal_opex_expr = self.pthermal.prod(thermal_opex_coeffs)
        return self.thermal_opex_expr

    def add_constraints(self, step_k: int, init_conds: dict, **kwargs) -> None:
        """Add constraints to the model.

        Args:
            step_k (int): The current simulation step.
            init_conds (dict): Initial conditions for the variables.

        Returns:
            None
        """
        self.c_link_uvw_init = thermal_unit_constr.add_c_link_uvw_init(
            model=self.model,
            u=self.status,
            v=self.startup,
            w=self.shutdown,
            initial_u=init_conds["initial_u"],
            thermal_units=self.thermal_units,
        )
        self.c_link_uvw = thermal_unit_constr.add_c_link_uvw(
            model=self.model,
            u=self.status,
            v=self.startup,
            w=self.shutdown,
            sim_horizon=self.sim_horizon,
            thermal_units=self.thermal_units,
        )
        self.c_link_pthermal = thermal_unit_constr.add_c_link_pthermal(
            model=self.model,
            pthermal=self.pthermal,
            p=self.vpower,
            u=self.status,
            timesteps=self.timesteps,
            thermal_units=self.thermal_units,
            thermal_min_capacity=self.thermal_min_capacity,
        )

        # Redundant with c_link_pthermal
        # self.c_link_pu_lower = thermal_unit_constr.add_c_link_pu_lower(
        #     model=self.model,
        #     pthermal=self.pthermal,
        #     u=self.status,
        #     timesteps=self.timesteps,
        #     thermal_units=self.thermal_units,
        #     thermal_min_capacity=self.thermal_min_capacity,
        # )
        self.c_link_pu_upper = thermal_unit_constr.add_c_link_pu_upper(
            model=self.model,
            pbar=self.vpowerbar,
            u=self.status,
            timesteps=self.timesteps,
            step_k=step_k,
            thermal_units=self.thermal_units,
            thermal_min_capacity=self.thermal_min_capacity,
            thermal_derated_capacity=self.thermal_derated_capacity,
        )
        self.c_min_down_init = thermal_unit_constr.add_c_min_down_init(
            model=self.model,
            u=self.status,
            sim_horizon=self.sim_horizon,
            thermal_units=self.thermal_units,
            initial_min_off=init_conds["initial_min_off"],
        )
        self.c_min_up_init = thermal_unit_constr.add_c_min_up_init(
            model=self.model,
            u=self.status,
            sim_horizon=self.sim_horizon,
            thermal_units=self.thermal_units,
            initial_min_on=init_conds["initial_min_on"],
        )
        self.c_min_down = thermal_unit_constr.add_c_min_down(
            model=self.model,
            u=self.status,
            w=self.shutdown,
            sim_horizon=self.sim_horizon,
            thermal_units=self.thermal_units,
            TD=self.inputs.TD,
        )
        self.c_min_up = thermal_unit_constr.add_c_min_up(
            model=self.model,
            u=self.status,
            v=self.startup,
            sim_horizon=self.sim_horizon,
            thermal_units=self.thermal_units,
            TU=self.inputs.TU,
        )

        # Currently not implemented because we set SD = SU = ramping
        # self.c_peak_down_bound = thermal_unit_constr.add_c_peak_down_bound(
        #     model=self.model,
        #     p=self.vpower,
        #     spin=self.spin,
        #     u=self.status,
        #     v=self.startup,
        #     w=self.shutdown,
        #     sim_horizon=self.sim_horizon,
        #     step_k=step_k,
        #     thermal_units=self.thermal_units,
        #     thermal_min_capacity=self.thermal_min_capacity,
        #     thermal_derated_capacity=self.thermal_derated_capacity,
        #     SD=self.inputs.SD,
        #     SU=self.inputs.SU,
        #     TU=self.inputs.TU,
        # )

        # self.c_peak_up_bound = thermal_unit_constr.add_c_peak_up_bound(
        #     model=self.model,
        #     p=self.vpower,
        #     spin=self.spin,
        #     u=self.status,
        #     v=self.startup,
        #     w=self.shutdown,
        #     sim_horizon=self.sim_horizon,
        #     step_k=step_k,
        #     thermal_units=self.thermal_units,
        #     thermal_min_capacity=self.thermal_min_capacity,
        #     thermal_derated_capacity=self.thermal_derated_capacity,
        #     SD=self.inputs.SD,
        #     SU=self.inputs.SU,
        #     TU=self.inputs.TU,
        # )

        self.c_ramp_down_init = thermal_unit_constr.add_c_ramp_down_init(
            model=self.model,
            p=self.vpower,
            w=self.shutdown,
            thermal_units=self.thermal_units,
            initial_p=init_conds["initial_p"],
            initial_u=init_conds["initial_u"],
            thermal_min_capacity=self.thermal_min_capacity,
            RD=self.inputs.RD,
            SD=self.inputs.SD,
        )
        self.c_ramp_up_init = thermal_unit_constr.add_c_ramp_up_init(
            model=self.model,
            pbar=self.vpowerbar,
            u=self.status,
            v=self.startup,
            thermal_units=self.thermal_units,
            initial_p=init_conds["initial_p"],
            thermal_min_capacity=self.thermal_min_capacity,
            RU=self.inputs.RU,
            SU=self.inputs.SU,
        )
        self.c_ramp_down = thermal_unit_constr.add_c_ramp_down(
            model=self.model,
            p=self.vpower,
            u=self.status,
            w=self.shutdown,
            sim_horizon=self.sim_horizon,
            thermal_units=self.thermal_units,
            thermal_min_capacity=self.thermal_min_capacity,
            RD=self.inputs.RD,
            SD=self.inputs.SD,
        )
        self.c_ramp_up = thermal_unit_constr.add_c_ramp_up(
            model=self.model,
            p=self.vpower,
            pbar=self.vpowerbar,
            u=self.status,
            v=self.startup,
            sim_horizon=self.sim_horizon,
            thermal_units=self.thermal_units,
            thermal_min_capacity=self.thermal_min_capacity,
            RU=self.inputs.RU,
            SU=self.inputs.SU,
        )

        if self.inputs.use_spin_var:
            self.c_link_spin = thermal_unit_constr.add_c_link_spin(
                model=self.model,
                p=self.vpower,
                pbar=self.vpowerbar,
                spin=self.spin,
                timesteps=self.timesteps,
                thermal_units=self.thermal_units,
            )
        else:
            self.c_link_ppbar = thermal_unit_constr.add_c_link_ppbar(
                model=self.model,
                p=self.vpower,
                pbar=self.vpowerbar,
                timesteps=self.timesteps,
                thermal_units=self.thermal_units,
            )

    def update_variables(self, step_k: int) -> None:
        """Update variables with time-dependent upper bounds:
        - `pthermal`: Power output by a thermal unit
        - `vpower`: Thermal unit commitment status (on/off)
        - `vpowerbar`: Thermal unit start-up status

        Args:
            step_k (int): The current timestep.

        Returns:
            None
        """
        thermal_unit_vars = [
            self.pthermal,
            self.vpower,
            self.vpowerbar,
        ]
        for var_dict in thermal_unit_vars:
            update_var_with_variable_ub(var_dict, step_k, self.thermal_derated_capacity)

    def update_constraints(self, step_k: int, init_conds: dict, **kwargs) -> None:
        """Update time-dependent constraints:
        - c_link_uvw_init: initial_u is from the previous iteration
        - c_link_pu_upper: thermal_derated_capacity is a timeseries
        - c_min_down_init: initial_min_off is from the previous iteration
        - c_min_up_init: initial_min_on is from the previous iteration
        - c_ramp_down_init: initial vpower and u is from the previous iteration
        - c_ramp_up_init: initial vpower is from the previous iteration

        Args:
            step_k (int): The current timestep.
            init_conds (dict): Initial conditions for the variables.

        Returns:
            None
        """
        self.model.remove(self.c_link_uvw_init)
        self.c_link_uvw_init = thermal_unit_constr.add_c_link_uvw_init(
            model=self.model,
            u=self.status,
            v=self.startup,
            w=self.shutdown,
            initial_u=init_conds["initial_u"],
            thermal_units=self.thermal_units,
        )

        self.model.remove(self.c_link_pu_upper)
        self.c_link_pu_upper = thermal_unit_constr.add_c_link_pu_upper(
            model=self.model,
            pbar=self.vpowerbar,
            u=self.status,
            timesteps=self.timesteps,
            step_k=step_k,
            thermal_units=self.thermal_units,
            thermal_min_capacity=self.thermal_min_capacity,
            thermal_derated_capacity=self.thermal_derated_capacity,
        )

        self.model.remove(self.c_min_down_init)
        self.c_min_down_init = thermal_unit_constr.add_c_min_down_init(
            model=self.model,
            u=self.status,
            sim_horizon=self.sim_horizon,
            thermal_units=self.thermal_units,
            initial_min_off=init_conds["initial_min_off"],
        )

        self.model.remove(self.c_min_up_init)
        self.c_min_up_init = thermal_unit_constr.add_c_min_up_init(
            model=self.model,
            u=self.status,
            sim_horizon=self.sim_horizon,
            thermal_units=self.thermal_units,
            initial_min_on=init_conds["initial_min_on"],
        )

        self.model.remove(self.c_ramp_down_init)
        self.c_ramp_down_init = thermal_unit_constr.add_c_ramp_down_init(
            model=self.model,
            p=self.vpower,
            w=self.shutdown,
            thermal_units=self.thermal_units,
            initial_p=init_conds["initial_p"],
            initial_u=init_conds["initial_u"],
            thermal_min_capacity=self.thermal_min_capacity,
            RD=self.inputs.RD,
            SD=self.inputs.SD,
        )

        self.model.remove(self.c_ramp_up_init)
        self.c_ramp_up_init = thermal_unit_constr.add_c_ramp_up_init(
            model=self.model,
            pbar=self.vpowerbar,
            u=self.status,
            v=self.startup,
            thermal_units=self.thermal_units,
            initial_p=init_conds["initial_p"],
            thermal_min_capacity=self.thermal_min_capacity,
            RU=self.inputs.RU,
            SU=self.inputs.SU,
        )

    def get_variables(self) -> dict[str, gp.tupledict]:
        """Get the variables of the thermal unit.

        Returns:
            dict[str, gp.tupledict]: A dictionary of variables.
        """
        return {
            "pthermal": self.pthermal,
            "vpower": self.vpower,
            "vpowerbar": self.vpowerbar,
            "status": self.status,
            "startup": self.startup,
            "shutdown": self.shutdown,
        }
