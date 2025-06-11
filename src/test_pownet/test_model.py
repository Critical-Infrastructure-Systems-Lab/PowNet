"""This is test_model.py"""

import unittest

import gurobipy as gp
import pandas as pd
from pownet.optim_model import PowerSystemModel


class TestPowerSystemModel(unittest.TestCase):
    def setUp(self):
        """Create a simple optimization problem of two variables and a constraint
        min -x - 2y
        s.t. x + y >= 1
        x, y >= 0

        solution: x = 0, y = 1, objval = -2
        """
        self.gurobi_instance = gp.Model()
        x = self.gurobi_instance.addVar(name="x", lb=0)
        y = self.gurobi_instance.addVar(name="y", lb=0)
        self.gurobi_instance.setObjective(-x - 2 * y, gp.GRB.MINIMIZE)
        self.gurobi_instance.addConstr(x + y <= 1)
        self.gurobi_instance.update()
        self.psm = PowerSystemModel(self.gurobi_instance)

        self.infeasible_gurobi_instance = gp.Model()
        x = self.infeasible_gurobi_instance.addVar(name="x", lb=0)
        y = self.infeasible_gurobi_instance.addVar(name="y", lb=0)
        self.infeasible_gurobi_instance.setObjective(x + y, gp.GRB.MINIMIZE)
        self.infeasible_gurobi_instance.addConstr(x + y <= -1)
        self.infeasible_gurobi_instance.update()
        self.infeasible_psm = PowerSystemModel(self.infeasible_gurobi_instance)

        self.expected_solution = pd.DataFrame(
            {"varname": ["x", "y"], "value": [0.0, 1.0]}
        )

    def test_optimize_gurobi(self):
        self.psm.optimize(solver="gurobi", log_to_console=False)
        self.psm.check_feasible()
        self.assertEqual(self.psm.get_objval(), -2)

    def test_optimize_highs(self):
        self.psm.optimize(solver="highs", log_to_console=False)
        info = self.psm.model.getInfo()
        self.psm.check_feasible()
        self.assertEqual(info.objective_function_value, -2)

    def test_optimize_invalid_solver(self):
        with self.assertRaises(ValueError):
            self.psm.optimize(solver="invalid_solver")

    def test_check_infeasible_gurobi(self):
        self.infeasible_psm.optimize(solver="gurobi", log_to_console=False)
        self.assertFalse(self.infeasible_psm.check_feasible())

    def test_get_solution_gurobi(self):

        self.psm.optimize(solver="gurobi", log_to_console=False)
        pd.testing.assert_frame_equal(
            pd.DataFrame(self.psm.get_solution()), self.expected_solution
        )

    def test_get_solution_highs(self):
        self.psm.optimize(solver="highs", log_to_console=False)
        pd.testing.assert_frame_equal(
            pd.DataFrame(self.psm.get_solution()), self.expected_solution
        )


if __name__ == "__main__":
    unittest.main()
