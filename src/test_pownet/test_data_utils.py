import unittest
import pandas as pd

from pownet.data_utils import calc_remaining_on_duration, calc_remaining_off_duration


class TestCalcMinOnlineDuration1(unittest.TestCase):

    def test_startup_within_horizon(self):
        """Test case where a unit has a startup within the simulation horizon.
        - Simulation horizon of 10 hours.
        - A minimum online duration (TU) of 3 hours
        - Latest start at hour 8.
        - The remaining minimum online duration is 0.
        """
        solution = pd.DataFrame(
            {
                "node": ["Unit1"] * 10 + ["Unit2"] * 10,
                "timestep": [x for x in range(1, 11)] + [x for x in range(1, 11)],
                "value": [0, 0, 0, 1, 1, 0, 0, 1, 0, 0]
                + [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                "vartype": ["startup"] * 10 + ["shutdown"] * 10,
            }
        )
        sim_horizon = 10
        thermal_units = ["Unit1"]
        TU = {"Unit1": 3}

        expected_output = {
            "Unit1": 0,
        }  # Unit1 started recently, Unit2 has some time left
        result = calc_remaining_on_duration(solution, sim_horizon, thermal_units, TU)
        self.assertEqual(result, expected_output)

    def test_startup_outside_horizon(self):
        """Test case where a unit has a startup within the simulation horizon.

        Unit1
        -------
        - A minimum online duration (TU) of 5 hours
        - Latest start at hour 8.
        - The remaining minimum online duration is 2.

        Unit2
        -------
        - A minimum online duration (TU) of 2 hours
        - Latest start at hour 10.
        - The remaining minimum online duration is 1.


        """
        solution = pd.DataFrame(
            {
                "node": ["Unit1"] * 10 + ["Unit2"] * 10,
                "timestep": [x for x in range(1, 11)] + [x for x in range(1, 11)],
                "value": [0, 0, 0, 1, 1, 0, 0, 1, 0, 0]
                + [0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
                "vartype": ["startup"] * 20,
            }
        )
        sim_horizon = 10
        thermal_units = ["Unit1", "Unit2"]
        TU = {"Unit1": 5, "Unit2": 2}

        expected_output = {
            "Unit1": 2,
            "Unit2": 1,
        }  # Unit1 started recently, Unit2 has some time left
        result = calc_remaining_on_duration(solution, sim_horizon, thermal_units, TU)
        self.assertEqual(result, expected_output)


class TestCalcMinOnlineDuration2(unittest.TestCase):

    def test_shutdown_within_horizon(self):
        """Test case where a unit has a shutdown within the simulation horizon.
        - Simulation horizon of 10 hours.
        - A minimum offline duration (TD) of 1 hours
        - Latest shutdown at hour 10.
        - The remaining minimum offline duration is 0.
        """
        solution = pd.DataFrame(
            {
                "node": ["Unit1"] * 10 + ["Unit2"] * 10,
                "timestep": [x for x in range(1, 11)] + [x for x in range(1, 11)],
                "value": [0, 0, 0, 1, 1, 0, 0, 1, 1, 1]
                + [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                "vartype": ["dummy_var"] * 10 + ["shutdown"] * 10,
            }
        )
        sim_horizon = 10
        thermal_units = ["Unit2"]  # Only test for Unit2
        TD = {"Unit2": 1}

        expected_output = {
            "Unit2": 0,
        }  # Unit1 started recently, Unit2 has some time left
        result = calc_remaining_off_duration(solution, sim_horizon, thermal_units, TD)
        self.assertEqual(result, expected_output)

    def test_shutdown_outside_horizon(self):
        """Test case where a unit has a shutdown within the simulation horizon.

        Unit1
        -------
        - A minimum offline duration (TD) of 5 hours
        - Latest shutdown at hour 6.
        - The remaining minimum offline duration is 0.

        Unit2
        -------
        - A minimum offline duration (TD) of 2 hours
        - Latest shutdown at hour 10.
        - The remaining minimum offline duration is 1.


        """
        solution = pd.DataFrame(
            {
                "node": ["Unit1"] * 10 + ["Unit2"] * 10,
                "timestep": [x for x in range(1, 11)] + [x for x in range(1, 11)],
                "value": [0, 0, 0, 0, 0, 1, 0, 0, 0, 0]
                + [0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
                "vartype": ["shutdown"] * 20,
            }
        )
        sim_horizon = 10
        thermal_units = ["Unit1", "Unit2"]
        TD = {"Unit1": 5, "Unit2": 2}

        expected_output = {
            "Unit1": 0,
            "Unit2": 1,
        }
        result = calc_remaining_off_duration(solution, sim_horizon, thermal_units, TD)
        self.assertEqual(result, expected_output)


if __name__ == "__main__":
    unittest.main()
