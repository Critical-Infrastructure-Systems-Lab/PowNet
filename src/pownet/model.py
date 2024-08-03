"""
This script defines a class object that wraps around Gurobi Model class
to provide a more user-friendly interface while compatible with HiGHs solver.
"""

import os

import gurobipy as gp
import highspy

from pownet.folder_utils import get_output_dir


class PowerSystemModel:
    def __init__(self, model: gp.Model):
        self.model = model

    def add_var(self, name, lb, ub, vtype, obj):
        return self.model.addVar(lb=lb, ub=ub, vtype=vtype, obj=obj, name=name)

    def add_constr(self, lhs, sense, rhs, name):
        return self.model.addConstr(lhs, sense, rhs, name)

    def set_objective(self, obj):
        self.model.setObjective(obj)

    def write_mps(self, name: str):
        # Save the model
        dirname = os.path.join(get_output_dir(), f"{name}_instances")
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        self.model.write(os.path.join(dirname, f"{name}.mps"))

    def optimize(self):
        self.model.optimize()

    def check_feasible(self):
        if isinstance(self.model, gp.Model):
            return self.model.status == gp.GRB.Status.OPTIMAL
        elif isinstance(self.model, highspy.highs.Highs):
            model_status = self.model.getModelStatus()
            return self.model.modelStatusToString(model_status) == "Optimal"

    def write_ilp_mps(self, name):
        # Write the infeasible model to a file
        self.model.computeIIS()
        ilp_file = os.path.join(
            get_output_dir(),
            f"infeasible_{name}.ilp",
        )
        self.model.write(ilp_file)
        # Write the infeasible model to a MPS file
        self.model.write(ilp_file.replace(".ilp", ".mps"))

    def optimize_with_highs(self):
        # Export the instance to MPS and solve with HiGHs
        mps_file = "temp_instance_for_HiGHs.mps"
        self.model.write(mps_file)
        self.model = highspy.Highs()
        self.model.readModel(mps_file)
        self.model.run()
        # Delete the MPS file
        os.remove(mps_file)

    def get_objval(self) -> float:
        if isinstance(self.model, gp.Model):
            return self.model.objVal
        elif isinstance(self.model, highspy.highs.Highs):
            info = self.model.getInfo()
            return info.objective_function_value

    def get_status(self):
        if isinstance(self.model, gp.Model):
            return self.model.status
        elif isinstance(self.model, highspy.highs.Highs):
            return self.model.getModelStatus()

    def get_model(self):
        return self.model

    def get_solution(self) -> dict:
        if isinstance(self.model, gp.Model):
            return {
                "varname": self.model.getAttr("varname"),
                "value": self.model.getAttr("X"),
            }
        elif isinstance(self.model, highspy.highs.Highs):
            return {
                "varname": [
                    self.model.getColName(i)[1]
                    for i in range(self.model.getNumCol())  # getColName returns a tuple
                ],
                "value": self.model.getSolution().col_value,
            }

    def get_runtime(self) -> float:
        if isinstance(self.model, gp.Model):
            return self.model.Runtime
        elif isinstance(self.model, highspy.highs.Highs):
            return self.model.getRunTime()

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
