""" This is test_model.py
"""

import os
import unittest
from unittest.mock import patch, MagicMock, call

import gurobipy as gp
import highspy
from pownet.model import PowerSystemModel


class TestPowerSystemModel(unittest.TestCase):
    def setUp(self):
        self.mock_gurobi_model = MagicMock(spec=gp.Model)
        self.mock_gurobi_instance = self.mock_gurobi_model.return_value

        self.mock_highs = MagicMock(spec=highspy.Highs)
        self.mock_highs_instance = self.mock_highs.return_value

        # Create an instance of the PowerSystemModel class
        self.psm = PowerSystemModel(self.mock_gurobi_model)

    @patch("pownet.model.os.path.exists")
    @patch("pownet.model.os.makedirs")
    def test_write_mps(self, mock_makedirs, mock_exists):
        output_folder = "test_output"
        filename = "test_model"
        expected_path = os.path.join(output_folder, f"{filename}.mps")
        # Assume the directory does not exist and create it
        mock_exists.return_value = False
        # Call the write_mps method
        self.psm.write_mps(output_folder, filename)
        # Check if the directory was created
        mock_makedirs.assert_called_once_with(output_folder)
        # Check if the model was written to the correct path
        self.mock_gurobi_model.write.assert_called_once_with(expected_path)

    def test_optimize_gurobi(self):
        self.psm.optimize(solver="gurobi")
        self.mock_gurobi_model.optimize.assert_called_once()

    def test_optimize_invalid_solver(self):
        with self.assertRaises(ValueError):
            self.psm.optimize(solver="invalid_solver")

    def test_check_feasible_gurobi(self):
        self.mock_gurobi_model.status = gp.GRB.Status.OPTIMAL
        self.assertTrue(self.psm.check_feasible())

    @patch("pownet.model.highspy.Highs")
    def test_check_feasible_highs(self, mock_highs):
        # Create a mock Highs instance
        mock_highs_instance = mock_highs.return_value
        mock_highs_instance.getModelStatus.return_value = (
            1  # Set return value for getModelStatus
        )
        # Ensure that modelStatusToString returns "Optimal" for the mocked status code
        mock_highs_instance.modelStatusToString.return_value = "Optimal"
        # Replace the current model with the mock Highs instance
        self.psm.model = mock_highs_instance
        self.psm.solver = "highs"
        # Assert the result of check_feasible()
        self.assertTrue(self.psm.check_feasible())

    # test writing ilp
    @patch("pownet.model.os.path.join")
    @patch("pownet.model.os.makedirs")
    def test_write_ilp_mps(self, mock_makedirs, mock_join):
        output_folder = "test_output"
        instance_name = "test_instance"
        self.psm.write_ilp_mps(output_folder, instance_name)
        calls = [
            call("test_output", "infeasible_test_instance.ilp"),
            call().replace(".ilp", ".mps"),
        ]
        mock_join.assert_has_calls(calls)

    def test_get_objval_gurobi(self):
        self.solver = "gurobi"
        self.mock_gurobi_model.objVal = 100
        self.assertEqual(self.psm.get_objval(), 100)


if __name__ == "__main__":
    unittest.main()
