from typing import Callable, Any
import gurobipy as gp


class UserConstraint:
    def __init__(
        self,
        model: gp.Model,
    ):
        self.model = model

        # Constraints that do not need to be updated with each iteration
        self.constraints: dict[tuple] = {}  # list of functions and its arguments
        self.constrs_with_update: dict[str] = {}
        self.added_constraints: gp.tupledict = gp.tupledict()

    def register_constraint(
        self,
        constraint: Callable[..., Any],
        constr_name: str,
        **kwargs: Any,
    ):
        self.constraints[constr_name] = (constraint, kwargs)

    def register_constraint_with_update(
        self,
        constraint: Callable[..., Any],
        constr_name: str,
        **kwargs: Any,
    ):
        # Remove step_k from kwargs
        del kwargs["step_k"]
        self.constrs_with_update[constr_name] = (constraint, kwargs)

    def add_constraints_to_model(self, step_k: int = 1):
        # Constraints without update
        for constr_name, (constraint, kwargs) in self.constraints.items():
            self.added_constraints[constr_name] = constraint(
                self.model, constr_name=constr_name, **kwargs
            )
        # Constraints with update
        for constr_name, (constraint, kwargs) in self.constrs_with_update.items():
            self.added_constraints[constr_name] = constraint(
                self.model, step_k=step_k, constr_name=constr_name, **kwargs
            )

        self.model.update()

    def remove_constraints(self, constr_names: str):
        for constr_name in constr_names:
            self.model.remove(self.added_constraints[constr_name])
        self.model.update()

    def update_constraints(self, step_k: int):
        # Remove constraints
        for constr_name in self.constrs_with_update.keys():
            self.model.remove(self.added_constraints[constr_name])
        # Add constraints
        for constr_name, (constraint, kwargs) in self.constrs_with_update.items():
            self.added_constraints[constr_name] = constraint(
                self.model, step_k=step_k, constr_name=constr_name, **kwargs
            )

        self.model.update()
