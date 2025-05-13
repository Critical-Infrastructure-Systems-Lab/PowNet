"""basebuilder.py: This module defines the abstract base class for component builders in the Pownet framework."""

from abc import ABC, abstractmethod

import gurobipy as gp

from ..input import SystemInput


class ComponentBuilder(ABC):
    """
    Abstract base class for component builders in the Pownet framework.

    This class defines the interface for building components, which includes methods for
    creating a model, adding variables, constraints, and objectives to the model.
    """

    def __init__(self, model: gp.Model, inputs: SystemInput):
        self.model = model
        self.inputs = inputs
        self.sim_horizon = inputs.sim_horizon
        self.timesteps = range(1, self.inputs.sim_horizon + 1)

    @abstractmethod
    def add_variables(self, step_k: int) -> None:
        pass

    @abstractmethod
    def get_fixed_objective_terms(self) -> gp.LinExpr:
        pass

    @abstractmethod
    def get_variable_objective_terms(self, step_k: int, **kwargs) -> gp.LinExpr:
        pass

    @abstractmethod
    def add_constraints(self, step_k: int, init_conds: dict, **kwargs) -> None:
        pass

    @abstractmethod
    def update_variables(self, step_k: int) -> None:
        pass

    @abstractmethod
    def update_constraints(self, step_k: int, init_conds: dict, **kwargs) -> None:
        pass

    @abstractmethod
    def get_variables(self) -> dict[str, gp.tupledict]:
        pass
