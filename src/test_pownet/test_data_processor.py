""" This is test_data_processor.py
"""

import os
import unittest
from unittest.mock import patch, MagicMock
from pownet.data_processor import (
    DataProcessor,
)

from pownet.data_utils import get_dates
from pownet.folder_utils import get_database_dir, get_model_dir


class TestDataProcessor(unittest.TestCase):
    def test_initialization(self):
        # Arrange
        model_name = "test_model"
        year = 2024
        frequency = 50

        # Act
        processor = DataProcessor(model_name, year, frequency)

        # Assert
        self.assertEqual(processor.model_name, model_name)
        self.assertEqual(processor.year, year)
        self.assertEqual(processor.frequency, frequency)
        self.assertEqual(processor.wavelength, 6000)
        self.assertEqual(
            processor.model_folder,
            os.path.join(get_model_dir(), model_name),
        )
        # Timeseries should have 8760 rows
        self.assertEqual(processor.cycle_map, {})
        self.assertEqual(processor.thermal_derate_factors.shape[0], 8760)
        self.assertEqual(processor.marginal_costs.shape[0], 8760)


if __name__ == "__main__":
    unittest.main()
