""" timeseries_utils.py: Utility functions for timeseries data """

import numpy as np
import pandas as pd
from sklearn.preprocessing import PowerTransformer


def transform_log1p(y: pd.Series, B1_y: pd.Series):
    # Take difference
    y = y - B1_y
    # Apply the transformation
    y = np.log1p(y)
    return y


def inverse_log1p(y_pred: pd.Series, B1_y: pd.Series) -> pd.Series:
    # invert the transformation
    y_pred = np.expm1(y_pred)
    # Convert negative values to 0
    y_pred = np.maximum(y_pred, 0)
    # Add the last observed value
    y_pred = y_pred + B1_y
    return y_pred


def transform_yeojohnson(
    y: pd.Series, B1_y: pd.Series
) -> tuple[pd.Series, PowerTransformer]:
    """Differencing the data and apply the Yeo-Johnson transformation to the data"""
    # Take difference and discard the first observation
    transformed_y = (y - B1_y).dropna()
    # Apply the transformation
    power_transformer = PowerTransformer(method="yeo-johnson")
    power_transformer.fit(transformed_y.values.reshape(-1, 1))
    transformed_y = power_transformer.transform(transformed_y.values.reshape(-1, 1))
    return transformed_y, power_transformer


def inverse_yeojohnson(
    y_pred: np.array,
    B1_y: pd.Series,
    initial_value: float,
    power_transformer: PowerTransformer,
) -> pd.Series:
    """Invert the Yeo-Johnson transformation"""
    # invert the transformation
    y_pred = power_transformer.inverse_transform(y_pred.reshape(-1, 1))
    y_pred = pd.Series(y_pred.flatten(), index=B1_y.index)
    # Add value from the previous timestep because the data was differenced
    y_pred = y_pred + B1_y
    # Insert the first observed value to the beginning of the series
    # because the first value was removed during differencing
    temp_series = pd.Series([initial_value])
    temp_series.index = [B1_y.index[0] - 1]
    y_pred = pd.concat([temp_series, y_pred])
    return y_pred


def post_process_solar(
    solar_data: pd.DataFrame, value_cols: list[str], sunrise_time: str, sunset_time: str
):
    # Ensure values are zero outside sunset and sunrise times
    solar_data.loc[
        (solar_data["datetime"].dt.time < pd.to_datetime(sunrise_time).time())
        | (solar_data["datetime"].dt.time > pd.to_datetime(sunset_time).time()),
        value_cols,
    ] = 0

    # Ensure no negative values, which can happen with ARIMA predictions
    solar_data[value_cols] = solar_data[value_cols].clip(lower=0)
