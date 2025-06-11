"""
model.py: PowerSystemModel is wrapper of gurobipy.Model and highspy.Highs
to provide a more user-friendly interface while compatible with HiGHs solver.
"""

import os

import gurobipy as gp
import highspy
import pandas as pd

from pownet.data_utils import (
    get_node_hour_from_flow_constraint,
    parse_lmp,
    parse_node_variables,
)

from .rounding_algo import optimize_with_rounding

import logging

logger = logging.getLogger(__name__)


class PowerSystemModel:
    def __init__(self, model: gp.Model):
        self.model = model
        self.solver: str = "gurobi"

        # Rounding related variables
        self.status_vars: gp.tupledict = None

        # Define dictionaries of functions for Gurobi and HiGHs
        self.optimize_functions = {
            "gurobi": self._optimize_gurobi,
            "highs": self._optimize_highs,
        }
        self.check_feasible_functions = {
            "gurobi": self._check_feasible_gurobi,
            "highs": self._check_feasible_highs,
        }
        self.get_objval_functions = {
            "gurobi": self._get_objval_gurobi,
            "highs": self._get_objval_highs,
        }
        self.get_status_functions = {
            "gurobi": self._get_status_gurobi,
            "highs": self._get_status_highs,
        }
        self.get_solution_functions = {
            "gurobi": self.get_solution_gurobi,
            "highs": self.get_solution_highs,
        }
        self.get_runtime_functions = {
            "gurobi": self.get_runtime_gurobi,
            "highs": self.get_runtime_highs,
        }
        self.solve_for_lmp_functions = {
            "gurobi": self.solve_for_lmp_gurobi,
            "highs": self.solve_for_lmp_highs,
        }

        self.rounding_optimization_time: float = None
        self.rounding_iterations: int = None

    def write_mps(self, output_folder: str, filename: str):
        if not isinstance(self.model, gp.Model):
            raise ValueError("The model must be a Gurobi model")
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
        self.model.write(os.path.join(output_folder, f"{filename}.mps"))

    def _optimize_gurobi(
        self,
        log_to_console: bool,
        mipgap: float,
        timelimit: int,
        num_threads: int,
    ):

        self.model.Params.LogToConsole = log_to_console
        self.model.Params.MIPGap = mipgap
        self.model.Params.TimeLimit = timelimit
        self.model.Params.Threads = num_threads

        self.model.optimize()

    def _optimize_highs(
        self, log_to_console: bool, mipgap: float, timelimit: int, num_threads: int
    ):
        # Export the instance to MPS and solve with HiGHs
        mps_file = "temp_instance_for_HiGHs.mps"
        self.model.write(mps_file)
        self.model = highspy.Highs()
        self.model.readModel(mps_file)

        self.model.setOptionValue("log_to_console", log_to_console)
        self.model.setOptionValue("mip_rel_gap", mipgap)
        self.model.setOptionValue("time_limit", timelimit)
        self.model.setOptionValue("threads", num_threads)

        # Must faster than automatic selection
        self.model.setOptionValue("solver", "simplex")

        self.model.run()
        # Delete the MPS file
        os.remove(mps_file)

    def optimize(
        self,
        solver: str = "gurobi",
        log_to_console: bool = True,
        mipgap: float = 1e-3,
        timelimit: int = 600,
        num_threads: int = 0,
    ):
        if solver not in ["gurobi", "highs"]:
            raise ValueError("The solver must be either 'gurobi' or 'highs'")

        # Update the solver attribute for referencing in other methods
        self.solver = solver
        self.optimize_functions[self.solver](
            log_to_console=log_to_console,
            mipgap=mipgap,
            timelimit=timelimit,
            num_threads=num_threads,
        )

    def optimize_with_rounding(
        self,
        rounding_strategy: str,
        max_rounding_iter: int,
        threshold: float = 0,
        mipgap: float = 1e-3,
        timelimit: int = 600,
        num_threads: int = 0,
        log_to_console: bool = False,
    ) -> None:
        self.model, self.rounding_optimization_time, self.rounding_iterations = (
            optimize_with_rounding(
                model=self.model,
                rounding_strategy=rounding_strategy,
                threshold=threshold,
                max_rounding_iter=max_rounding_iter,
                log_to_console=log_to_console,
                mipgap=mipgap,
                timelimit=timelimit,
                num_threads=num_threads,
            )
        )

    def _check_feasible_gurobi(self) -> bool:
        not_allowed_statuses = [
            gp.GRB.Status.INFEASIBLE,
            gp.GRB.Status.INF_OR_UNBD,
            gp.GRB.Status.UNBOUNDED,
        ]
        return self.model.status not in not_allowed_statuses

    def _check_feasible_highs(self) -> bool:
        model_status = self.model.getModelStatus()
        return self.model.modelStatusToString(model_status) == "Optimal"

    def check_feasible(self) -> bool:
        return self.check_feasible_functions[self.solver]()

    def write_ilp_mps(self, output_folder: str, instance_name: str):
        # Write the infeasible model to a file
        self.model.computeIIS()
        ilp_file = os.path.join(
            output_folder,
            f"infeasible_{instance_name}.ilp",
        )
        self.model.write(ilp_file)
        # Write the infeasible model to a MPS file
        self.model.write(ilp_file.replace(".ilp", ".mps"))

    def _get_objval_gurobi(self) -> float:
        return self.model.objVal

    def _get_objval_highs(self) -> float:
        info = self.model.getInfo()
        return info.objective_function_value

    def get_objval(self) -> float:
        return self.get_objval_functions[self.solver]()

    def _get_status_gurobi(self):
        return self.model.status

    def _get_status_highs(self):
        return self.model.getModelStatus()

    def get_status(self):
        return self.get_status_functions[self.solver]()

    def get_model(self):
        return self.model

    def get_solution_gurobi(self) -> dict:
        return {
            "varname": self.model.getAttr("varname"),
            "value": self.model.getAttr("X"),
        }

    def get_solution_highs(self) -> dict:
        return {
            "varname": [
                self.model.getColName(i)[1]
                for i in range(self.model.getNumCol())  # getColName returns a tuple
            ],
            "value": self.model.getSolution().col_value,
        }

    def get_solution(self) -> pd.DataFrame:
        return pd.DataFrame(self.get_solution_functions[self.solver]())

    def get_runtime_gurobi(self) -> float:
        return self.model.Runtime

    def get_runtime_highs(self) -> float:
        return self.model.getRunTime()

    def get_runtime(self) -> float:
        return self.get_runtime_functions[self.solver]()

    def solve_for_lmp_gurobi(self) -> dict:
        """Return the locational marginal price (LMP).

        Args:
            model: The Gurobi model.

        Returns:
            The LMP at each node.
        """
        # Fix the binary variables
        model_fixed = self.model.fixed()
        # Reoptimize as linear program, which is already obtained by fixing the binary variables
        model_fixed.optimize()
        # Get the dual variables
        pi = model_fixed.getAttr("Pi", model_fixed.getConstrs())
        # Filter to only constraints that are nodal balance, which has 'flowBal' in the name
        nodal_price = {
            constr.ConstrName: pi[i]
            for i, constr in enumerate(model_fixed.getConstrs())
            if "flowBal" in constr.ConstrName
        }
        return nodal_price

    def solve_for_lmp_highs(self) -> dict:
        raise NotImplementedError("This method is not implemented for HiGHs solver")

    def solve_for_lmp(self) -> dict:
        return self.solve_for_lmp_functions[self.solver]()

    def solve_for_export_capacity(
        self, shared_nodes: list, sim_horizon: int, step_k: int
    ) -> tuple:
        """Return the export capacity and hourly prices at the shared nodes"""
        # Fix binary variables to simulate fixing unit commitments
        model_fixed = self.model.fixed()

        # Add export variables to the model with a negative coefficient (minimization problem)
        # The value should be high enough to incentivize export but not high enough to create shortfall
        export_vars = model_fixed.addVars(
            shared_nodes,
            range(1, sim_horizon + 1),
            vtype=gp.GRB.CONTINUOUS,
            obj=-1,  # A small negative value should urge the model to export
            name="export",
        )

        # Add export variables to the flow balance at the shared nodes
        for constr in model_fixed.getConstrs():
            node, t = get_node_hour_from_flow_constraint(constr.ConstrName)
            if (node is not None) and (node in shared_nodes):
                model_fixed.chgCoeff(
                    constr,
                    export_vars[(node, t)],
                    -1,  # This will add the export variable to the demand on the RHS
                )
        model_fixed.optimize()

        # Extract the export capacity
        export_capacity = pd.DataFrame(
            {
                "varname": [v.varname for v in export_vars.values()],
                "value": [v.x for v in export_vars.values()],
            }
        )

        # Format the dataframe with additional columns
        export_capacity = parse_node_variables(export_capacity, sim_horizon, step_k)

        return export_capacity.pivot(index="hour", columns="node", values="value")

    def solve_for_export_prices(
        self, shared_nodes: list, sim_horizon: int, step_k: int
    ) -> pd.DataFrame:
        """The export prices are locational marginal prices at the shared nodes."""
        export_prices = parse_lmp(
            lmp=self.solve_for_lmp(),
            sim_horizon=sim_horizon,
            step_k=step_k,
        )
        export_prices = export_prices[export_prices["node"].isin(shared_nodes)]
        return export_prices.pivot(index="hour", columns="node", values="value")

    def print_added_constraints(self):
        added_constrs = set()
        for attr_name in self.model.getConstrs():
            constr_type = attr_name.ConstrName.split("[")[0]
            added_constrs.add(constr_type)

        # Sort the constraints for better readability
        added_constrs = sorted(list(added_constrs))

        log_message = "\nAdded constraints:\n"
        log_message += "\n".join(added_constrs)
        logger.warning(log_message)
