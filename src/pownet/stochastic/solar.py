""" solar.py: Model for solar time series data"""

import numpy as np
import pandas as pd
from pmdarima import auto_arima
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.seasonal import STL, DecomposeResult

from .timeseries_model import TimeSeriesModel

import logging

logger = logging.getLogger(__name__)


def process_solar_series(solar_ts: pd.Series, suntimes: pd.DataFrame) -> pd.Series:
    # Remove negative values
    output_df = solar_ts.copy()

    # Convert sunrise and sunset to datetime
    suntimes["sunrise"] = pd.to_datetime(suntimes["sunrise"])
    suntimes["sunset"] = pd.to_datetime(suntimes["sunset"])

    output_df = output_df.to_frame().join(suntimes)
    output_df.loc[
        (output_df.index.hour < output_df["sunrise"].dt.hour)
        | (output_df.index.hour > output_df["sunset"].dt.hour),
        "value",
    ] = 0

    # Any negative value is zero
    output_df["value"] = np.maximum(output_df["value"], 0)
    # Drop sunrise and sunset columns
    output_df = output_df.drop(columns=["sunrise", "sunset"])

    # All negative values are set to zero
    output_df["value"] = np.maximum(output_df["value"], 0)
    return output_df


class SolarTSModel(TimeSeriesModel):
    def __init__(
        self,
    ) -> None:
        super().__init__()
        self._monthly_models: dict[int, SARIMAX] = {}
        self._predictions: pd.Series = pd.Series()
        self._pred_residuals: pd.Series = pd.Series()

        # Specific model parameters
        self.stl_seasonal_value = 24 * 7 - 1  # Must be an odd number
        self.stl_period_value = 24
        self.monthly_stl_results: dict[int, DecomposeResult] = {}

    @property
    def monthly_models(self) -> dict:
        if not self._is_fitted:
            raise ValueError("Model must be fitted first!")
        return self._monthly_models

    @property
    def predictions(self) -> pd.Series:
        if not self._is_fitted:
            raise ValueError("Model must be fitted first!")
        return self._predictions

    @property
    def pred_residuals(self) -> pd.Series:
        if not self._is_fitted:
            raise ValueError("Model must be fitted first!")
        return self._pred_residuals

    def _fit(
        self,
        target_column: str,
        arima_order: tuple[int, int, int],
        seasonal_order: tuple[int, int, int, int] = None,
        exog_vars: list[str] = None,
    ) -> None:
        # Check that self.data has sunrise and sunset columns
        if "sunrise" not in self.data.columns or "sunset" not in self.data.columns:
            raise ValueError("Data should have columns 'sunrise' and 'sunset'")

        self._pred_residuals = pd.Series()
        for month in self.months:
            logger.info(f"Fitting SARIMAX model for month {month}")
            monthly_y = self.data.loc[self.data.index.month == month, target_column]
            # We are interested in fitting a time series model to the
            # trend + residuals of the STL decomposition
            # The choice of seasonal argument is arbitrary to weekly patterns
            stl_model = STL(
                monthly_y,
                seasonal=self.stl_seasonal_value,
                period=self.stl_period_value,
            )
            stl_result = stl_model.fit()
            monthly_yt = monthly_y - stl_result.seasonal

            # SARIMAX
            exog_data = (
                self.data.loc[self.data.index.month == month, exog_vars]
                if exog_vars
                else None
            )
            sarimax_model = SARIMAX(
                monthly_yt,
                exog=exog_data,
                order=arima_order,
                seasonal_order=seasonal_order,
            ).fit(disp=True)

            # Store the models, and residuals
            self._monthly_models[month] = sarimax_model
            self.monthly_stl_results[month] = stl_result

            if self._pred_residuals.empty:
                self._pred_residuals = sarimax_model.resid
            else:
                self._pred_residuals = pd.concat(
                    [self._pred_residuals, sarimax_model.resid]
                )
        self._pred_residuals.name = "value"

    def _predict(self) -> pd.Series:
        self._predictions = pd.Series()
        for month in self.months:
            sarimax_model = self._monthly_models[month]
            # The SARIMAX model predicts yt, which is the trend and residuals of LOESS
            monthly_yt_pred = sarimax_model.predict()
            monthly_y_pred = monthly_yt_pred + self.monthly_stl_results[month].seasonal
            monthly_y_pred.name = "value"
            if self._predictions.empty:
                self._predictions = monthly_y_pred
            else:
                self._predictions = pd.concat([self._predictions, monthly_y_pred])

        # Post-processing involves removing negative values and
        # setting irradiance to zero during night hours
        suntimes = self.data.loc[:, ["sunrise", "sunset"]]
        self._predictions = process_solar_series(self._predictions, suntimes)

        return self._predictions

    def _get_synthetic(self, exog_data: pd.DataFrame, seed: int) -> pd.Series:
        synthetic_y = pd.Series()
        for month in self.months:
            sarimax_model = self._monthly_models[month]
            stl_result = self.monthly_stl_results[month]

            # Find the maximum number of days in the month
            max_day = self.data.loc[self.data.index.month == month].shape[0] // 24

            for day in range(1, max_day + 1):

                # Extract the start and end time for the day for indexing
                # the synthetic data
                start_time = self.data.loc[
                    (self.data.index.month == month) & (self.data.index.day == day)
                ].index[0]
                end_time = start_time + pd.Timedelta("23h")

                # This is the trend + residuals of the STL decomposition
                daily_exog_data = None
                if exog_data is not None:
                    daily_exog_data = exog_data.loc[start_time:end_time, :]

                daily_yt_syn = sarimax_model.simulate(
                    exog=daily_exog_data,
                    nsimulations=24,
                    anchor="end",
                    random_state=seed,
                )

                # Add the seasonal component from the STL decomposition to
                # get the synthetic data (irradiance)
                daily_y_syn = (
                    daily_yt_syn.values
                    + stl_result.seasonal.loc[start_time:end_time].values
                )
                daily_y_syn = pd.Series(
                    daily_y_syn,
                    name="value",
                    index=pd.date_range(start_time, end_time, freq="h"),
                )
                if synthetic_y.empty:
                    synthetic_y = daily_y_syn
                else:
                    synthetic_y = pd.concat([synthetic_y, daily_y_syn])

        # Post-processing involves removing negative values and
        # setting irradiance to zero during night hours
        suntimes = self.data.loc[:, ["sunrise", "sunset"]]
        synthetic_y = process_solar_series(synthetic_y, suntimes)
        return synthetic_y

    def _find_best_model(
        self,
        target_column: str,
        exog_vars: list[str],
        month_to_use: int,
        seed: int,
        suppress_warnings: bool,
    ) -> tuple[tuple[int, int, int], tuple[int, int, int, int]]:
        monthly_y = self.data.loc[self.data.index.month == month_to_use, target_column]
        monthly_exog = None
        if exog_vars:
            monthly_exog = self.data.loc[
                self.data.index.month == month_to_use, exog_vars
            ]

        # Find monthly_yt
        stl_model = STL(
            monthly_y,
            seasonal=self.stl_seasonal_value,
            period=self.stl_period_value,
        )
        stl_result = stl_model.fit()
        monthly_yt = monthly_y - stl_result.seasonal

        # Find the best model
        best_model = auto_arima(
            monthly_yt,
            X=monthly_exog,
            start_p=0,
            start_q=0,
            max_p=2,
            max_d=2,
            max_q=2,
            seasonal=False,
            information_criterion="aic",
            stepwise=True,
            suppress_warnings=suppress_warnings,
            error_action="warn",
            random_state=seed,
        )
        return best_model.order, best_model.seasonal_order
