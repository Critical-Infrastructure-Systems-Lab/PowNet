""" timeseries_model.py: Abstract class for time series models."""

from abc import ABC, abstractmethod

import pandas as pd


class TimeSeriesModel(ABC):
    def __init__(
        self,
    ) -> None:
        self._is_fitted: bool = False
        self._is_loaded: bool = False

        # DataFrame to be loaded
        self.data: pd.DataFrame = pd.DataFrame()
        self.months: list = []  # Months are labeled from 1 to 12
        self.exog_vars: list[str] = None

    @property
    @abstractmethod
    def monthly_models(self) -> dict:
        pass

    @property
    @abstractmethod
    def predictions(self) -> pd.Series:
        pass

    @property
    @abstractmethod
    def pred_residuals(self) -> pd.Series:
        pass

    def load_data(self, data: pd.DataFrame) -> None:
        """Load the time series data"""
        # Check that there are columns called 'datetime' and 'value'
        if "datetime" not in data.columns:
            raise ValueError("Data should have columns 'datetime'")
        self.data = data
        # Convert 'datetime' column to datetime type
        self.data["datetime"] = pd.to_datetime(self.data["datetime"])
        self.months = self.data["datetime"].dt.month.unique().tolist()
        # Downstream code expects months to be sorted
        self.months.sort()
        # Time series modeling requires datetime to be the index
        self.data = self.data.set_index("datetime")
        self.data.index.freq = "h"  # Requires hourly time series
        self._is_loaded = True

    def fit(
        self,
        target_column: str,
        arima_order: tuple[int, int, int],
        seasonal_order: tuple[int, int, int, int] = None,
        exog_vars: list[str] = None,
    ) -> None:
        """Fit the model to the data

        Args:
            target_column (str): Target column to fit the model
            arima_order (tuple[int, int, int]): ARIMA order
            seasonal_order (tuple[int, int, int, int]): Seasonal order
            exog_vars (list[str], optional): List of exogenous variables. Defaults to None.
        """
        self._fit(
            target_column=target_column,
            arima_order=arima_order,
            seasonal_order=seasonal_order,
            exog_vars=exog_vars,
        )
        self._is_fitted = True
        self.exog_vars = exog_vars

    def predict(self) -> pd.Series:
        """Return the predictions"""
        if not self._is_fitted:
            raise ValueError("Model must be fitted before making predictions.")
        return self._predict()

    def get_synthetic(
        self,
        exog_data: pd.DataFrame = None,
        seed: int = None,
    ) -> pd.Series:
        """
        Create synthetic time series.

        Args:
            n_samples (int, optional): Number of samples to generate. Defaults to 1.
            exog_data (pd.DataFrame, optional): Exogenous variables. Defaults to None.
            seed (int, optional): Random seed. Defaults to None.

        Returns:
            pd.Series: Synthetic time series data.

        Raises:
            ValueError: If the model is not fitted.
            ValueError: If exogenous variables are not in the data.
            ValueError: If exogenous data index is not equal to the time series data index.
        """
        if not self._is_fitted:
            raise ValueError("Model must be fitted before creating synthetic data.")
        if exog_data is not None:
            if not all([var in exog_data.columns for var in self.exog_vars]):
                raise ValueError("Exogenous variables should be in the data.")
            if not exog_data.index.equals(self.data.index):
                raise ValueError(
                    "Exogenous data should have the same index as the time series data."
                )

        return self._get_synthetic(exog_data=exog_data, seed=seed)

    def find_best_model(
        self,
        target_column: str,
        exog_vars: list[str] = None,
        month_to_use: int = 1,
        seed: int = None,
        suppress_warnings: bool = False,
    ) -> tuple[tuple[int, int, int], tuple[int, int, int, int]]:
        """Find the best model for the time series data

        Args:
            target_column (str): Target column to fit the model
            exog_vars (list[str], optional): List of exogenous variables. Defaults to None.
            month_to_use (int, optional): Month to use for finding the best model. Defaults to 1.
            seed (int, optional): Random seed. Defaults to 112.
            suppress_warnings (bool, optional): Suppress warnings. Defaults to False.

        Returns:
            tuple[tuple[int, int, int], tuple[int, int, int, int]]: Best model SARIMA parameters

        Raises:
            ValueError: If data is not loaded
        """
        if not self._is_loaded:
            raise ValueError("Data must be loaded first.")
        return self._find_best_model(
            target_column=target_column,
            exog_vars=exog_vars,
            month_to_use=month_to_use,
            seed=seed,
            suppress_warnings=suppress_warnings,
        )

    @abstractmethod
    def _fit(
        self,
        target_column: str,
        arima_order: tuple[int, int, int],
        seasonal_order: tuple[int, int, int, int],
        exog_vars: list[str],
    ) -> None:
        pass

    @abstractmethod
    def _predict(self) -> pd.Series:
        pass

    @abstractmethod
    def _get_synthetic(self, exog_vars: list[str], seed: int) -> pd.Series:
        pass

    @abstractmethod
    def _find_best_model(
        self,
        target_column: str,
        exog_vars: list[str],
        month_to_use: int,
        seed: int,
        suppress_warnings: bool,
    ) -> tuple[tuple[int, int, int], tuple[int, int, int, int]]:
        pass
