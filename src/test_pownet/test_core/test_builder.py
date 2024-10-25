""" Unit tests for the ModelBuilder class.
"""

import os
import unittest
from pownet.core import ModelBuilder, SystemInput
from pownet.folder_utils import get_model_dir


class TestModelBuilder(unittest.TestCase):
    """Unless otherwise stated, use "dummy_trade" over 24-hr as the test case."""

    def setUp(self) -> None:
        # Load the test data
        self.inputs = SystemInput(
            input_folder=get_model_dir(),
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
