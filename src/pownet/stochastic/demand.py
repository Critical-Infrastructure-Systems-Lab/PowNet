""" demand.py: Model for solar time series data"""

import numpy as np
import pandas as pd
from pmdarima import auto_arima
from statsmodels.regression.linear_model import OLS
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.seasonal import STL, DecomposeResult

from .timeseries_model import TimeSeriesModel

import logging

logger = logging.getLogger(__name__)


class DemandTSModel(TimeSeriesModel):
    def __init__(
        self,
    ) -> None:
        super().__init__()
        self._monthly_models: dict[int, SARIMAX] = {}
        self._predictions: pd.Series = pd.Series()
        self._pred_residuals: pd.Series = pd.Series()

        # Specific model parameters
        self.monthly_reg_models: dict[int, OLS] = {}
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
        exog_vars: list[str],
        arima_order: tuple[int, int, int],
        seasonal_order: tuple[int, int, int, int] = None,
    ) -> None:
        """Steps include
        1) Fit a regression to get yt
        2) Fit an STL to the regression residuals to get ytt
        3) Fit a SARIMAX model to ytt

        Note that the user must at lease use temperature as a predictor
        """
        self._pred_residuals = pd.Series()
        for month in self.months:
            logger.info(f"Fitting SARIMAX model for month {month}")
            # Subset the data for the month
            monthly_y = self.data.loc[self.data.index.month == month, target_column]
            monthly_exog = self.data.loc[
                self.data.index.month == month, exog_vars
            ].astype(float)

            # Regression model
            reg_model = OLS(monthly_y, monthly_exog).fit()
            monthly_yt = reg_model.resid

            # STL model
            stl_model = STL(
                monthly_yt,
                seasonal=self.stl_seasonal_value,
                period=self.stl_period_value,
            )
            stl_result = stl_model.fit()

            # SARIMAX model
            monthly_ytt = monthly_yt - stl_result.seasonal - stl_result.trend
            sarimax_model = SARIMAX(
                monthly_ytt,
                order=arima_order,
                seasonal_order=seasonal_order,
            ).fit(disp=True)

            # Store the models, and residuals
            self.monthly_reg_models[month] = reg_model
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
            monthly_exog = self.data.loc[
                self.data.index.month == month, self.exog_vars
            ].astype(float)
            sarimax_model = self._monthly_models[month]
            # SARIMAX model ytt, which is the trend and residuals of LOESS
            monthly_ytt_pred = sarimax_model.predict()
            monthly_yt_pred = (
                monthly_ytt_pred + self.monthly_stl_results[month].seasonal
            )

            # Regression model to get y
            reg_pred = self.monthly_reg_models[month].predict(monthly_exog)
            monthly_y_pred = monthly_yt_pred + reg_pred

            monthly_y_pred.name = "value"
            if self._predictions.empty:
                self._predictions = monthly_y_pred
            else:
                self._predictions = pd.concat([self._predictions, monthly_y_pred])
        return self._predictions

    def _get_synthetic(self, exog_data: pd.DataFrame, seed: int) -> pd.Series:
        synthetic_y = pd.Series()
        for month in self.months:
            # Models are fitted for each month
            reg_model = self.monthly_reg_models[month]
            stl_result = self.monthly_stl_results[month]
            sarimax_model = self._monthly_models[month]

            monthly_exog = exog_data.loc[exog_data.index.month == month]

            # Create a synthetic time series for each day
            for day in monthly_exog.index.day.unique():
                # Regression model
                start_time = monthly_exog.loc[monthly_exog.index.day == day].index[0]
                end_time = start_time + pd.Timedelta(hours=23)
                daily_exog = monthly_exog.loc[start_time:end_time]
                reg_pred = self.monthly_reg_models[month].predict(exog=daily_exog)
                reg_pred = pd.Series(reg_pred, index=daily_exog.index)

                # Bootstrap the SARIMAX predictions within 75% confidence interval
                sarimax_pred = sarimax_model.predict()
                sarimax_pred_ci = np.percentile(sarimax_pred, [2.5, 97.5])
                sarimax_bootstrap = np.random.choice(sarimax_pred, size=len(daily_exog))
                sarimax_bootstrap = pd.Series(sarimax_bootstrap, index=daily_exog.index)

                # Recover electricity demand by adding predictions from the regression model,
                # predictions from SARIMAX, and also the STL's seasonal and trend components
                daily_stl_seasonal = stl_result.seasonal.loc[start_time:end_time]
                daily_stl_trend = stl_result.trend.loc[start_time:end_time]
                daily_syn_y = (
                    sarimax_bootstrap + reg_pred + daily_stl_seasonal + daily_stl_trend
                )
                daily_syn_y.name = "value"
                if synthetic_y.empty:
                    synthetic_y = daily_syn_y
                else:
                    synthetic_y = pd.concat([synthetic_y, daily_syn_y])
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
        monthly_exog = self.data.loc[
            self.data.index.month == month_to_use, exog_vars
        ].astype(float)

        # Regression model
        reg_model = OLS(monthly_y, monthly_exog).fit()
        monthly_yt = reg_model.resid

        # STL model
        stl_model = STL(
            monthly_yt,
            seasonal=self.stl_seasonal_value,
            period=self.stl_period_value,
        )
        stl_result = stl_model.fit()

        # SARIMAX model
        monthly_ytt = monthly_yt - stl_result.seasonal - stl_result.trend
        best_model = auto_arima(
            monthly_ytt,
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
