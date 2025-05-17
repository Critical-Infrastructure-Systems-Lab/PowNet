"""test_timeseries_model.py"""

import unittest

# Skip this test if the user has not installed pmdarima package
try:
    import pmdarima
except ImportError:
    pmdarima = None
    raise unittest.SkipTest("pmdarima is not installed, skipping tests.")

import pandas as pd
from pownet.stochastic import timeseries_model


class ConcreteTimeSeriesModel(timeseries_model.TimeSeriesModel):
    """A concrete implementation for testing the abstract base class."""

    def __init__(self):
        super().__init__()
        self._predictions = pd.Series(dtype=float)
        self._residuals = pd.Series(dtype=float)
        self._monthly_models = {}

    @property
    def monthly_models(self) -> dict:
        return self._monthly_models

    @property
    def predictions(self) -> pd.Series:
        return self._predictions

    @property
    def pred_residuals(self) -> pd.Series:
        return self._residuals

    def _fit(
        self,
        target_column: str,
        arima_order: tuple[int, int, int],
        seasonal_order: tuple[int, int, int, int],
        exog_vars: list[str],
    ) -> None:
        # Minimal implementation for testing purposes
        # In a real scenario, this would fit some model
        self._monthly_models[1] = "dummy_model_for_month_1"
        pass

    def _predict(self) -> pd.Series:
        # Minimal implementation
        if not self.data.empty:
            return pd.Series(
                [1.0] * len(self.data), index=self.data.index, name="predictions"
            )
        return pd.Series(dtype=float)

    def _get_synthetic(
        self, exog_data: pd.DataFrame = None, seed: int = None
    ) -> pd.Series:
        # For this dummy, we'll keep the logic based on self.data, as it doesn't
        # actually use the exogenous variables for its dummy output.
        if not self.data.empty:
            return pd.Series(
                [0.5] * len(self.data), index=self.data.index, name="synthetic"
            )
        return pd.Series(dtype=float)

    def _find_best_model(
        self,
        target_column: str,
        exog_vars: list[str],
        month_to_use: int,
        seed: int,
        suppress_warnings: bool,
    ) -> tuple[tuple[int, int, int], tuple[int, int, int, int]]:
        # Minimal implementation
        return ((1, 0, 0), (0, 0, 0, 0))


class TestTimeSeriesModel(unittest.TestCase):

    def setUp(self):
        self.model = ConcreteTimeSeriesModel()
        self.sample_data = pd.DataFrame(
            {
                "datetime": pd.to_datetime(
                    [
                        "2023-01-01 00:00:00",
                        "2023-01-01 01:00:00",
                        "2023-01-01 02:00:00",  # Changed this line
                        "2023-01-01 03:00:00",  # Added an extra point for more data
                    ]
                ),
                "value": [10, 12, 15, 11],  # Adjusted values
                "exog1": [1, 2, 3, 4],  # Adjusted exog
            }
        )
        self.target_column = "value"

    def test_initialization(self):
        self.assertFalse(self.model._is_fitted)
        self.assertFalse(self.model._is_loaded)
        self.assertTrue(self.model.data.empty)
        self.assertEqual(self.model.months, [])
        self.assertIsNone(self.model.exog_vars)

    def test_load_data_success(self):
        self.model.load_data(self.sample_data.copy())
        self.assertTrue(self.model._is_loaded)
        self.assertFalse(self.model.data.empty)
        self.assertIn(pd.Timestamp("2023-01-01 00:00:00"), self.model.data.index)
        self.assertEqual(self.model.data.index.freqstr, "h")
        self.assertEqual(self.model.months, [1])  # Sorted
        self.assertIsInstance(self.model.data.index, pd.DatetimeIndex)

    def test_load_data_missing_datetime_column(self):
        bad_data = pd.DataFrame({"val": [1, 2]})
        with self.assertRaisesRegex(ValueError, "Data should have columns 'datetime'"):
            self.model.load_data(bad_data)

    def test_fit_success(self):
        self.model.load_data(self.sample_data.copy())
        self.model.fit(
            target_column=self.target_column, arima_order=(1, 0, 0), exog_vars=["exog1"]
        )
        self.assertTrue(self.model._is_fitted)
        self.assertEqual(self.model.exog_vars, ["exog1"])
        # You might also check if the dummy _fit method was "called" (e.g., by checking its side effects)
        self.assertIn(1, self.model.monthly_models)  # Based on dummy _fit

    def test_predict_not_fitted(self):
        with self.assertRaisesRegex(
            ValueError, "Model must be fitted before making predictions."
        ):
            self.model.predict()

    def test_predict_success(self):
        self.model.load_data(self.sample_data.copy())
        self.model.fit(target_column=self.target_column, arima_order=(1, 0, 0))
        predictions = self.model.predict()
        self.assertIsInstance(predictions, pd.Series)
        self.assertEqual(
            len(predictions), len(self.model.data)
        )  # Based on dummy _predict

    def test_get_synthetic_not_fitted(self):
        self.model.load_data(self.sample_data.copy())
        with self.assertRaisesRegex(
            ValueError, "Model must be fitted before creating synthetic data."
        ):
            self.model.get_synthetic()

    def test_get_synthetic_exog_vars_mismatch(self):
        self.model.load_data(self.sample_data.copy())
        self.model.fit(
            target_column=self.target_column,
            arima_order=(1, 0, 0),
            exog_vars=["exog_missing"],
        )
        exog_df = pd.DataFrame(
            {"exog_other": [1, 1, 1, 1]}, index=self.model.data.index
        )
        with self.assertRaisesRegex(
            ValueError, "Exogenous variables should be in the data."
        ):
            self.model.get_synthetic(exog_data=exog_df)

    def test_get_synthetic_exog_index_mismatch(self):
        self.model.load_data(self.sample_data.copy())
        self.model.fit(
            target_column=self.target_column, arima_order=(1, 0, 0), exog_vars=["exog1"]
        )
        wrong_index = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
        exog_df = pd.DataFrame(
            {"exog1": [1, 1, 1]}, index=wrong_index
        )  # Different index
        with self.assertRaisesRegex(
            ValueError,
            "Exogenous data should have the same index as the time series data.",
        ):
            self.model.get_synthetic(exog_data=exog_df)

    def test_get_synthetic_success(self):
        self.model.load_data(self.sample_data.copy())
        self.model.fit(target_column=self.target_column, arima_order=(1, 0, 0))
        synthetic_data = self.model.get_synthetic()
        self.assertIsInstance(synthetic_data, pd.Series)
        self.assertEqual(len(synthetic_data), len(self.model.data))

    def test_find_best_model_not_loaded(self):
        with self.assertRaisesRegex(ValueError, "Data must be loaded first."):
            self.model.find_best_model(target_column=self.target_column)

    def test_find_best_model_success(self):
        self.model.load_data(self.sample_data.copy())
        order, seasonal_order = self.model.find_best_model(
            target_column=self.target_column
        )
        self.assertEqual(order, (1, 0, 0))  # From dummy implementation
        self.assertEqual(seasonal_order, (0, 0, 0, 0))  # From dummy implementation


if __name__ == "__main__":
    unittest.main()
