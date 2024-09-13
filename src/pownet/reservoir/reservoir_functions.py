""" reservoir_functions.py: Functions for operating reservoirs."""

import numpy as np
import pandas as pd


def adjust_hydropeaking(
    release: float,
    release_t0: float,
    max_release: float,
    min_release: float,
    hydropeak_factor: float = 0.15,
) -> float:
    """
    Adjust water release by considering hydropeaking and minimum environmental flow.
    The change in release is limited to hydropeak_factor times the maximum release.
    Also, the release cannot be lower than the minimum release or higher than the maximum release.

    Args:
        release (float): The release for the current day. Can be both negative and positive
        release_t0 (float): The release for the previous day. Can be both negative and positive
        max_release (float): The maximum release as a positive value
        min_release (float): The minimum release as a positive value
        hydropeak_factor (float): The factor to limit the change in release. Default is 0.15.

    Returns:
        float: The adjusted release.

    """
    # Calculate the difference between the current and previous release.
    # The sign is handled later in the code.
    release_change = release - release_t0

    # The rate of change is limited to hydropeak_factor
    change_limit = hydropeak_factor * max_release

    # Case 1: The difference is positive
    if release_change > 0:
        release_change = min(change_limit, release_change)

    # Case 2: The difference is negative, limit the decrease
    else:
        release_change = max(-change_limit, release_change)

    # Adjust the release based on the hydropeaking factor
    adj_release = release_t0 + release_change

    # Release is also bounded by min_release and  max_release
    adj_release = max(min_release, adj_release)
    adj_release = min(max_release, adj_release)
    return adj_release


def calc_min_environ_flow(
    inflow: float,
    mean_annual_flow: float,
    max_release: float,
) -> float:
    """Tdetermine the minimum amount of water that should be released
    from a reservoir to maintain the health of the downstream ecosystem.

    Example of three cases:

    1) If the inflow is less than 40% of the mean annual flow,
    the minimum flow is set to 60% of the inflow.
    This ensures that a reasonable portion of the limited water
    is still released to support the ecosystem.

    2) If the inflow is greater than 80% of the mean annual flow,
    the minimum flow is 30% of the inflow. a smaller percentage is
    released since the ecosystem is likely receiving ample water already.

    3) Otherwise, the minimum flow is 45% of the inflow.

    Args:
        inflow (float): The inflow to the reservoir
        mean_annual_flow (float): The mean annual flow
        max_release (float): The maximum release

    Returns:
        float: The minimum environmental flow
    """
    lower_maf_fraction = 0.4
    upper_maf_fraction = 0.8

    low_flow_scenario = lower_maf_fraction * mean_annual_flow
    upper_maf_fraction = upper_maf_fraction * mean_annual_flow

    small_fraction = 0.3
    medium_fraction = 0.45
    large_fraction = 0.6

    # Also need to ensure that the minimum environmental flow is less than the maximum release
    if inflow <= low_flow_scenario:
        return min(large_fraction * inflow, max_release)
    elif inflow > upper_maf_fraction:
        return min(small_fraction * inflow, max_release)
    else:
        return min(medium_fraction * inflow, max_release)


def calc_min_flow(
    inflow: pd.Series, mean_annual_flow: pd.Series, max_release: float
) -> None:
    """Find the minimum environmental flow for each day."""
    df = pd.DataFrame({"inflow": inflow, "mean_annual_flow": mean_annual_flow})
    min_flow = df.apply(
        lambda x: calc_min_environ_flow(
            inflow=x.inflow,
            mean_annual_flow=x.mean_annual_flow,
            max_release=max_release,
        ),
        axis=1,
    )
    return min_flow


def calc_target_level(
    min_day: int,
    max_day: int,
    min_level: float,
    max_level: float,
) -> pd.Series:
    """Calculate the target level for each day based on linear interpolation.

    Args:
        min_day (int): The day when the target level is at its minimum
        max_day (int): The day when the target level is at its maximum
        min_level (float): The minimum target level
        max_level (float): The maximum target level

    Returns:
        pd.Series: The target level for each day of the year
    """

    days_in_year = 365

    def _interpolate_between_min_and_max(day: int) -> float:
        """Interpolate target level between min_level and max_level."""
        return ((day - min_day) / (max_day - min_day)) * (
            max_level - min_level
        ) + min_level

    def _interpolate_after_max(day: int) -> float:
        """Interpolate target level after max_day."""
        return ((days_in_year - day + min_day) / (days_in_year - max_day + min_day)) * (
            max_level - min_level
        ) + min_level

    def _interpolate_before_min(day: int) -> float:
        """Interpolate target level before min_day."""
        return ((min_day - day) / (days_in_year - max_day + min_day)) * (
            max_level - min_level
        ) + min_level

    target_level = pd.Series(
        [
            (
                _interpolate_between_min_and_max(day)
                if min_day <= day <= max_day
                else (
                    _interpolate_after_max(day)
                    if day > max_day
                    else _interpolate_before_min(day)
                )
            )
            for day in range(1, days_in_year + 1)
        ],
        index=range(1, days_in_year + 1),
        dtype=float,
    )
    return target_level


def calc_target_storage(
    target_level: pd.Series,
    min_level: float,
    max_level: float,
    max_storage: float,
) -> pd.Series:
    """Calculate the target storage for each day based on linear interpolation.

    Args:
        target_level (pd.Series): The target level for each day
        min_level (float): The minimum level
        max_level (float): The maximum level
        max_storage (float): The maximum storage

    Returns:
        pd.Series: The target storage for each day
    """
    return ((target_level - min_level) / (max_level - min_level)) * max_storage


