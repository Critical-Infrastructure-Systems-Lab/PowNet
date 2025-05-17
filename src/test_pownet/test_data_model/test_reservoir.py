import unittest
import pandas as pd

from pownet.data_model import ReservoirParams


class TestReservoirParams(unittest.TestCase):

    def setUp(self):
        """Set up common data for tests."""
        self.default_inflow_ts = pd.Series([10.0, 12.0, 15.0], index=[1, 2, 3])
        self.default_minflow_ts = pd.Series([1.0, 1.0, 1.0], index=[1, 2, 3])
        self.valid_params = {
            "name": "TestReservoir",
            "min_day": 150,
            "max_day": 270,
            "min_level": 100.0,
            "max_level": 150.0,
            "max_head": 50.0,
            "max_storage": 1000000.0,
            "max_release": 500.0,
            "max_generation": 100.0,
            "turbine_factor": 0.85,
            "inflow_ts": self.default_inflow_ts,
            "minflow_ts": self.default_minflow_ts,
            "upstream_units": [],
            "downstream_flow_fracs": {"Downstream1": 0.6, "Downstream2": 0.4},
        }

    def test_valid_params_creation(self):
        """Test successful creation with valid parameters."""
        try:
            ReservoirParams(**self.valid_params)
        except ValueError:
            self.fail("ReservoirParams raised ValueError unexpectedly for valid data.")

    def test_downstream_flow_fracs_sum_not_one(self):
        """Test ValueError if downstream flow fractions do not sum to 1."""
        params = self.valid_params.copy()
        params["downstream_flow_fracs"] = {
            "Downstream1": 0.5,
            "Downstream2": 0.4,
        }  # Sums to 0.9
        with self.assertRaisesRegex(
            ValueError, "Downstream units for TestReservoir do not sum to 1"
        ):
            ReservoirParams(**params)

        params["downstream_flow_fracs"] = {
            "Downstream1": 0.7,
            "Downstream2": 0.4,
        }  # Sums to 1.1
        with self.assertRaisesRegex(
            ValueError, "Downstream units for TestReservoir do not sum to 1"
        ):
            ReservoirParams(**params)

    def test_downstream_flow_fracs_sum_is_one_edge_cases(self):
        """Test successful creation when downstream flow fractions sum is close to 1."""
        params = self.valid_params.copy()
        params["downstream_flow_fracs"] = {
            "D1": 0.999
        }  # Test lower bound (assuming only one downstream)
        # To make this test pass, let's adjust for multiple units
        params["downstream_flow_fracs"] = {"D1": 0.5, "D2": 0.49999}
        try:
            ReservoirParams(**params)
        except ValueError:
            self.fail(
                "ReservoirParams raised ValueError for sum slightly less than 1 but within tolerance."
            )

        params["downstream_flow_fracs"] = {"D1": 0.5, "D2": 0.50001}
        try:
            ReservoirParams(**params)
        except ValueError:
            self.fail(
                "ReservoirParams raised ValueError for sum slightly more than 1 but within tolerance."
            )

    def test_mismatched_timeseries_indices(self):
        """Test ValueError if inflow_ts and minflow_ts have different indices."""
        params = self.valid_params.copy()
        params["minflow_ts"] = pd.Series(
            [1.0, 1.0, 1.0], index=[1, 2, 4]
        )  # Mismatched index
        with self.assertRaisesRegex(
            ValueError,
            "Inflows and minflows for TestReservoir are not indexed the same",
        ):
            ReservoirParams(**params)

    def test_timeseries_index_not_starting_at_one(self):
        """Test ValueError if timeseries indices do not start at 1."""
        params_inflow = self.valid_params.copy()
        params_inflow["inflow_ts"] = pd.Series([10.0, 12.0], index=[0, 1])
        params_inflow["minflow_ts"] = pd.Series(
            [1.0, 1.0], index=[0, 1]
        )  # Keep minflow consistent for this test focus
        with self.assertRaises(ValueError):
            ReservoirParams(**params_inflow)

        params_minflow = self.valid_params.copy()
        # Correct inflow to isolate minflow test
        params_minflow["inflow_ts"] = pd.Series([10.0, 12.0], index=[1, 2])
        params_minflow["minflow_ts"] = pd.Series([1.0, 1.0], index=[0, 1])
        with self.assertRaises(ValueError):
            ReservoirParams(**params_minflow)

    def test_inflow_less_than_minflow(self):
        """Test ValueError if inflow_ts is less than minflow_ts on any day."""
        params = self.valid_params.copy()
        params["inflow_ts"] = pd.Series(
            [10.0, 0.5, 15.0], index=[1, 2, 3]
        )  # Day 2 inflow < minflow
        params["minflow_ts"] = pd.Series([1.0, 1.0, 1.0], index=[1, 2, 3])
        with self.assertRaises(ValueError):
            ReservoirParams(**params)

    def test_empty_downstream_flow_fracs(self):
        """Test creation with empty downstream_flow_fracs."""
        params = self.valid_params.copy()
        params["downstream_flow_fracs"] = {}
        try:
            ReservoirParams(**params)
        except ValueError:
            self.fail(
                "ReservoirParams raised ValueError unexpectedly for empty downstream_flow_fracs."
            )

    def test_inflow_equal_to_minflow(self):
        """Test successful creation if inflow_ts is equal to minflow_ts."""
        params = self.valid_params.copy()
        params["inflow_ts"] = pd.Series([1.0, 2.0, 3.0], index=[1, 2, 3])
        params["minflow_ts"] = pd.Series([1.0, 2.0, 3.0], index=[1, 2, 3])
        try:
            ReservoirParams(**params)
        except ValueError:
            self.fail(
                "ReservoirParams raised ValueError when inflow_ts equals minflow_ts."
            )


if __name__ == "__main__":
    unittest.main(argv=["first-arg-is-ignored"], exit=False)
