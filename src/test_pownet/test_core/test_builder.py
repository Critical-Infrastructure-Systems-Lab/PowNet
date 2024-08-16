""" Unit tests for the ModelBuilder class.
"""

import unittest
from unittest.mock import MagicMock, patch

import gurobipy as gp

from pownet.folder_utils import get_output_dir, get_model_dir
from pownet.model import PowerSystemModel
from pownet.core import ModelBuilder, SystemInput


class TestModelBuilder(unittest.TestCase):
    """Unless otherwise stated, use "dummy_trade" over 24-hr as the test case."""

    def setUp(self) -> None:
        # Load the test data
        self.inputs = SystemInput(
            model_name="dummy_trade",
            year=2016,
            sim_horizon=24,
        )
        self.T: int = self.inputs.sim_horizon
        self.inputs.load_data()
        self.inputs.check_data()
        # Create a model builder object
        self.model_builder = ModelBuilder(self.inputs)

    def test_init(self):
        self.assertEqual(self.model_builder.T, self.inputs.sim_horizon)
        self.assertIsNotNone(self.model_builder.model)

    def test_add_var_pthermal(self):
        """Test the add_var_dispatch method."""
        model = gp.Model("dummy")

        def check_pthermal(step_k):
            pthermal = self.model_builder._add_var_pthermal(model=model, step_k=step_k)
            model.update()

            # Variables are created for each thermal unit and timestep
            expected_keys = {
                (unit, t)
                for unit in self.inputs.thermal_units
                for t in range(1, self.T + 1)
            }
            self.assertEqual(set(pthermal.keys()), expected_keys)

            # Upper bounds are set to the rated capacity of the thermal units
            for unit, t in expected_keys:
                self.assertEqual(
                    pthermal[(unit, t)].UB,
                    self.inputs.thermal_derated_capacity.loc[
                        t + (step_k - 1) * self.T, unit
                    ],
                )

        check_pthermal(step_k=1)
        check_pthermal(step_k=2)

    def test_add_var_phydro(self):
        """Test the add_var_phydro method."""
        model = gp.Model("dummy")

        def check_phydro(model: gp.Model, step_k: int):
            phydro = self.model_builder._add_var_phydro(model=model, step_k=step_k)
            model.update()

            # Variables are created for each hydro unit and timestep
            expected_keys = {
                (unit, t)
                for unit in self.inputs.hydro_units
                for t in range(1, self.T + 1)
            }
            self.assertEqual(set(phydro.keys()), expected_keys)

            # Upper bounds are set to the rated capacity of the hydro units
            for unit, t in expected_keys:
                self.assertEqual(
                    phydro[(unit, t)].UB,
                    self.inputs.hydro_capacity.loc[
                        t + (step_k - 1) * self.T, unit
                    ].iloc[0],
                )

        check_phydro(model, step_k=1)
        check_phydro(model, step_k=2)

    def test_get_thermal_fixed_coeffs(self):
        inputs = SystemInput(model_name="dummy_trade", year=2016, sim_horizon=24)
        inputs.load_data()

        inputs.thermal_rated_capacity = {"unit1": 100, "unit2": 200}
        inputs.thermal_fixed_cost = {"unit1": 50, "unit2": 60}
        inputs.thermal_units = ["unit1", "unit2"]
        inputs.sim_horizon = 24

        model_builder = ModelBuilder(inputs)
        model_builder.timesteps = [1, 2, 3]

        # Call the method under test
        thermal_fixed_coeffs = model_builder._get_thermal_fixed_coeffs()

        expected_coeffs = {
            ("unit1", 1): 100 * 50,
            ("unit1", 2): 100 * 50,
            ("unit1", 3): 100 * 50,
            ("unit2", 1): 200 * 60,
            ("unit2", 2): 200 * 60,
            ("unit2", 3): 200 * 60,
        }
        self.assertEqual(thermal_fixed_coeffs, expected_coeffs)

    def test_get_thermal_opex_coeffs(self):
        """Test the _get_thermal_opex_coeffs method."""
        # Set up some sample data for the inputs
        model_builder = ModelBuilder(self.inputs)
        model_builder.inputs.thermal_fuel_cost = {"unit1": 2.0, "unit2": 3.0}
        model_builder.inputs.thermal_heat_rate = {"unit1": 10.0, "unit2": 8.0}
        model_builder.inputs.thermal_opex = {"unit1": 5.0, "unit2": 10.0}
        model_builder.inputs.thermal_units = ["unit1", "unit2"]

        model_builder.timesteps = [0, 1, 2]  # Simulate some timesteps

        # Call the method under test
        thermal_opex_coeffs = model_builder._get_thermal_opex_coeffs()

        # Assert the expected results
        expected_coeffs = {
            ("unit1", 0): (2.0 * 10.0) + 5.0,  # (fuel_cost * heat_rate) + opex
            ("unit1", 1): (2.0 * 10.0) + 5.0,
            ("unit1", 2): (2.0 * 10.0) + 5.0,
            ("unit2", 0): (3.0 * 8.0) + 10.0,
            ("unit2", 1): (3.0 * 8.0) + 10.0,
            ("unit2", 2): (3.0 * 8.0) + 10.0,
        }
        self.assertEqual(thermal_opex_coeffs, expected_coeffs)

    def test_get_thermal_startup_coeffs(self):
        """Test the _get_thermal_startup_coeffs method."""

        # Set up sample data for the inputs
        model_builder = ModelBuilder(self.inputs)
        model_builder.inputs.thermal_rated_capacity = {"unit1": 100, "unit2": 200}
        model_builder.inputs.thermal_startup_cost = {
            "unit1": 30,
            "unit2": 40,
        }  # New input
        model_builder.inputs.thermal_units = ["unit1", "unit2"]

        model_builder.timesteps = [0, 1, 2]

        # Call the method under test
        thermal_startup_coeffs = model_builder._get_thermal_startup_coeffs()

        # Assert the expected results
        expected_coeffs = {
            ("unit1", 0): 100 * 30,  # (rated_capacity * startup_cost)
            ("unit1", 1): 100 * 30,
            ("unit1", 2): 100 * 30,
            ("unit2", 0): 200 * 40,
            ("unit2", 1): 200 * 40,
            ("unit2", 2): 200 * 40,
        }
        self.assertEqual(thermal_startup_coeffs, expected_coeffs)

    def test_add_var_phydro(self):
        """Test the _add_var_phydro method."""
        model = gp.Model("dummy")

        def check_phydro(model: gp.Model, step_k: int):
            phydro = self.model_builder._add_var_phydro(model=model, step_k=step_k)
            model.update()

            # Variables are created for each hydro unit and timestep
            expected_keys = {
                (unit, t)
                for unit in self.inputs.hydro_units
                for t in range(1, self.T + 1)
            }
            self.assertEqual(set(phydro.keys()), expected_keys)

            # Upper bounds are set to the rated capacity of the hydro units
            for unit, t in expected_keys:
                self.assertEqual(
                    phydro[(unit, t)].UB,
                    self.inputs.hydro_capacity.loc[
                        t + (step_k - 1) * self.T, unit
                    ].iloc[0],
                )

        check_phydro(model, step_k=1)
        check_phydro(model, step_k=2)

    def test_add_var_flow(self):
        """Test the _add_var_flow method."""
        model = gp.Model("dummy")

        def check_flow(model: gp.Model, step_k: int):
            flow = self.model_builder._add_var_flow(model=model, step_k=step_k)
            model.update()

            # Variables are created for each line and timestep
            expected_keys = {
                (edge[0], edge[1], t)
                for edge in self.inputs.edges
                for t in range(1, self.T + 1)
            }
            self.assertEqual(len(set(flow.keys())), len(expected_keys))

            # Upper bounds are set to the rated capacity of the lines
            for a, b, t in expected_keys:
                self.assertEqual(
                    flow[a, b, t].LB,
                    -1
                    * self.inputs.line_capacity_factor
                    * self.inputs.line_capacity.loc[t + (step_k - 1) * self.T, (a, b)],
                )
                self.assertEqual(
                    flow[a, b, t].UB,
                    self.inputs.line_capacity_factor
                    * self.inputs.line_capacity.loc[t + (step_k - 1) * self.T, (a, b)],
                )

        check_flow(model, step_k=1)
        check_flow(model, step_k=2)

    # def test_unit_status_continuity(self):
    #     pass

    # def test_min_up_time(self):
    #     pass

    # def test_min_down_time(self):
    #     pass


if __name__ == "__main__":
    unittest.main()
