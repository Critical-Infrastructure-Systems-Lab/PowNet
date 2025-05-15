"""Unit tests for the ModelBuilder class."""

import os
import unittest
from pownet import ModelBuilder, SystemInput


class TestModelBuilder(unittest.TestCase):
    """Unless otherwise stated, use "dummy_trade" over 24-hr as the test case."""

    def setUp(self) -> None:
        # Load the test data
        test_model_library_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "test_model_library")
        )

        self.inputs = SystemInput(
            input_folder=test_model_library_path,
            model_name="dummy",
            year=2016,
            sim_horizon=24,
        )
        self.inputs.load_data()
        self.inputs.check_data()
        # Create a model builder object
        self.model_builder = ModelBuilder(self.inputs)

    def test_init(self):
        self.assertEqual(
            self.model_builder.timesteps, range(1, self.inputs.sim_horizon + 1)
        )


if __name__ == "__main__":
    unittest.main()
