import math
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from pownet.folder_sys import get_model_dir
from pownet.reservoir.solve_release import (
    solve_release_from_dispatch,
    solve_release_from_storage,
)


def adjust_hydropeaking(
    release: float,
    release_t0: float,
    max_release: float,
    min_release: float,
) -> float:
    """
    Adjust the release to consider hydropeaking and minimum environmental flow.
    The change in release is limited to 15% of the maximum release.
    Also, the release cannot be lower than the minimum release or higher than the maximum release.

    Let t0 denotes the previous day or timestep.
    """
    hydropeak_factor = 0.15
    # Calculate the difference between the current and previous release.
    # The sign is handled later in the code.
    diff_release = release - release_t0

    # Limit the change in release to at most 15% of the maximum release
    change_limit = hydropeak_factor * max_release

    # Case 1: If the difference is positive, limit the increase
    if diff_release > 0:
        diff_release = min(change_limit, diff_release)

    # Case 2: If the difference is negative, limit the decrease
    else:
        diff_release = max(-change_limit, diff_release)

    # Adjust the release
    adj_release = release_t0 + diff_release
    # Limit the release to the minimum and maximum release
    adj_release = max(min_release, release)
    adj_release = min(max_release, release)
    return adj_release


class Reservoir:
    """This class simulates a reservoir."""

    def __init__(
        self,
        model_name: str,
        reservoir_name: str,
        num_days: int,
        upstream_flow: pd.Series = None,
    ) -> None:
        # Reservoir parameters
        self.model_name = model_name
        self.name = reservoir_name
        self.num_days = num_days

        # Either hourly or daily, which is specified when
        # exporting hydropower as .CSV
        self.hydro_timestep: str = None

        reservoir_params = (
            pd.read_csv(
                os.path.join(get_model_dir(), model_name, "reservoir.csv"),
                header=0,
            )
            .set_index("name")
            .loc[reservoir_name]
        )

        self.min_day = int(reservoir_params["min_day"])
        self.max_day = int(reservoir_params["max_day"])
        self.min_level = reservoir_params["min_level"]
        self.max_level = reservoir_params["max_level"]

        # Max head is the maximum distance between the water level and turbine
        self.max_head = reservoir_params["max_head"]  # in meters

        self.max_storage = reservoir_params["max_storage"]  # in m3
        self.max_release = reservoir_params["max_release"]  # in m3/day
        # Max generation is power in MW
        self.max_generation = reservoir_params["max_generation"]
        # Number of cascade levels with zero being the furthest upstream
        self.cascade_level = reservoir_params["cascade_level"]
        # turbine efficiency
        self.turbine_factor = reservoir_params["turbine_factor"]

        # Inflow is in m3/day
        self.inflow = pd.read_csv(
            os.path.join(get_model_dir(), self.model_name, "inflow.csv")
        )
        # Remove 29th February from the dataset
        self.inflow = self.inflow[~((self.inflow.month == 2) & (self.inflow.day == 29))]
        self.inflow = self.inflow[self.name]
        # Index starts from 1
        self.inflow.index += 1

        # Upstream flow is in m3/day. Each column represents cascase level
        if upstream_flow is None:
            self.upstream_flow = pd.Series(0, index=range(1, self.num_days + 1))
        else:
            self.upstream_flow = upstream_flow
        # Make sure that indexing starts from 1
        if self.upstream_flow.index[0] != 1:
            raise ValueError("Index of upstream flow should start from 1.")
        # Make sure that upstream flow is non-negative
        if (self.upstream_flow < 0).any():
            raise ValueError("Upstream flow should be non-negative.")

        # Total inflow is in m3/day
        self.total_inflow = self.inflow + self.upstream_flow

        # Mean annual flow is in m3/day
        self.mean_annual_flow = pd.read_csv(
            os.path.join(get_model_dir(), self.model_name, "mean_annual_flow.csv")
        )
        # Remove 29th February from the dataset
        self.mean_annual_flow = self.mean_annual_flow[
            ~((self.mean_annual_flow.month == 2) & (self.mean_annual_flow.day == 29))
        ]
        self.mean_annual_flow = self.mean_annual_flow[self.name]
        # Index starts from 1
        self.mean_annual_flow.index += 1

        # Values to be calculated
        self.level: pd.Series = None  # in meters
        # The mid_level is the average of the level of the current day and the next day
        self.mid_level: pd.Series = None  # in meters
        self.storage: pd.Series = None  # in m3
        self.release: pd.Series = None  # in m3/day
        self.spill: pd.Series = None  # in m3/day
        self.min_flow: float = None  # in m3/day
        self.hydroenergy: pd.Series = None  # in MW-day
        self.hydropower: pd.Series = None  # in MW

        # These policies are calculated based on the min_day and max_day
        self.target_level: pd.Series = None  # in meters
        self.target_storage: pd.Series = None  # in m3

        # Reoperation values
        self.reop_storage: pd.Series = None
        self.reop_release: pd.Series = None
        self.reop_spill: pd.Series = None
        self.reop_level: pd.Series = None
        self.reop_mid_level: pd.Series = None

    def initialize(self) -> None:
        """Simulate the operation of the reservoir."""
        # Calculate the minimum environmental flow
        self._calc_min_flow()
        # Calculate the target storage and level
        self._calc_target_storage()
        # Get release using target storage
        self.release, self.spill, self.storage, storage_deviation = (
            solve_release_from_storage(
                reservoir_name=self.name,
                max_release=self.max_release,
                max_storage=self.max_storage,
                target_storage=self.target_storage,
                min_flow=self.min_flow,
                total_inflow=self.total_inflow,
            )
        )
        self.level = self.calc_level_from_storage(self.storage)
        self.mid_level = self.calc_mid_level_from_level(self.level)
        self.hydropower, self.hydroenergy = self.calc_hydropower_from_mid_level(
            release=self.release, mid_level=self.mid_level
        )

    def _calc_min_environmental_flow(
        self,
        inflow: float,
        mean_annual_flow: float,
    ) -> float:
        """The minimum environmental flow a relative value based on
        the mean annual flow and the inflow.
        There are three cases:

        1) If the inflow is less than 40% of the mean annual flow,
        the minimum flow is 60% of the inflow.

        2) If the inflow is greater than 80% of the mean annual flow,
        the minimum flow is 30% of the inflow.

        3) Otherwise, the minimum flow is 45% of the inflow.
        """
        # Also need to ensure that the minimum environmental flow is less than the maximum release
        if inflow <= 0.4 * mean_annual_flow:
            return min(0.6 * inflow, self.max_release)
        elif inflow > 0.8 * mean_annual_flow:
            return min(0.3 * inflow, self.max_release)
        else:
            return min(0.45 * inflow, self.max_release)

    def _calc_min_flow(self) -> None:
        """Find the minimum environmental flow for each day."""
        self.min_flow = pd.Series(np.nan, index=self.inflow.index)
        for day in range(1, self.num_days + 1):
            self.min_flow[day] = self._calc_min_environmental_flow(
                self.inflow[day], self.mean_annual_flow[day]
            )

    def _calc_target_storage(self) -> None:
        """
        Calculate the change in volume and level of the reservoir each day.
        The calculations are based on linear interpolation.

        Case 1: self.min_day < day < self.max_day
        If the day is between self.min_day and self.max_day,
        it interpolates target level between self.min_level and self.max_level.

        Case 2: day >= self.max_day
        If the day is greater than self.max_day, it interpolates
        between self.min_level and self.max_level.

        Case 3: day <= self.min_day
        If the day is less than self.min_day, it calculates the target level
        using a linear interpolation between self.min_level and self.max_level.

        The values are stored in self.target_level and self.target_storage.

        """
        self.target_storage = []
        self.target_level = []

        for day in range(self.num_days):  # 365 days in a year
            if self.min_day < day < self.max_day:
                target_level = (day - self.min_day) / (self.max_day - self.min_day) * (
                    self.max_level - self.min_level
                ) + self.min_level
            elif day >= self.max_day:
                target_level = (self.num_days - day + self.min_day) / (
                    self.num_days - self.max_day + self.min_day
                ) * (self.max_level - self.min_level) + self.min_level
            elif day <= self.min_day:
                target_level = (self.min_day - day) / (
                    self.num_days - self.max_day + self.min_day
                ) * (self.max_level - self.min_level) + self.min_level
            self.target_level.append(target_level)
            # Use linear interpolation to calculate the target volume
            self.target_storage.append(
                (
                    (target_level - self.min_level)
                    / (self.max_level - self.min_level)
                    * self.max_storage
                )
            )
        # Use pd.Series to conform to the indexing of other variables
        self.target_level = pd.Series(
            self.target_level, index=range(1, self.num_days + 1)
        )
        self.target_storage = pd.Series(
            self.target_storage, index=range(1, self.num_days + 1)
        )

    def calc_level_from_storage(self, storage: pd.Series) -> pd.Series:
        """Calculate the water level of the reservoir from the storage.
        The water level is calculated as a percentage of the maximum storage.
        """
        level = (
            storage / self.max_storage * (self.max_level - self.min_level)
            + self.min_level
        )
        return level

    def calc_mid_level_from_level(self, level: pd.Series) -> pd.Series:
        """Mid-level is the average of the level of the current day and the next day."""
        # Calculate the change in water level between t and t-1
        mid_level = (level + level.shift(1)) / 2
        # Assume the mid_level of the first day is the target level of the first day
        mid_level[1] = self.target_level[1]
        return mid_level

    def calc_hydropower_from_mid_level(
        self, release: pd.Series, mid_level: pd.Series
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate the mean hydropower of each day from the change in water level.
        To get the energy, we need to multiply the mean hydropower by
        the number of hours in a day.

        energy = turbine_factor * rho * g * head * flow_rate

        where,
        rho = 998 kg/m3 (density of water)

        To determine the water height above turbine (or head), let h(t) is the water level at time t
        h(t) = storage/max_storage * (max_level - min_level) + min_level

        Rachel's implementation:
        head = max_head - (max_level - ( h(t) + h(t-1) ) / 2)

        let mid_level = ( h(t) + h(t-1) ) / 2
        head = max_head - (max_level - mid_level)

        flow_rate in m3/s

        """
        # Define constants
        density = 998  # kg/m3
        g = 9.81  # m/s2
        # The head (d) is adjusted to max_head
        # by scaling water level with respect to max_level.
        head = self.max_head - (self.max_level - mid_level)
        # The formula requires m3/s not m3/day
        flow_rate = release / (24 * 3600)

        # Calculate the hydropower in Watts
        hydropower = self.turbine_factor * density * g * head * flow_rate
        # Convert to Megawatts
        hydropower = hydropower / 1e6
        # A turbine is limited by its maximum capacity.
        # Any unused water is not routed through the turbine.
        hydropower = np.minimum(hydropower, self.max_generation)

        # Convert to MW-day (energy)
        hydroenergy = hydropower * 24
        return hydropower, hydroenergy

    def reoperate(
        self,
        pownet_dispatch: pd.DataFrame,
        upstream_flow: pd.Series,
    ) -> pd.DataFrame:
        """Reoperate the reservoir based on the daily dispatch of the power system model.
        There are four cases:

        Case 1: If dispatch is equal to the maximum hydroenergy, then no need to reoperate.
        The reservoir cannot release more water than the maximum release.

        Case 2: If dispatch is equal to the minimum hydroenergy, then no need to reoperate.
        The reservoir cannot release less water than the minimum environmental flow.

        Case 3: If dispatch is less than the minimum hydroenergy, then no need to reoperate.
        This is similar to Case 2. However, we need to separate this case because
        comparing equality needs to consider numerical stability.
        Set the reoperated hydroenergy to the minimum hydroenergy because the reservoir
        does not need to dispatch all energy from minimum release.

        Case 4: If dispatch is less than the previous guess then set release to max release.

        In this function, t-1 is denoted as t0; t is denoted as t; t+1 is denoted as t1.
        """
        # days start from 1 to 365
        days = pownet_dispatch.index.to_list()
        # We do not reoperate on the first day (or first timestep) because the release is fixed on the first day.
        # Instead of reoperation, just use the original values.
        if 1 == days[0]:
            # Use the first day/step to initialize the reop values
            self.reop_storage = pd.Series(np.nan, index=range(1, self.num_days + 1))
            self.reop_storage[1] = self.storage[1]

            self.reop_release = pd.Series(np.nan, index=range(1, self.num_days + 1))
            self.reop_release[1] = self.release[1]

            self.reop_spill = pd.Series(np.nan, index=range(1, self.num_days + 1))
            self.reop_spill[1] = self.spill[1]

            self.reop_level = self.calc_level_from_storage(self.reop_storage)
            self.reop_mid_level = self.calc_mid_level_from_level(self.reop_level)

            self.reop_hydroenergy = pd.Series(np.nan, index=range(1, self.num_days + 1))

            return pownet_dispatch

        for day in days:
            # The maximum release (m3/day) based on hydropeaking.
            # The reservoir values are in m3/s.
            dispatch_t = pownet_dispatch.loc[day]
            release_t0 = self.reop_release.loc[day - 1]

            # Define the previous guesses of hydroenergy
            previous_hydroenergy_rule_curve = self.hydroenergy.loc[day]
            previous_hydroenergy_reop = self.reop_hydroenergy.loc[day]

            # solve_release optimization is not exact, so the hydroenergy
            # can be different from calculated with the formula
            opt_hydroenergy_t = None

            # Must consider output from reservoirs located upstream in the basin
            total_inflow_t = self.inflow.loc[day] + upstream_flow.loc[day]

            storage_t0 = self.reop_storage.loc[day - 1]
            level_t0 = self.calc_level_from_storage(storage_t0)

            ###################
            ##### Find hydropower from maximum and minimum releases
            ##### to compare with the dispatch
            ###################

            ###### Maximum release
            # Max release is 15% more than the original release or
            # the maximum release, whichever is smaller.
            hydropeak_factor = 0.15
            max_release_hydropeak_t = release_t0 + self.max_release * hydropeak_factor
            max_release_t = min(self.max_release, max_release_hydropeak_t)
            # Release cannot be less than the minimum environmental flow
            max_release_t = max(self.min_flow.loc[day], max_release_t)
            # Release cannot make the storage become negative
            if storage_t0 + total_inflow_t - max_release_t < 0:
                max_release_t = storage_t0 + total_inflow_t

            # TODO: Find a non-recurve approach to calculate the spill
            # Possibly need to use another optimization model
            spill_from_max_release_t = max(
                storage_t0 + total_inflow_t - self.max_storage - max_release_t,
                0,
            )
            storage_from_max_release_t = (
                storage_t0 + total_inflow_t - max_release_t - spill_from_max_release_t
            )
            level_from_max_release_t = self.calc_level_from_storage(
                storage_from_max_release_t
            )

            mid_level_from_max_release_t = (level_t0 + level_from_max_release_t) / 2

            _, max_hydroenergy_t = self.calc_hydropower_from_mid_level(
                max_release_t, mid_level_from_max_release_t
            )

            ###### Minimum release
            min_release_hydropeak_t = release_t0 - self.max_release * 0.15
            # Minimum environmental flow
            min_env_flow_t = self.min_flow.loc[day]
            min_release_t = max(min_env_flow_t, min_release_hydropeak_t)
            # Release cannot make the storage become negative
            if storage_t0 + total_inflow_t - min_release_t < 0:
                min_release_t = storage_t0 + total_inflow_t

            # TODO: Find a non-recurve approach to calculate the spill
            # Possibly need to use another optimization model
            spill_from_min_release_t = max(
                storage_t0 + total_inflow_t - self.max_storage - min_release_t,
                0,
            )
            storage_from_min_release_t = (
                storage_t0 + total_inflow_t - min_release_t - spill_from_min_release_t
            )
            level_from_min_release_t = self.calc_level_from_storage(
                storage_from_min_release_t
            )
            mid_level_from_min_release_t = (level_t0 + level_from_min_release_t) / 2
            _, min_hydroenergy_t = self.calc_hydropower_from_mid_level(
                min_release_t, mid_level_from_min_release_t
            )

            ###### Reoperation

            # Two values are equal when they are within 1 MW-day
            tolerance = 1

            # If the reservoir has been reoperated and hydroenergy is binding, then
            # the reservoir should release more water.
            if math.isclose(
                dispatch_t,
                previous_hydroenergy_rule_curve,
                abs_tol=tolerance,
            ):
                release_t = max_release_t
                spill_t = spill_from_max_release_t

            # Case 1: If dispatch is equal to max hydroenergy, then terminate.
            elif math.isclose(dispatch_t, max_hydroenergy_t, abs_tol=tolerance):
                self.reop_release.loc[day] = max_release_t
                self.reop_spill.loc[day] = spill_from_max_release_t
                self.reop_storage[day] = storage_from_max_release_t
                self.reop_level[day] = level_from_max_release_t
                self.reop_hydroenergy.loc[day] = max_hydroenergy_t
                return pownet_dispatch

            # If dispatch (from previous guess) is greater than max hydroenergy,
            # then the reservoir can only give the maximum release.
            elif dispatch_t > max_hydroenergy_t:
                release_t = max_release_t
                spill_t = spill_from_max_release_t

            # Case 2: If dispatch is equal to min hydroenergy, then terminate
            elif math.isclose(dispatch_t, min_hydroenergy_t, abs_tol=tolerance):
                self.reop_release.loc[day] = min_release_t
                self.reop_spill.loc[day] = spill_from_min_release_t
                self.reop_storage.loc[day] = storage_from_min_release_t
                self.reop_level[day] = level_from_min_release_t
                self.reop_hydroenergy.loc[day] = min_hydroenergy_t
                return pownet_dispatch

            # Case 3: If the dispatch is less than the min hydroenergy,
            # set the release to min release.
            elif dispatch_t < min_hydroenergy_t:
                self.reop_release.loc[day] = min_release_t
                self.reop_spill.loc[day] = spill_from_min_release_t
                self.reop_storage.loc[day] = storage_from_min_release_t
                self.reop_level[day] = level_from_min_release_t
                # Set the hydroenergy to the minimum hydroenergy
                # to get convergence
                self.reop_hydroenergy.loc[day] = min_hydroenergy_t
                return pownet_dispatch

            # If dispatch is between min_hydroenergy and max_hydroenergy,
            # then find the release using an optimization algorithm.
            elif min_hydroenergy_t < dispatch_t < max_hydroenergy_t:
                (
                    release_t,
                    spill_t,
                    opt_storage,
                    opt_level,
                    opt_hydroenergy_t,
                    z_t,
                    opt_hydropower,
                ) = solve_release_from_dispatch(
                    dispatch=dispatch_t,
                    turbine_factor=self.turbine_factor,
                    max_head=self.max_head,
                    max_level=self.max_level,
                    min_level=self.min_level,
                    level_t0=level_t0,
                    storage_max=self.max_storage,
                    storage_t0=storage_t0,
                    inflow=total_inflow_t,
                    min_release=min_release_t,
                    max_release=max_release_t,
                    max_generation=self.max_generation,
                    res_name=self.name,
                )

            # Case 5: If dispatch is equal to the previous guess from reoperation,
            # then terminate.
            elif math.isclose(dispatch_t, previous_hydroenergy_reop, abs_tol=tolerance):
                return pownet_dispatch

            # Case 4: If dispatch is less than the previous guess,
            # then the reservoir should save water.
            elif dispatch_t < previous_hydroenergy_reop:
                (
                    release_t,
                    spill_t,
                    opt_storage,
                    opt_level,
                    opt_hydroenergy_t,
                    z_t,
                    opt_hydropower,
                ) = solve_release_from_dispatch(
                    dispatch=dispatch_t,
                    turbine_factor=self.turbine_factor,
                    max_head=self.max_head,
                    max_level=self.max_level,
                    min_level=self.min_level,
                    level_t0=level_t0,
                    storage_max=self.max_storage,
                    storage_t0=storage_t0,
                    inflow=total_inflow_t,
                    min_release=min_release_t,
                    max_release=max_release_t,
                    max_generation=self.max_generation,
                    res_name=self.name,
                )

            # Catch other cases.
            else:
                raise ValueError(
                    f"Unknown case: {dispatch_t} vs. {previous_hydroenergy_reop}"
                )

            # Calculate the storage and level from the release and spill
            storage_t = storage_t0 + total_inflow_t - release_t - spill_t
            level_t = self.calc_level_from_storage(storage_t)
            mid_level_t = (level_t + level_t0) / 2

            _, new_hydroenergy_t = self.calc_hydropower_from_mid_level(
                release_t, mid_level_t
            )

            if opt_hydroenergy_t:
                if abs(new_hydroenergy_t - opt_hydroenergy_t) / opt_hydroenergy_t < 0.3:
                    new_hydroenergy_t = opt_hydroenergy_t
                else:
                    raise ValueError("Hydropower is not close to the optimized value.")

            # Update the reoperation values
            self.reop_release.loc[day] = release_t
            self.reop_spill.loc[day] = spill_t
            self.reop_storage.loc[day] = storage_t
            self.reop_level[day] = level_t
            self.reop_hydroenergy.loc[day] = new_hydroenergy_t

        return new_hydroenergy_t


class Basin:
    def __init__(
        self,
        model_name: str,
        basin: str,
        num_days: int,
    ) -> None:
        """
        This class is a collection of Reservoirs on a basin.
        """

        self.model_name: str = model_name
        self.basin: str = basin
        self.num_days: int = num_days

        # User must specify reservoirs and their parameters in a CSV file
        res_df = pd.read_csv(
            os.path.join(get_model_dir(), self.model_name, "reservoir.csv")
        )
        # Filter reservoirs by basin
        res_df = res_df[res_df["basin"] == self.basin]
        self.reservoir_names = res_df["name"].tolist()

        # Largest cascade level in the basin
        # Cascade level starts from 0 (most upstream)
        self.max_cascade = res_df["cascade_level"].max()
        if self.basin not in res_df.basin.unique():
            raise ValueError("Basin not found. Check basin name.")

        # Map cascade level to its list of reservoir names {cascade_lvl: [name1, name2]}
        sub_df = res_df[["cascade_level", "name"]]
        self.map_cascade = sub_df.groupby("cascade_level")["name"].apply(list).to_dict()

        # Each column represents outflow from reservoirs at the previous cascade level
        # Ending index has +2 because
        # (+1) Python indexing starts at 1 and
        # (+1) Placement for outflow from the last cascade level
        self.upstream_flow = pd.DataFrame(
            0, columns=range(self.max_cascade + 2), index=range(1, self.num_days + 1)
        )

        # Dict of reservoir objects based on their cascasde level
        # {cascade_level: [Reservoir1, Reservoir2]}
        self.reservoirs: dict[int, Reservoir] = {
            i: [] for i in range(self.max_cascade + 1)
        }

        # Timeseries of hydropower by each reservoir
        self.basin_hydropower: pd.DataFrame = None

    def initialize(self) -> None:
        # Initialize hydropower dataframe with columns as reservoirs
        self.basin_hydropower = pd.DataFrame()
        # Initialize the upstream flow for each cascade level
        for cas_lvl in range(self.max_cascade + 1):
            res_names = self.map_cascade[cas_lvl]
            for res_name in res_names:
                res = Reservoir(
                    model_name=self.model_name,
                    reservoir_name=res_name,
                    num_days=self.num_days,
                    upstream_flow=self.upstream_flow.loc[:, cas_lvl],
                )
                res.initialize()
                self.reservoirs[cas_lvl].append(res)
                # The outflow from this reservoir is the inflow
                # to the downstream. Hence, add 1 to the cascade level.
                self.upstream_flow.loc[:, cas_lvl + 1] = (
                    self.upstream_flow.loc[:, cas_lvl + 1] + res.release + res.spill
                )
                # Hydroenergy is in MW-day
                self.basin_hydropower[res.name] = res.hydroenergy

    def export_hydropower_csv(self, timestep: str) -> None:
        """Export the hydropower values as an input for the power system model.
        The timestep parameter can be either 'daily' or 'hourly'.
        """
        csv_name = f"pownet_hydropower.csv"
        input_folder = os.path.join(get_model_dir(), self.model_name, csv_name)
        if timestep == "daily":
            self.basin_hydropower.to_csv(input_folder, index=False)
            return
        elif timestep == "hourly":
            # Repeat the hydropower values for each hour of the day
            df = self.basin_hydropower.loc[
                self.basin_hydropower.index.repeat(24)
            ].reset_index(drop=True)

            # Divide the hydropower by 24 to get the hourly values
            df = df / 24
            df.to_csv(input_folder, index=False)
            return
        else:
            raise ValueError("Unknown timestep")

    def get_basin_hydropower(self, timestep) -> pd.DataFrame:
        """Return a dataframe of hydropower by each reservoir."""
        if timestep == "daily":
            return self.basin_hydropower

        elif timestep == "hourly":
            # Repeat the hydropower values for each hour of the day
            df = self.basin_hydropower.loc[
                self.basin_hydropower.index.repeat(24)
            ].reset_index(drop=True)
            df = df / 24
            return df
        else:
            raise ValueError("Unknown timestep")


class ReservoirOperator:
    def __init__(
        self,
        model_name: str,
        num_days: int,
    ) -> None:
        """A class that manages the operation of multiple basins."""
        self.model_name: str = model_name
        self.num_days: int = num_days

        self.basin_names: list[str] = (
            pd.read_csv(
                os.path.join(get_model_dir(), model_name, "reservoir.csv"), header=0
            )["basin"]
            .unique()
            .tolist()
        )

        self.basins: list[Basin] = [
            Basin(model_name, basin, num_days) for basin in self.basin_names
        ]

        # Store the hydropower timeseries
        self.hydropower: pd.DataFrame = None

        # Get a list of reservoir names in the system
        self.reservoir_names = []
        for basin in self.basins:
            for name in basin.reservoir_names:
                if name in basin.reservoir_names:
                    self.reservoir_names.append(name)

    def simulate(self):
        self.hydropower = pd.DataFrame()
        for basin in self.basins:
            basin.initialize()
            self.hydropower = pd.concat(
                [self.hydropower, basin.get_basin_hydropower(timestep="daily")],
                axis=1,
            )

    def reoperate_basins(self, pownet_dispatch: pd.DataFrame) -> pd.DataFrame:
        """Reoperate the reservoirs based on the daily dispatch of the power system model.
        Note that we don't reoperate on the first day of the simulation period.
        """
        days = pownet_dispatch.index.to_list()
        new_hydroenergy = pd.DataFrame(np.nan, index=days, columns=self.reservoir_names)

        for basin in self.basins:
            # Initialize the upstream flow for each cascade
            # Add 2 to the max cascade level because the last column is for the outflow
            # from the last cascade level. Also, Python indexing excludes the last element.
            upstream_flow = pd.DataFrame(
                0, index=days, columns=range(basin.max_cascade + 2)
            )
            # Loop in order of cascade level
            for cas_lvl in range(basin.max_cascade + 1):
                for res in basin.reservoirs[cas_lvl]:
                    res_dispatch = pownet_dispatch[res.name]
                    res_hydroenergy = res.reoperate(
                        res_dispatch, upstream_flow.loc[:, cas_lvl]
                    )
                    # Update upstream_flow for the next cascade level
                    upstream_flow.loc[:, cas_lvl + 1] = (
                        upstream_flow.loc[:, cas_lvl + 1]
                        + res.reop_release[days]
                        + res.reop_spill[days]
                    )

                    if isinstance(res_hydroenergy, float):
                        new_hydroenergy.loc[days, res.name] = res_hydroenergy
                    elif isinstance(res_hydroenergy, pd.Series):
                        new_hydroenergy.loc[days, res.name] = res_hydroenergy.values

        return new_hydroenergy

    def get_hydropower(self) -> pd.DataFrame:
        return self.hydropower

    def export_hydropower_csv(self, timestep: str) -> None:
        csv_name = f"pownet_hydropower.csv"
        input_folder = os.path.join(get_model_dir(), self.model_name, csv_name)

        self.hydro_timestep = timestep

        if timestep == "daily":
            self.hydropower.to_csv(input_folder, index=False)
            return
        elif timestep == "hourly":
            # Repeat the hydropower values for each hour of the day
            df = self.hydropower.loc[self.hydropower.index.repeat(24)].reset_index(
                drop=True
            )
            df = df / 24
            df.to_csv(input_folder, index=False)
            return
        else:
            raise ValueError("Unknown timestep")

    def get_plots(self):
        """Plot daily storage, release, and spill of each reservoir."""
        for basin in self.basins:
            reservoirs = [
                res for res_lists in basin.reservoirs.values() for res in res_lists
            ]
            for res in reservoirs:
                fig, ax = plt.subplots()
                ax.plot(res.release, label="Release (m3/day)")
                ax.plot(res.total_inflow, label="Inflow (m3/day)")
                ax.plot(res.spill, label="Spill (m3/day)", linestyle="dotted")
                ax.plot(
                    res.release + res.spill,
                    label="Outflow (m3/day)",
                    linestyle="dotted",
                )
                ax.set_xlabel("Day")
                ax.set_ylabel("Flow rate (m3/day)")
                ax.set_title(res.name)

                ax2 = ax.twinx()
                ax2.plot(res.storage, label="Storage (m3)", color="k", linewidth=1)
                ax2.plot(
                    res.target_storage,
                    label="Target Storage (m3)",
                    linestyle="--",
                    color="k",
                    linewidth=5,
                    alpha=0.5,
                )
                ax2.set_ylabel("Storage (m3)")
                fig.legend()
                plt.show()


if __name__ == "__main__":
    # Test the Reservoir class
    model_name = "dummy_hydro"

    # Test the ReservoirOperator class
    res_operator = ReservoirOperator(model_name, num_days=365)
    res_operator.simulate()
    res_operator.get_plots()