def calc_level_from_storage(
    storage: pd.Series,
    min_level: float,
    max_level: float,
    max_storage: float,
) -> pd.Series:
    """Calculate the level for each day based on linear interpolation.

    Args:
        storage (pd.Series): The storage for each day
        min_level (float): The minimum level
        max_level (float): The maximum level
        max_storage (float): The maximum storage

    Returns:
        pd.Series: The level for each day
    """
    return ((storage / max_storage) * (max_level - min_level)) + min_level


def calc_daily_hydropower(
    release: pd.Series,
    mid_level: pd.Series,
    max_generation: float,
    turbine_factor: float,
    max_head: float,
    max_level: float,
) -> pd.Series:
    """Calculate daily hydropower generation from release and mid-level.

    The hourly hydropower is calculated using the following formula:

    hourly_hydropower = min(turbine_factor * rho * g * head * flow_rate, max_generation)

    where:
    * rho: Density of water (kg/m3)
    * g: Acceleration due to gravity (m/s2)
    * head: Water head above the turbine (m)
    * flow_rate: Water flow rate (m3/s)
    * max_generation: Maximum power generation capacity of the turbine (MW)
    * turbine_factor: Turbine efficiency

    The daily hydropower is then obtained by multiplying the hourly hydropower by 24.

    Args:
        release: Water release (m3/day)
        mid_level: Average water level between current and previous timestep (m)
        max_generation: Maximum power generation capacity of the turbine (MW)
        turbine_factor: Turbine efficiency
        max_head: Maximum head (m)
        max_level: Maximum water level (m)

    Returns:
        pd.Series: Daily hydropower generation (MW-day)
    """
    # Define constants
    density = 998  # kg/m3
    gravity = 9.81  # m/s2

    # Calculate the water head above the turbine
    head = max_head - (max_level - mid_level)
    # Convert release from m3/day to m3/s
    flow_rate = release / (24 * 3600)
    # Calculate the hourly hydropower
    hourly_hydropower = (
        turbine_factor * density * gravity * head * flow_rate
    )  # in Watts
    hourly_hydropower = hourly_hydropower / 1e6  # Convert to MegaWatts
    # A turbine has a maximum water intake, so the power generation is capped
    hourly_hydropower = np.minimum(hourly_hydropower, max_generation)
    # Convert to MW-day
    daily_hydropower = hourly_hydropower * 24
    return daily_hydropower


def calc_release_impact(
    release_t: float,
    storage_t0: float,
    total_inflow_t: float,
    min_level: float,
    max_level: float,
    max_storage: float,
    level_t0: float,
    max_generation: float,
    turbine_factor: float,
    max_head: float,
) -> tuple[float, float, float, float]:
    """Calculate the impact of a given release on storage, level, mid-level, and hydropower."""
    spill_t = max(
        storage_t0 + total_inflow_t - max_storage - release_t,
        0,
    )
    storage_t = storage_t0 + total_inflow_t - release_t - spill_t
    level_t = calc_level_from_storage(
        storage=storage_t,
        min_level=min_level,
        max_level=max_level,
        max_storage=max_storage,
    )
    mid_level_t = (level_t0 + level_t) / 2
    daily_hydropower_t = calc_daily_hydropower(
        release=release_t,
        mid_level=mid_level_t,
        max_generation=max_generation,
        turbine_factor=turbine_factor,
        max_head=max_head,
        max_level=max_level,
    )
    return spill_t, storage_t, level_t, daily_hydropower_t


def calc_max_release(
    total_inflow_t: float,
    release_t0: float,
    storage_t0: float,
    min_flow_t: float,
    max_release: float,
    hydropeak_factor: float,
) -> float:
    """Calculate the maximum allowable release of the current timestep."""
    # Release is limited by the hydropeaking factor
    max_release_hydropeak_t = release_t0 + max_release * hydropeak_factor
    # Release cannot be larger than the turbine capacity
    max_release_t = min(max_release, max_release_hydropeak_t)
    # Release cannot be less than the min environmental flow
    max_release_t = max(min_flow_t, max_release_t)
    # Cannot release more than the amount of water in the reservoir
    if storage_t0 + total_inflow_t - max_release_t < 0:
        max_release_t = storage_t0 + total_inflow_t
    return max_release_t


def calc_min_release(
    total_inflow_t: float,
    release_t0: float,
    storage_t0: float,
    min_flow_t: float,
    max_release: float,
    hydropeak_factor: float,
) -> float:
    """Calculate the minimum allowable release of the current timestep."""
    # Release is limited by the hydropeaking factor
    min_release_hydropeak_t = release_t0 - max_release * hydropeak_factor
    # Limited by the minimum environmental flow
    min_release_t = max(min_flow_t, min_release_hydropeak_t)
    # Release cannot make the storage become negative
    if storage_t0 + total_inflow_t - min_release_t < 0:
        min_release_t = storage_t0 + total_inflow_t
    return min_release_t


def convert_to_hourly_hydropower(daily_hydropower) -> pd.Series:
    """Return the hourly hydropower values."""
    hourly_hydropower = daily_hydropower / 24
    # Repeat the hydropower values for each hour of the day
    hourly_hydropower = hourly_hydropower.loc[
        hourly_hydropower.index.repeat(24)
    ].reset_index(drop=True)
    # Index starts from 1
    hourly_hydropower.index += 1
    return hourly_hydropower
