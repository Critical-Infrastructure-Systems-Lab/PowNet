import math
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from pownet.folder_sys import get_model_dir, get_output_dir
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

        # These policies are calculated based on the min_day and max_day
        self.target_level: pd.Series = None  # in meters
        self.target_storage: pd.Series = None  # in m3

        # Reoperation values
        self.reop_upstream: pd.Series = None
        self.reop_storage: pd.Series = None
        self.reop_release: pd.Series = None
        self.reop_spill: pd.Series = None
        self.reop_level: pd.Series = None

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
                resname=self.name,
            )
        )
        self.level = self._calc_level_from_storage(self.storage)

        self.mid_level = (self.level + self.level.shift(1)) / 2
        # Assume the mid_level of the first day is the target level of the first day
        self.mid_level[1] = self.target_level[1]

        self.hydroenergy = self._calc_hydroenergy(
            release=self.release,
            mid_level=self.mid_level,
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

    def _calc_level_from_storage(self, storage: pd.Series) -> pd.Series:
        """Calculate the water level of the reservoir from the storage.
        The water level is calculated as a percentage of the maximum storage.
        """
        return (
            storage / self.max_storage * (self.max_level - self.min_level)
            + self.min_level
        )

    def _calc_hydroenergy(
        self,
        release: pd.Series,
        mid_level: pd.Series,
    ) -> pd.Series:
        """Calculate hydroenergy from release and mid-level
        To get the energy, we need to multiply the mean hydropower by
        the number of hours in a day.

        energy = turbine_factor * rho * g * head * flow_rate

        where,
        rho = 998 kg/m3 (density of water)

        To determine the water height above turbine (or head), let h(t) is the water level at time t
        h(t) = storage/max_storage * (max_level - min_level) + min_level

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

        return hydroenergy

    def reoperate(
        self, pownet_dispatch: pd.DataFrame, upstream_flow: pd.Series
    ) -> pd.DataFrame:
        """Reoperate the reservoir based on the daily dispatch of the power system model.
        There are seven cases to consider:

        1) If dispatch is equal to the previous guess from reoperation,
        then terminate.

        2) If dispatch is equal to min hydroenergy,
        set release to min release.

        3) If dispatch is equal to max hydroenergy,
        set release to max release.

        4) If dispatch is less than min hydroenergy,
        set release to min release.

        5) If dispatch is greater than max hydroenergy,
        set release to max release.

        6) If dispatch is equal to hydropower from the rule curve,
        set release to the maximum release.

        7) If dispatch is between min_hydroenergy and max_hydroenergy,
        then find the release using an optimization algorithm.

        In this function, t-1 is denoted as t0; t is denoted as t; t+1 is denoted as t1.
        """
        # Upstream flow may change every reoperation iteration because
        # reservoirs located upstream may reoperate.
        self.reop_upstream = upstream_flow

        # Day(s) in which to reoperate the reservoir
        days = pownet_dispatch.index.to_list()

        # We do not reoperate on the first day (or first timestep) because the release is fixed on the first day.
        # Instead of reoperation, just use the original values.
        if days[0] == 1:
            # Use this opportunity to initialize reoperation values
            self.reop_storage = pd.Series(np.nan, index=range(1, self.num_days + 1))
            self.reop_storage[1] = self.storage[1]

            self.reop_release = pd.Series(np.nan, index=range(1, self.num_days + 1))
            self.reop_release[1] = self.release[1]

            self.reop_spill = pd.Series(np.nan, index=range(1, self.num_days + 1))
            self.reop_spill[1] = self.spill[1]

            self.reop_level = self._calc_level_from_storage(self.reop_storage)
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

            # Reoperation uses the total inflow for calculations
            total_inflow_t = self.inflow.loc[day] + upstream_flow.loc[day]

            # Reservoir values from the previous timestep
            storage_t0 = self.reop_storage.loc[day - 1]
            level_t0 = self._calc_level_from_storage(storage_t0)

            ###################
            ##### Find hydropower from maximum and minimum releases
            ##### to compare with the dispatch
            ###################
            # Change in release is limited to 15% of the maximum release
            hydropeak_factor = 0.15

            ###### Maximum release
            max_release_hydropeak_t = release_t0 + self.max_release * hydropeak_factor
            # Release cannot be larger than the channel capacity
            max_release_t = min(self.max_release, max_release_hydropeak_t)

            # Release cannot be less than the minimum environmental flow
            max_release_t = max(self.min_flow.loc[day], max_release_t)

            # Cannot release more than the amount of water in the reservoir
            if storage_t0 + total_inflow_t - max_release_t < 0:
                max_release_t = storage_t0 + total_inflow_t

            spill_from_max_release_t = max(
                storage_t0 + total_inflow_t - self.max_storage - max_release_t,
                0,
            )
            storage_from_max_release_t = (
                storage_t0 + total_inflow_t - max_release_t - spill_from_max_release_t
            )
            level_from_max_release_t = self._calc_level_from_storage(
                storage_from_max_release_t
            )

            mid_level_from_max_release_t = (level_t0 + level_from_max_release_t) / 2

            max_hydroenergy_t = self._calc_hydroenergy(
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

            spill_from_min_release_t = max(
                storage_t0 + total_inflow_t - self.max_storage - min_release_t,
                0,
            )
            storage_from_min_release_t = (
                storage_t0 + total_inflow_t - min_release_t - spill_from_min_release_t
            )
            level_from_min_release_t = self._calc_level_from_storage(
                storage_from_min_release_t
            )
            mid_level_from_min_release_t = (level_t0 + level_from_min_release_t) / 2
            min_hydroenergy_t = self._calc_hydroenergy(
                min_release_t, mid_level_from_min_release_t
            )

            ###################
            ##### Cases to consider
            ###################

            # Two values are equal when they are within 1 MW-day
            tolerance = 1

            # Case 1: If dispatch is equal to the previous guess from reoperation,
            # then terminate.
            if math.isclose(dispatch_t, previous_hydroenergy_reop, abs_tol=tolerance):
                return pownet_dispatch

            # Case 2: If dispatch is equal to min hydroenergy,
            # set release to min release
            elif math.isclose(dispatch_t, min_hydroenergy_t, abs_tol=tolerance):
                self.reop_release.loc[day] = min_release_t
                self.reop_spill.loc[day] = spill_from_min_release_t
                self.reop_storage.loc[day] = storage_from_min_release_t
                self.reop_level[day] = level_from_min_release_t
                self.reop_hydroenergy.loc[day] = min_hydroenergy_t
                return pownet_dispatch

            # Case 3: If dispatch is equal to max hydroenergy,
            # set release to max release.
            elif math.isclose(dispatch_t, max_hydroenergy_t, abs_tol=tolerance):
                self.reop_release.loc[day] = max_release_t
                self.reop_spill.loc[day] = spill_from_max_release_t
                self.reop_storage[day] = storage_from_max_release_t
                self.reop_level[day] = level_from_max_release_t
                self.reop_hydroenergy.loc[day] = max_hydroenergy_t
                return pownet_dispatch

            # Case 4: If dispatch is less than min hydroenergy,
            # set release to min release.
            elif dispatch_t < min_hydroenergy_t:
                self.reop_release.loc[day] = min_release_t
                self.reop_spill.loc[day] = spill_from_min_release_t
                self.reop_storage.loc[day] = storage_from_min_release_t
                self.reop_level[day] = level_from_min_release_t
                self.reop_hydroenergy.loc[day] = min_hydroenergy_t
                # Return the original dispatch to get convergence
                # for the reoperation
                return pownet_dispatch

            # Case 5: If dispatch is greater than max hydroenergy,
            # then the reservoir can only give the maximum release.
            elif dispatch_t > max_hydroenergy_t:
                self.reop_release.loc[day] = max_release_t
                self.reop_spill.loc[day] = spill_from_max_release_t
                self.reop_storage[day] = storage_from_max_release_t
                self.reop_level[day] = level_from_max_release_t
                self.reop_hydroenergy.loc[day] = max_hydroenergy_t
                return max_hydroenergy_t

            # Case 6: If dispatch is equal to hydropower from the rule curve
            # (presumably this is the first iteration of reoperation),
            # then set release to the maximum release.
            elif math.isclose(
                dispatch_t,
                previous_hydroenergy_rule_curve,
                abs_tol=tolerance,
            ):
                self.reop_release.loc[day] = max_release_t
                self.reop_spill.loc[day] = spill_from_max_release_t
                self.reop_storage[day] = storage_from_max_release_t
                self.reop_level[day] = level_from_max_release_t
                self.reop_hydroenergy.loc[day] = max_hydroenergy_t
                return max_hydroenergy_t

            # Case 7: If dispatch is between min_hydroenergy and max_hydroenergy,
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

                # The optimization might not produce the exact values
                # Check that the values are close
                storage_t = storage_t0 + total_inflow_t - release_t - spill_t
                level_t = self._calc_level_from_storage(storage_t)

                mid_level_t = (level_t + level_t0) / 2
                hydroenergy_t = self._calc_hydroenergy(release_t, mid_level_t)

                check1 = math.isclose(opt_storage, storage_t, rel_tol=0.05)
                check2 = math.isclose(opt_level, level_t, rel_tol=0.05)
                check3 = math.isclose(opt_hydroenergy_t, hydroenergy_t, rel_tol=0.05)
                if not (check1 and check2 and check3):
                    raise ValueError("Optimization did not produce the correct values.")

                # Update the reoperation values
                self.reop_release.loc[day] = release_t
                self.reop_spill.loc[day] = spill_t
                self.reop_storage.loc[day] = storage_t
                self.reop_level[day] = level_t
                self.reop_hydroenergy.loc[day] = hydroenergy_t
                return hydroenergy_t

            # Catch other cases.
            else:
                raise ValueError(
                    f"Unknown case: {dispatch_t} vs. {previous_hydroenergy_reop}"
                )


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
            # Increase font size
            for res in reservoirs:
                fig, ax = plt.subplots(figsize=(13, 7), layout="constrained", dpi=350)
                ax.plot(res.total_inflow, label="Inflow (m3/day)")
                ax.plot(res.release, label="Release (m3/day)")
                ax.plot(
                    res.spill, label="Spill (m3/day)", linestyle="dotted", linewidth=2
                )
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
                fig.legend(loc="outside right upper")

                # Save figure
                output_folder = os.path.join(
                    get_output_dir(), f"{self.model_name}_reservoirs"
                )
                if not os.path.exists(output_folder):
                    os.makedirs(output_folder, exist_ok=True)
                fig.savefig(os.path.join(output_folder, f"{res.name}.png"))

                plt.show()

    def export_reservoir_outputs(self):
        """Export the daily values of storage, release, and spill of each reservoir."""
        output_folder = os.path.join(get_output_dir(), f"{self.model_name}_reservoirs")
        # If the output directory does not exist, create it
        if not os.path.exists(output_folder):
            os.makedirs(output_folder, exist_ok=True)

        for basin in self.basins:
            reservoirs = [
                res for res_lists in basin.reservoirs.values() for res in res_lists
            ]
            for res in reservoirs:
                df = pd.DataFrame(
                    {
                        "inflow": res.inflow,
                        "upstream_flow": res.upstream_flow,
                        "storage": res.storage,
                        "release": res.release,
                        "spill": res.spill,
                        "level": res.level,
                        "mid_level": res.mid_level,
                        "min_flow": res.min_flow,
                    }
                )
                df.to_csv(
                    os.path.join(output_folder, f"{res.name}.csv"),
                    index=False,
                )

                if res.reop_storage is not None:
                    reop_df = pd.DataFrame(
                        {
                            "inflow": res.inflow,
                            "upstream_flow": res.upstream_flow,
                            "storage": res.reop_storage,
                            "release": res.reop_release,
                            "spill": res.reop_spill,
                            "level": res.reop_level,
                        }
                    )
                    reop_df.to_csv(
                        os.path.join(output_folder, f"{res.name}_reop.csv"),
                        index=False,
                    )


if __name__ == "__main__":
    # Test the Reservoir class
    model_name = "dummy_hydro"

    # Test the ReservoirOperator class
    res_operator = ReservoirOperator(model_name, num_days=365)
    res_operator.simulate()
    res_operator.export_reservoir_outputs()
    res_operator.export_hydropower_csv(timestep="daily")
    # res_operator.get_plots()