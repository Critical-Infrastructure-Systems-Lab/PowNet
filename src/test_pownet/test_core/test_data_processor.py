""" This is test_data_processor.py
"""

import os
import unittest
from pownet.core.data_processor import (
    DataProcessor,
)

from pownet.folder_utils import get_model_dir


class TestDataProcessor(unittest.TestCase):
    def test_initialization(self):
        # Arrange
        input_folder = os.getcwd()
        print(input_folder)
        model_name = "test_model"
        year = 2024
        frequency = 50

        # Act
        processor = DataProcessor(
            input_folder=input_folder,
            model_name=model_name,
            year=year,
            frequency=frequency,
        )

        # Assert
        self.assertEqual(processor.model_name, model_name)
        self.assertEqual(processor.year, year)
        self.assertEqual(processor.frequency, frequency)
        self.assertEqual(processor.wavelength, 6000)
        self.assertEqual(
            processor.model_folder,
            os.path.join(get_model_dir(), input_folder, model_name),
        )
        # Timeseries should have 8760 rows
        self.assertEqual(processor.cycle_map, {})
        self.assertEqual(processor.thermal_derate_factors.shape[0], 8760)
        self.assertEqual(processor.marginal_costs.shape[0], 8760)


if __name__ == "__main__":
    unittest.main()
