"""Tests for the ModelBuilder class."""

import os
import unittest
from pownet import ModelBuilder, SystemInput
from pownet.folder_utils import get_pownet_dir

from pownet.builder.thermal import ThermalUnitBuilder
from pownet.builder.hydro import HydroUnitBuilder
from pownet.builder.nondispatch import NonDispatchUnitBuilder
from pownet.builder.energy_storage import EnergyStorageUnitBuilder
from pownet.builder.system import SystemBuilder


class TestModelBuilder(unittest.TestCase):
    """Unless otherwise stated, use "dummy_trade" over 24-hr as the test case."""

    def setUp(self) -> None:
        # Load the test data
        test_model_library_path = os.path.abspath(
            os.path.join(get_pownet_dir(), "model_library")
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
        self.assertIsInstance(self.model_builder.thermal_builder, ThermalUnitBuilder)
        self.assertIsInstance(self.model_builder.hydro_builder, HydroUnitBuilder)
        self.assertIsInstance(
            self.model_builder.nondispatch_builder, NonDispatchUnitBuilder
        )
        self.assertIsInstance(
            self.model_builder.storage_builder, EnergyStorageUnitBuilder
        )
        self.assertIsInstance(self.model_builder.system_builder, SystemBuilder)

    def test_build(self):
        pass


if __name__ == "__main__":
    unittest.main()
