"""
model.py: PowerSystemModel is wrapper of gurobipy.Model and highspy.Highs
to provide a more user-friendly interface while compatible with HiGHs solver.
"""

import os

import gurobipy as gp
import highspy
import pandas as pd

from pownet.folder_utils import get_output_dir


class PowerSystemModel:
    def __init__(self, model: gp.Model):
        self.model = model
        self.solver: str = "gurobi"

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

    def _check_feasible_gurobi(self) -> bool:
        return self.model.status == gp.GRB.Status.OPTIMAL

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

    def get_lmp(self) -> dict:
        """Get the locational marginal price (LMP) for each node in the network"""
        # Fix the binary variables
        self.model = self.model.fixed()
        # Reoptimize as linear program
        self.model = self.model.relax()
        self.model.optimize()
        # Get the dual variables
        pi = self.model.getAttr("Pi", self.model.getConstrs())
        # Filter to only constraints that are nodal balance, which has 'flowBal' in the name
        nodal_price = {
            constr.ConstrName: pi[i]
            for i, constr in enumerate(self.model.getConstrs())
            if "flowBal" in constr.ConstrName
        }
        return nodal_price
