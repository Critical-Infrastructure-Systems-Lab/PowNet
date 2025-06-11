"""test_data_processor.py"""

import os
import unittest
from pownet.core.data_processor import (
    DataProcessor,
)


class TestDataProcessor(unittest.TestCase):
    def test_initialization(self):
        # Arrange
        test_model_library_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "test_model_library")
        )
        model_name = "dummy"
        year = 2024
        frequency = 50

        # Act
        processor = DataProcessor(
            input_folder=test_model_library_path,
            model_name=model_name,
            year=year,
            frequency=frequency,
        )

        processor.execute_data_pipeline()

        # Assert
        self.assertEqual(processor.model_name, model_name)
        self.assertEqual(processor.year, year)
        self.assertEqual(processor.frequency, frequency)
        self.assertEqual(processor.wavelength, 6000)
        self.assertEqual(
            processor.model_folder,
            os.path.join(test_model_library_path, model_name),
        )
        # Timeseries should have 8760 rows
        self.assertEqual(processor.cycle_map, {})
        self.assertEqual(processor.thermal_derate_factors.shape[0], 8760)


if __name__ == "__main__":
    unittest.main()
