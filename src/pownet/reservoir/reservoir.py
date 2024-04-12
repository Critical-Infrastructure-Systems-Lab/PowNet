import os

import gurobipy as gp
import pandas as pd
import numpy as np

from pownet.folder_sys import get_model_dir

# Mute gurobi outputs
gp.setParam("OutputFlag", 0)


def adjust_hydropeaking(
    release: float, release_t0: float, max_release: float, min_release: float
) -> float:
    """
    Adjust the release to consider hydropeaking and minimum environmental flow.
    The change in release is limited to 10% of the maximum release.
    Also, the release cannot be lower than the minimum release or higher than the maximum release.
    """
    # Calculate the difference between the current and previous release
    diff_release = release - release_t0
    # Limit the change in release to at most 10% of the maximum release
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
        self.min_flow: float = None  # in m3/s
        self.hydro_energy: pd.Series = None  # in MW-day
        self.hydropower: pd.Series = None  # in MW
        self.reoperated_days: pd.Series = None

        # These policies are calculated based on the min_day and max_day
        self.target_level: list[float] = None  # in meters
        self.target_storage: list[float] = None  # in m3
        self.target_release: list[float] = None  # in m3/day

    def initialize(self, upstream_flow: pd.Series) -> None:
        self.inflow = pd.read_csv(
            os.path.join(get_model_dir(), self.model_name, "inflow.csv")
        )
        # Remove 29th February from the dataset
        self.inflow = self.inflow[~(
            (self.inflow.month == 2) & (self.inflow.day == 29))]
        self.inflow = self.inflow[self.name]

        self.upstream_flow = upstream_flow

        # Add the total inflows
        self.total_inflow = self.inflow + self.upstream_flow

        # Mean annual flow was previously calculated
        self.mean_annual_flow = pd.read_csv(
            os.path.join(get_model_dir(), self.model_name,
                         "mean_annual_flow.csv")
        )
        # Remove 29th February from the dataset
        self.mean_annual_flow = self.mean_annual_flow[
            ~((self.mean_annual_flow.month == 2)
              & (self.mean_annual_flow.day == 29))
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
        ''' Minimum environmental flow is a relative value based on the mean annual flow and the inflow.
        '''
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
            target_release = self.target_storage[day -
                                                 1] - self.target_storage[day]

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

    def solve_for_optimal_release(self) -> None:
        """Solve the optimization problem to find the optimal release from the reservoir.
        The objective is to minimize the storage deviation from the target storage with L1 norm.
        Also need to minimize the amount of spill.
        """
        model = gp.Model("reservoir")
        # Create the decision variables
        # Gurobipy indexing starts at 1
        releases = model.addVars(
            self.num_days, lb=0, ub=self.max_release, name="release"
        )
        spills = model.addVars(self.num_days, lb=0, name="spill")
        storages = model.addVars(
            self.num_days, lb=0, ub=self.max_storage, name="storage"
        )

        """
        We want to minimize the L1 norm of the storage deviation from the target storage.
        This requires refolution of the following optimization problem:

        min | target_storage - storage | + spill

        We can rewrite this as:

        min sum_{day} (sbar[day] + spill[day])
        s.t.
        - sbar[day] <= target_storage[day] - storage[day] <= sbar[day]

        """
        sbar = model.addVars(self.num_days, lb=0, name="sbar")

        """
        When using max/min as a function, we need to use gp.max_ and gp.min_
        see https://support.gurobi.com/hc/en-us/community/posts/360078185112-gurobipy-Model-addGenConstrMin-Invalid-data-in-vars-array

        spills[day] = max(0, total_inflows[day] + storages[day] - max_storage)
        spills[day] = gp.max_(0, spills_bar[day])

        with
        spill_bar[day] = total_inflows[day] + \
            storages[day] - max_storage - releases[day]
        """

        spill_bar = model.addVars(
            self.num_days,
            lb=-gp.GRB.INFINITY,
            name="spill_bar",
        )

        # Create the objective function
        model.setObjective(
            gp.quicksum(((sbar[day] + spills[day])
                        for day in range(self.num_days))),
            sense=gp.GRB.MINIMIZE,
        )

        # Lower and upper bounds for the storage deviation are defined by sbar
        model.addConstrs(
            (
                -1 * sbar[day] <= self.target_storage[day] - storages[day]
                for day in range(self.num_days)
            ),
            name="c_min_sbar",
        )
        model.addConstrs(
            (
                self.target_storage[day] - storages[day] <= sbar[day]
                for day in range(self.num_days)
            ),
            name="c_max_sbar",
        )
        # Maximum and minimum release
        model.addConstrs(
            (releases[day] >= self.min_flow[day]
             for day in range(self.num_days)),
            name="c_min_release",
        )
        model.addConstrs(
            (releases[day] <= self.max_release for day in range(self.num_days)),
            name="c_max_release",
        )
        # Spill
        model.addConstrs(
            (spills[day] == gp.max_(0, spill_bar[day])
             for day in range(self.num_days)),
            name="c_spill",
        )
        # Define spill_bar
        model.addConstrs(
            (
                spill_bar[day]
                == self.total_inflow.iloc[day]
                + storages[day - 1]
                - self.max_storage
                - releases[day]
                for day in range(1, self.num_days)
            ),
            name="c_define_spill_bar",
        )

        # Define initial spill_bar
        model.addConstr(
            spill_bar[0]
            == self.total_inflow.iloc[0] + storages[0] - self.max_storage - releases[0],
            name="c_initial_spill_bar",
        )

        # Storage constraint
        model.addConstrs(
            (
                storages[day]
                == storages[day - 1]
                + self.total_inflow.iloc[day]
                - releases[day]
                - spills[day]
                for day in range(1, self.num_days)
            ),
            name="c_storage",
        )

        # Define the initial condition for the storage
        model.addConstr(
            (
                storages[0]
                == self.target_storage[0]
                + self.total_inflow.iloc[0]
                - releases[0]
                - spills[0]
            ),
            name="c_initial_storage",
        )

        # Solve the optimization problem
        model.optimize()

        # Check the status of the optimization
        if model.status == gp.GRB.INFEASIBLE:
            # Export IIS file if the problem is infeasible
            model.computeIIS()
            model.write("reservoir.ilp")
            raise Exception(f"Reservoir model is infeasible: {self.name}")

        # Extract the results
        self.release = pd.Series(
            [releases[day].x for day in range(self.num_days)],
            index=range(self.num_days),
        )
        self.spill = pd.Series(
            [spills[day].x for day in range(self.num_days)], index=range(self.num_days)
        )
        self.storage = pd.Series(
            [storages[day].x for day in range(self.num_days)],
            index=range(self.num_days),
        )

    def calc_levels_from_storage(self) -> None:
        """Calculate the water level of the reservoir from the storage.
        The water level is calculated as a percentage of the maximum storage.
        """
        self.level = (
            self.storage / self.max_storage * (self.max_level - self.min_level)
            + self.min_level
        )

        # Calculate the change in water level between t and t+1
        self.mid_level = (self.level + self.level.shift(-1)) / 2

        # Assume that the mid_level of the last day is the same as the level
        # of the last day. The slightly more head is not expected to generate
        # too much hydropower that affects the outcome.
        self.mid_level.iloc[-1] = self.level.iloc[-1]

    def calc_hydropower_from_level(self) -> None:
        """Calculate the mean hydropower of each day from the change in water level.
        To get the energy, we need to multiply the mean hydropower by
        the number of hours in a day.

        energy = turbine_factor * rho * g * d * flow_rate

        where,
        rho = 998 kg/m3 (density of water)

        To determine the water height (or head), let h(t) is the water level at time t
        h(t) = storage/max_storage * (max_level - min_level) + min_level

        Rachel's implementation:
        d = max_head - (max_level - ( h(t) + h(t+1) ) / 2)
        let mid_levels = ( h(t) + h(t+1) ) / 2
        d = max_head - (max_level - mid_levels)

        flow_rate in m3/s

        """
        # The water height (d) is adjusted to max_head
        # by scaling water level with respect to max_level.
        d = self.max_head - (self.max_level - self.mid_level)

        # The formula requires m3/s not m3/day
        flow_rate = self.release / (24 * 3600)

        density = 998  # kg/m3
        g = 9.81  # m/s2

        # Calculate the hydropower in Watts
        self.hydropower = self.turbine_factor * density * g * d * flow_rate
        # Convert to Megawatts
        self.hydropower = self.hydropower / 1e6
        # A turbine is limited by its maximum capacity.
        # Any unused water is not routed through the turbine.
        self.hydropower = np.minimum(self.hydropower, self.max_generation)

        # Convert to MW-day (energy)
        self.hydro_energy = self.hydropower * 24

    def simulate(self) -> None:
        """Simulate the operation of the reservoir."""
        self.calc_targets()
        self.solve_for_optimal_release()
        self.calc_levels_from_storage()
        self.calc_hydropower_from_level()


class Basin:
    def __init__(
        self,
        model_name: str,
        basin: str,
        num_days: int,
    ) -> None:
        ''' This class is a collection of Reservoirs on a basin.
        '''
        self.model_name: str = model_name
        self.basin: str = basin
        self.num_days: int = num_days

        self.reservoirs: list[Reservoir] = None
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
                raise ValueError(
                    "Duplicated cascade level. Check reservoir.csv")
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

            res.initialize(upstream_flow=upstream_flow)
            res.simulate()
            self.cascade_hydropower[res.name] = res.hydro_energy
            # Update the upstream flow for the next cascade level
            upstream_flow = upstream_flow + res.release + res.spill

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
        ''' Return a dataframe of hydropower by each reservoir.
        '''
        if timestep == "daily":
            return self.cascade_hydropower
        elif timestep == "hourly":
            # Repeat the hydropower values for each hour of the day
            df = self.cascade_hydropower.loc[
                self.cascade_hydropower.index.repeat(24)
            ].reset_index(drop=True)
            df = df/24
            return df
        else:
            raise ValueError("Unknown timestep")


class ReservoirOperator:
    def __init__(
        self,
        model_name: str,
        num_days: int,
    ) -> None:
        ''' A class that manages the operation of multiple basins.
        '''
        self.model_name: str = model_name
        self.num_days: int = num_days

        self.basin_names: list[str] = pd.read_csv(
            os.path.join(get_model_dir(), model_name, "reservoir.csv"),
            header=0)['basin'].unique().tolist()

        self.basins: list[Basin] = [
            Basin(model_name, basin, num_days) for basin in self.basin_names]

        # Map basin to its reservoirs {basin: Basin}
        self.map_basin: dict[str, Basin] = None
        # Store the hydropower timeseries
        self.hydropower: pd.DataFrame = None

    def simulate(self):
        self.hydropower = pd.DataFrame()
        for basin in self.basins:
            basin.initialize()
            self.hydropower = pd.concat(
                [
                    self.hydropower,
                    basin.get_cascade_hydropower(timestep="daily")
                ],
                axis=1,
            )

    def get_hydropower(self) -> pd.DataFrame:
        return self.hydropower

    def export_hydropower_csv(self, timestep: str) -> None:
        csv_name = f"pownet_hydropower.csv"
        input_folder = os.path.join(get_model_dir(), self.model_name, csv_name)
        if timestep == "daily":
            self.hydropower.to_csv(input_folder, index=False)
            return
        elif timestep == "hourly":
            # Repeat the hydropower values for each hour of the day
            df = self.hydropower.loc[
                self.hydropower.index.repeat(24)
            ].reset_index(drop=True)
            df = df/24
            df.to_csv(input_folder, index=False)
            return
        else:
            raise ValueError("Unknown timestep")


if __name__ == "__main__":
    # Test the Reservoir class
    model_name = "dummy_hydro"

    # Test the ReservoirOperator class
    res_operator = ReservoirOperator(model_name, num_days=365)
    res_operator.simulate()
    res_operator.get_hydropower()
    hydropower = res_operator.get_hydropower()
    res_operator.export_hydropower_csv(timestep="hourly")
