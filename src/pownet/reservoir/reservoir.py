import math
import os

import gurobipy as gp
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

from pownet.folder_sys import get_model_dir
from pownet.reservoir.solve_release import gp_solve_release


def adjust_hydropeaking(
    release: float, release_t0: float, max_release: float, min_release: float
) -> float:
    """
    Adjust the release to consider hydropeaking and minimum environmental flow.
    The change in release is limited to 15% of the maximum release.
    Also, the release cannot be lower than the minimum release or higher than the maximum release.
    """
    # Calculate the difference between the current and previous release
    diff_release = release - release_t0
    # Limit the change in release to at most 15% of the maximum release
    # Case 1: If the difference is positive, limit the increase
    if diff_release > 0:
        diff_release = min(max_release * 0.15, diff_release)
    # Case 2: If the difference is negative, limit the decrease
    else:
        diff_release = max(-max_release * 0.15, diff_release)
    # Adjust the release
    adj_release = release_t0 + diff_release
    # Limit the release to the minimum and maximum release
    adj_release = max(min_release, release)
    adj_release = min(max_release, release)
    return adj_release


class Reservoir:
    """This class simulates the operation of a reservoir."""

    def __init__(
        self,
        model_name: str,
        reservoir_name: str,
        num_days: int,
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

        self.min_day: int = int(reservoir_params["min_day"])
        self.max_day: int = int(reservoir_params["max_day"])
        self.min_level: float = reservoir_params["min_level"]
        self.max_level: float = reservoir_params["max_level"]

        # Max head is the maximum distance between the water level and turbine
        self.max_head: float = reservoir_params["max_head"]  # in meters

        self.max_storage: float = reservoir_params["max_storage"]  # in m3
        self.max_release: float = reservoir_params["max_release"]  # in m3/day
        # Max generation is power in MW
        self.max_generation: float = reservoir_params["max_generation"]
        # Number of cascade levels with zero being the furthest upstream
        self.cascade_level: int = reservoir_params["cascade_level"]
        # turbine efficiency
        self.turbine_factor: float = reservoir_params["turbine_factor"]

        # Timeseries data
        self.inflow: pd.Series = None  # in m3/day
        self.upstream_flow: pd.Series = None  # in m3/day
        self.total_inflow: pd.Series = None  # in m3/day
        self.mean_annual_flow: pd.Series = None  # in m3/day

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
        self.reoperated_days: pd.Series = None

        # These policies are calculated based on the min_day and max_day
        self.target_level: list[float] = None  # in meters
        self.target_storage: list[float] = None  # in m3
        self.target_release: list[float] = None  # in m3/day

        self.model: gp.model = None
        self.release_vars: gp.tupledict[str, gp.Var] = None
        self.storage_vars: gp.tupledict[str, gp.Var] = None
        self.spill_vars: gp.tupledict[str, gp.Var] = None

        self.start_day: int = None  # Initial day of optimization

        # Reoperation values
        self.reop_storage: pd.Series = None
        self.reop_release: pd.Series = None
        self.reop_spill: pd.Series = None
        self.level: pd.Series = None
        self.reop_mid_level: pd.Series = None

    def initialize(self, upstream_flow: pd.Series) -> None:
        self.inflow = pd.read_csv(
            os.path.join(get_model_dir(), self.model_name, "inflow.csv")
        )
        # Remove 29th February from the dataset
        self.inflow = self.inflow[~((self.inflow.month == 2) & (self.inflow.day == 29))]
        self.inflow = self.inflow[self.name]

        self.upstream_flow = upstream_flow

        # Add the total inflows
        self.total_inflow = self.inflow + self.upstream_flow

        # Mean annual flow was previously calculated
        self.mean_annual_flow = pd.read_csv(
            os.path.join(get_model_dir(), self.model_name, "mean_annual_flow.csv")
        )
        # Remove 29th February from the dataset
        self.mean_annual_flow = self.mean_annual_flow[
            ~((self.mean_annual_flow.month == 2) & (self.mean_annual_flow.day == 29))
        ]
        self.mean_annual_flow = self.mean_annual_flow[self.name]

    def calc_target_storage(self) -> None:
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

    def _calc_min_environmental_flow(
        self,
        inflow: float,
        mean_annual_flow: float,
    ) -> float:
        """Minimum environmental flow is a relative value based on the mean annual flow and the inflow."""
        # Also need to ensure that the minimum environmental flow is less than the maximum release
        if inflow <= 0.4 * mean_annual_flow:
            return min(0.6 * inflow, self.max_release)
        elif inflow > 0.8 * mean_annual_flow:
            return min(0.3 * inflow, self.max_release)
        else:
            return min(0.45 * inflow, self.max_release)

    def calc_min_flow(self) -> None:
        """The minimum environmental flow a relative value based on
        the mean annual flow and the inflow.
        There are three cases:

        1) If the inflow is less than 40% of the mean annual flow,
        the minimum flow is 60% of the inflow.

        2) If the inflow is greater than 80% of the mean annual flow,
        the minimum flow is 30% of the inflow.

        3) Otherwise, the minimum flow is 45% of the inflow.
        """
        self.min_flow = pd.Series(np.nan, index=self.inflow.index)
        for day in range(self.num_days):
            self.min_flow[day] = self._calc_min_environmental_flow(
                self.inflow[day], self.mean_annual_flow[day]
            )

    def calc_target_release_from_target_volume(self) -> None:
        """Calculate the daily release from the reservoir from self.target_volumes.
        The release is in m3/day.
        """
        # The first day was already assumed to have the largest release possible because
        # we begin with a full reservoir.
        self.target_release = [self.max_release]
        for day in range(1, self.num_days):
            # The release should be a positive term,
            # so we switch the order of the subtraction.
            target_release = self.target_storage[day - 1] - self.target_storage[day]

            # Adjust the release to consider hydropeaking
            self.target_release.append(
                adjust_hydropeaking(
                    release=target_release,
                    release_t0=self.target_release[day - 1],
                    max_release=self.max_release,
                    min_release=self.min_flow[day],
                )
            )

    def calc_targets(self) -> None:
        """Simulate hydropower operation while considering the target levels."""
        # Calculate the minimum environmental flow
        self.calc_min_flow()
        # Calculate the target storage and level
        self.calc_target_storage()
        # Calculate the target release
        self.calc_target_release_from_target_volume()

    def build_model(self, start_day: int) -> None:
        """Build an optimization problem to find the optimal release from the reservoir.
        The objective is to minimize the storage deviation from the target storage with L1 norm.
        Also need to minimize the amount of spill.
        """
        self.start_day = start_day
        self.model = gp.Model(f"{self.name}")
        self.model.setParam("OutputFlag", 0)

        # Create the decision variables
        self.release_vars = self.model.addVars(
            range(start_day, self.num_days), lb=0, ub=self.max_release, name="release"
        )
        self.spill_vars = self.model.addVars(
            range(start_day, self.num_days), lb=0, name="spill"
        )
        self.storage_vars = self.model.addVars(
            range(start_day, self.num_days), lb=0, ub=self.max_storage, name="storage"
        )

        """
        We want to minimize the L1 norm of the storage deviation from the target storage.
        This requires refolution of the following optimization problem:

        min | target_storage - storage |

        We can rewrite this as:

        min sum_{day} sbar[day]
        s.t.
        - sbar[day] <= target_storage[day] - storage[day] <= sbar[day]

        """
        sbar = self.model.addVars(range(start_day, self.num_days), lb=0, name="sbar")

        """
        When using max/min as a function, we need to use gp.max_ and gp.min_
        see https://support.gurobi.com/hc/en-us/community/posts/360078185112-gurobipy-Model-addGenConstrMin-Invalid-data-in-vars-array

        spills[day] = max(0, total_inflow[day] + storage[day] - max_storage - release[day])
        spills[day] = gp.max_(0, spill_bar[day])

        with
        spill_bar[day] = total_inflow[day] + storage[day] - max_storage - release[day]
        """

        spill_bar = self.model.addVars(
            range(start_day, self.num_days),
            lb=-gp.GRB.INFINITY,
            name="spill_bar",
        )

        # Create the objective function
        self.model.setObjective(
            gp.quicksum(sbar[day] for day in range(start_day, self.num_days)),
            sense=gp.GRB.MINIMIZE,
        )

        # Lower and upper bounds for the storage deviation are defined by sbar
        self.model.addConstrs(
            (
                -1 * sbar[day] <= self.target_storage[day] - self.storage_vars[day]
                for day in range(start_day, self.num_days)
            ),
            name="c_min_sbar",
        )
        self.model.addConstrs(
            (
                self.target_storage[day] - self.storage_vars[day] <= sbar[day]
                for day in range(start_day, self.num_days)
            ),
            name="c_max_sbar",
        )
        # Maximum and minimum release
        self.model.addConstrs(
            (
                self.release_vars[day] >= self.min_flow[day]
                for day in range(start_day, self.num_days)
            ),
            name="c_min_release",
        )
        self.model.addConstrs(
            (
                self.release_vars[day] <= self.max_release
                for day in range(start_day, self.num_days)
            ),
            name="c_max_release",
        )
        # Spill
        self.model.addConstrs(
            (
                self.spill_vars[day] == gp.max_(0, spill_bar[day])
                for day in range(start_day, self.num_days)
            ),
            name="c_spill",
        )
        # Define spill_bar
        self.model.addConstrs(
            (
                spill_bar[day]
                == self.total_inflow.iloc[day]
                + self.storage_vars[day - 1]
                - self.max_storage
                - self.release_vars[day]
                for day in range(start_day + 1, self.num_days)
            ),
            name="c_define_spill_bar",
        )

        # Storage constraint
        self.model.addConstrs(
            (
                self.storage_vars[day]
                == self.storage_vars[day - 1]
                + self.total_inflow.iloc[day]
                - self.release_vars[day]
                - self.spill_vars[day]
                for day in range(start_day + 1, self.num_days)
            ),
            name="c_storage",
        )

        # # Define initial spill_bar
        # self.model.addConstr(
        #     spill_bar[start_day]
        #     == self.total_inflow.iloc[start_day]
        #     + self.storage_vars[start_day]
        #     - self.max_storage
        #     - self.release_vars[start_day],
        #     name="c_initial_spill_bar",
        # )

        # Define the initial condition for the storage
        self.model.addConstr(
            (
                self.storage_vars[start_day]
                == self.target_storage[start_day]
                + self.total_inflow.iloc[start_day]
                - self.release_vars[start_day]
                - self.spill_vars[start_day]
            ),
            name="c_initial_storage",
        )

    def solve_for_optimal_release(self) -> None:
        # Solve the optimization problem
        self.model.optimize()

        # Check the status of the optimization
        if self.model.status == gp.GRB.INFEASIBLE:
            # Export IIS file if the problem is infeasible
            self.model.computeIIS()
            self.model.write("reservoir.ilp")
            raise Exception(f"Reservoir model is infeasible: {self.name}")

        # Extract the results
        self.release = pd.Series(
            [self.release_vars[day].x for day in range(self.start_day, self.num_days)],
            index=range(self.start_day, self.num_days),
        )
        self.spill = pd.Series(
            [self.spill_vars[day].x for day in range(self.start_day, self.num_days)],
            index=range(self.start_day, self.num_days),
        )
        self.storage = pd.Series(
            [self.storage_vars[day].x for day in range(self.start_day, self.num_days)],
            index=range(self.start_day, self.num_days),
        )

    def calc_level_from_storage(
        self, storage: pd.Series
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate the water level of the reservoir from the storage.
        The water level is calculated as a percentage of the maximum storage.
        """
        level = (
            storage / self.max_storage * (self.max_level - self.min_level)
            + self.min_level
        )
        return level

    def calc_mid_level_from_level(self, level: pd.Series) -> pd.Series:
        # Calculate the change in water level between t and t-1
        mid_level = (level + level.shift(1)) / 2

        # Assume that the mid_level of the first day is just the target level of the first day
        mid_level[0] = self.target_level[0]
        return mid_level

    def calc_head_from_mid_level(self, mid_level: pd.Series) -> pd.Series:
        """Calculate the head of the reservoir from the water level."""
        head = self.max_head - (self.max_level - mid_level)
        return head

    def calc_hydropower_from_mid_level(
        self, release: pd.Series, mid_level: pd.Series
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate the mean hydropower of each day from the change in water level.
        To get the energy, we need to multiply the mean hydropower by
        the number of hours in a day.

        energy = turbine_factor * rho * g * d * flow_rate

        where,
        rho = 998 kg/m3 (density of water)

        To determine the water height above turbine (or head), let h(t) is the water level at time t
        h(t) = storage/max_storage * (max_level - min_level) + min_level

        Rachel's implementation:
        d = max_head - (max_level - ( h(t) + h(t-1) ) / 2)

        let mid_level = ( h(t) + h(t-1) ) / 2
        d = max_head - (max_level - mid_level)

        flow_rate in m3/s

        """
        # The head (d) is adjusted to max_head
        # by scaling water level with respect to max_level.
        d = self.calc_head_from_mid_level(mid_level)

        # The formula requires m3/s not m3/day
        flow_rate = release / (24 * 3600)

        density = 998  # kg/m3
        g = 9.81  # m/s2

        # Calculate the hydropower in Watts
        hydropower = self.turbine_factor * density * g * d * flow_rate
        # Convert to Megawatts
        hydropower = hydropower / 1e6
        # A turbine is limited by its maximum capacity.
        # Any unused water is not routed through the turbine.
        hydropower = np.minimum(hydropower, self.max_generation)
        # Convert to MW-day (energy)
        hydroenergy = hydropower * 24

        return hydropower, hydroenergy

    def simulate(self) -> None:
        """Simulate the operation of the reservoir."""
        self.calc_targets()
        self.build_model(start_day=0)
        self.solve_for_optimal_release()
        self.level = self.calc_level_from_storage(self.storage)
        self.mid_level = self.calc_mid_level_from_level(self.level)
        self.hydropower, self.hydroenergy = self.calc_hydropower_from_mid_level(
            release=self.release, mid_level=self.mid_level
        )

    def reoperate(
        self,
        pownet_dispatch: pd.DataFrame,
    ) -> pd.DataFrame:
        """Reoperate the reservoir based on the daily dispatch of the power system model.
        There are four cases:

        Case 1: If dispatch is equal to original hydroenergy, then check the following
                (a) If the dispatch is less than energy from the max release, then set release to maximum release
                (b) If the dispatch is equal to the max release, then stop reoperation.

        Case 2: If dispatch is less than the original hydroenergy, then check the following
                (a) If dispatch is greater than energy from the min flow, then set release to dispatch
                (b) If dispatch is equal to energy from the min flow, then stop reoperation.

        In this function, t-1 is denoted as t0; t is denoted as t; t+1 is denoted as t1.
        """
        # days start from 0 to 364
        days = pownet_dispatch.index.to_list()
        # We don't reoperate on the first day (or first timestep) because the release is fixed on the first day.
        if 0 in days:
            # Use the first day/step to initialize the reop values
            self.reop_storage = pd.Series(np.nan, index=range(self.num_days))
            self.reop_storage[0] = self.storage[0]

            self.reop_release = pd.Series(np.nan, index=range(self.num_days))
            self.reop_release[0] = self.release[0]

            self.reop_spill = pd.Series(np.nan, index=range(self.num_days))
            self.reop_spill[0] = self.spill[0]

            self.reop_level = self.calc_level_from_storage(self.reop_storage)
            self.reop_mid_level = self.calc_mid_level_from_level(self.reop_level)

            self.reop_hydroenergy = pd.Series(np.nan, index=range(self.num_days))

            return pownet_dispatch

        for day in days:
            # The maximum release (m3/day) based on hydropeaking.
            # Be careful with the units. The reservoir values are in m3/s.
            dispatch_t = pownet_dispatch.loc[day]
            release_t0 = self.reop_release.loc[day - 1]

            if np.isnan(self.reop_hydroenergy[day]):
                previous_hydroenergy_t = self.hydroenergy.loc[day]
            else:
                previous_hydroenergy_t = self.reop_hydroenergy.loc[day]

            # solve_release optimization is not exact, so the hydroenergy
            # can be different from calculated with the formula
            opt_hydroenergy_t = None

            # TODO: Update upstream flow from reoperation too
            # Total inflow already considers upstream flow
            total_inflow_t = self.total_inflow.loc[day]

            storage_t0 = self.reop_storage.loc[day - 1]
            level_t0 = self.calc_level_from_storage(storage_t0)

            ##### Find hydropower from maximum and minimum releases
            ##### to compare with the dispatch

            ###### Maximum release
            # Max release is 15% more than the original release or
            # the maximum release, whichever is smaller.
            max_release_hydropeak_t = release_t0 + self.max_release * 0.15
            max_release_t = min(self.max_release, max_release_hydropeak_t)
            # Release cannot be less than the minimum environmental flow
            max_release_t = max(self.min_flow.loc[day], max_release_t)
            # Release cannot make the storage become negative
            if storage_t0 + total_inflow_t - max_release_t < 0:
                max_release_t = storage_t0 + total_inflow_t

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

            ##### Find the amount of release to produce the same dispatch

            ###### Reoperation
            """ Note that we cannot use release, spill, storage from the original
            because hydropower is a function of the release and storage from the previous day.
            The operations have undoubtedly changed.
            """
            tolerance = 1  # 0.01 * max_hydroenergy_t
            # Case 1b: If dispatch is equal to max hydroenergy, then no need to reoperate
            if math.isclose(dispatch_t, max_hydroenergy_t, abs_tol=tolerance):
                self.reop_release.loc[day] = max_release_t
                self.reop_spill.loc[day] = spill_from_max_release_t
                self.reop_storage[day] = storage_from_max_release_t
                self.reop_level[day] = level_from_max_release_t
                self.reop_hydroenergy.loc[day] = max_hydroenergy_t
                return pownet_dispatch

            # Case 2b: If dispatch is equal to min hydroenergy, then no need to reoperate
            elif math.isclose(dispatch_t, min_hydroenergy_t, abs_tol=tolerance):
                self.reop_release.loc[day] = min_release_t
                self.reop_spill.loc[day] = spill_from_min_release_t
                self.reop_storage.loc[day] = storage_from_min_release_t
                self.reop_level[day] = level_from_min_release_t
                self.reop_hydroenergy.loc[day] = min_hydroenergy_t
                return pownet_dispatch

            # If the dispatch_t is less than the min_hydroenergy_t,
            # then use min_release_t but set new_hydroenergy_t to dispatch_t.
            # This simulates PowNet using less hydroenergy than available hydroenergy.
            elif dispatch_t < min_hydroenergy_t:
                self.reop_release.loc[day] = min_release_t
                self.reop_spill.loc[day] = spill_from_min_release_t
                self.reop_storage.loc[day] = storage_from_min_release_t
                self.reop_level[day] = level_from_min_release_t
                self.reop_hydroenergy.loc[day] = min_hydroenergy_t
                return pownet_dispatch

            # Case 1a: If dispatch is equal to original hydroenergy, then set release to max release
            # to make more hydroenergy available.
            elif math.isclose(dispatch_t, previous_hydroenergy_t, abs_tol=tolerance):
                release_t = max_release_t
                spill_t = max(
                    storage_t0 + total_inflow_t - self.max_storage - release_t,
                    0,
                )

            # Case 2a: If dispatch is less than the original hydroenergy, then
            # set release to dispatch to save water.
            elif dispatch_t < previous_hydroenergy_t:
                (
                    release_t,
                    spill_t,
                    opt_storage,
                    opt_level,
                    opt_hydroenergy_t,
                    z_t,
                    opt_hydropower,
                ) = gp_solve_release(
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

            # # The reservoir may have been reoperated such that
            # # the current timestep has less water than prior to reoperation.
            # # If dispatch is less than the min hydroenergy, then
            # # set release to min release.
            # elif dispatch_t < min_hydroenergy_t:
            #     release_t = min_release_t
            #     spill_t = max(
            #         storage_t0 + total_inflow_t - self.max_storage - release_t,
            #         0,
            #     )

            # Catch any other cases.
            else:
                raise ValueError(
                    f"Unknown case: {dispatch_t} vs. {previous_hydroenergy_t}"
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
        """This class is a collection of Reservoirs on a basin."""
        self.model_name: str = model_name
        self.basin: str = basin
        self.num_days: int = num_days

        self.reservoirs: list[Reservoir] = []
        # Map cascade level to its reservoir {cascade_lvl: reservoir_name}
        self.map_cascade: dict[int, str] = None
        self.max_cascade: int = None

        # Hydropower from each reservoir in the basin
        self.cascade_hydropower: pd.DataFrame = None

    def initialize(self) -> None:
        res_df = pd.read_csv(
            os.path.join(get_model_dir(), self.model_name, "reservoir.csv")
        )
        # Filter the reservoirs by the basin
        res_df = res_df[res_df["basin"] == self.basin]

        self.reservoir_names = res_df["name"].tolist()
        self.max_cascade = res_df["cascade_level"].max()

        if self.basin not in res_df.basin.unique():
            raise ValueError("Basin not found. Check basin name.")

        # Cascade level starts from 0, or the first reservoir
        sub_df = res_df[["cascade_level", "name"]]
        self.map_cascade = {}
        for row in sub_df.itertuples():
            # First check that there is only one reservoir per cascade level
            if row.cascade_level in self.map_cascade:
                raise ValueError("Duplicated cascade level. Check reservoir.csv")
            self.map_cascade[row.cascade_level] = row.name

        self.cascade_hydropower = pd.DataFrame()
        upstream_flow = pd.Series(np.zeros(self.num_days))
        for cas_lvl in range(self.max_cascade + 1):
            res_name = self.map_cascade[cas_lvl]
            # Simulate
            res = Reservoir(
                model_name=self.model_name,
                reservoir_name=res_name,
                num_days=self.num_days,
            )
            upstream_flow = upstream_flow
            res.initialize(upstream_flow=upstream_flow)
            res.simulate()
            self.cascade_hydropower[res.name] = res.hydroenergy
            # Update the upstream flow for the next cascade level
            upstream_flow = upstream_flow + res.release + res.spill

            self.reservoirs.append(res)

    def export_hydropower_csv(self, timestep):
        """Export the hydropower values as an input for the power system model.
        The timestep parameter can be either 'daily' or 'hourly'.
        """
        csv_name = f"pownet_hydropower.csv"
        input_folder = os.path.join(get_model_dir(), self.model_name, csv_name)
        if timestep == "daily":
            self.cascade_hydropower.to_csv(input_folder, index=False)
            return
        elif timestep == "hourly":
            # Repeat the hydropower values for each hour of the day
            df = self.cascade_hydropower.loc[
                self.cascade_hydropower.index.repeat(24)
            ].reset_index(drop=True)

            # Divide the hydropower by 24 to get the hourly values
            df = df / 24
            df.to_csv(input_folder, index=False)
            return
        else:
            raise ValueError("Unknown timestep")

    def get_cascade_hydropower(self, timestep) -> pd.DataFrame:
        """Return a dataframe of hydropower by each reservoir."""
        if timestep == "daily":
            return self.cascade_hydropower
        elif timestep == "hourly":
            # Repeat the hydropower values for each hour of the day
            df = self.cascade_hydropower.loc[
                self.cascade_hydropower.index.repeat(24)
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

        # Map basin to its reservoirs {basin: Basin}
        self.map_basin: dict[str, Basin] = None
        # Store the hydropower timeseries
        self.hydropower: pd.DataFrame = None

    def simulate(self):
        self.hydropower = pd.DataFrame()
        for basin in self.basins:
            basin.initialize()
            self.hydropower = pd.concat(
                [self.hydropower, basin.get_cascade_hydropower(timestep="daily")],
                axis=1,
            )

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
            for res in basin.reservoirs:
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

    def reoperate_basins(self, pownet_dispatch: pd.DataFrame) -> pd.DataFrame:
        """Reoperate the reservoirs based on the daily dispatch of the power system model.
        Note that we don't reoperate on the first day of the simulation period.
        """
        reservoirs = []
        for basin in self.basins:
            for res in basin.reservoirs:
                reservoirs.append(res.name)
        new_hydroenergy = pd.DataFrame(
            np.nan, index=pownet_dispatch.index, columns=reservoirs
        )

        days = pownet_dispatch.index.to_list()
        for basin in self.basins:
            for res in basin.reservoirs:
                res_dispatch = pownet_dispatch[res.name]
                res_hydroenergy = res.reoperate(res_dispatch)
                if isinstance(res_hydroenergy, float):
                    new_hydroenergy.loc[days, res.name] = res_hydroenergy
                elif isinstance(res_hydroenergy, pd.Series):
                    new_hydroenergy.loc[days, res.name] = res_hydroenergy.values
                else:
                    raise ValueError(f"Unknown type {type(res_hydroenergy)}")
        return new_hydroenergy


if __name__ == "__main__":
    # Test the Reservoir class
    model_name = "dummy_hydro"

    # Test the ReservoirOperator class
    res_operator = ReservoirOperator(model_name, num_days=365)
    res_operator.simulate()
    # res_operator.get_plots()
