""" reservoir.py: This module contains classes to simulate the operation of a reservoir.
"""

import math
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from pownet.data_utils import remove_29feb
from pownet.folder_utils import get_model_dir, get_reservoir_file
from .solve_release import (
    solve_release_from_target_storage,
    solve_release_from_dispatch,
)
from .reservoir_functions import (
    calc_min_flow,
    calc_target_level,
    calc_target_storage,
    calc_level_from_storage,
    calc_daily_hydropower,
    calc_release_impact,
    calc_max_release,
    calc_min_release,
    convert_to_hourly_hydropower,
)


class Reservoir:
    """This class simulates a reservoir."""

    def __init__(
        self,
        model_name: str,
        reservoir_name: str,
        upstream_flow: pd.Series = None,
        sim_horizon: int = 365,
    ) -> None:

        # Number of days in a year
        self.sim_horizon = sim_horizon

        self.model_name: str = model_name
        self.name: str = reservoir_name

        # Upstream flow
        self.upstream_flow: pd.Series = None
        if upstream_flow is not None:
            self.set_upstream_flow(upstream_flow)
        else:
            self.upstream_flow: pd.Series = pd.Series(
                0, index=range(1, self.sim_horizon + 1)
            )

        ############################
        # Loaded parameters from CSV
        ############################

        self.min_day: int = None
        self.max_day: int = None
        self.min_level: float = None  # in meters
        self.max_level: float = None  # in meters

        # Max head is the maximum distance between the water level and turbine
        self.max_head: float = None  # in meters
        self.max_storage: float = None  # in m3
        self.max_release: float = None  # in m3/day
        # Max generation is power in MW
        self.max_generation: float = None
        # Index of the reservoir's cascade level. Zero is the furthest upstream.
        self.cascade_level: int = None
        # Turbine efficiency
        self.turbine_factor: float = None

        self.inflow: pd.Series = None  # in m3/day
        self.mean_annual_flow: pd.Series = None  # in m3/day

        ############################
        # Simulated values
        ############################

        self.level: pd.Series = None  # in meters
        # The mid_level is the average of the level of the current day and the next day
        self.mid_level: pd.Series = None  # in meters
        self.storage: pd.Series = None  # in m3
        self.release: pd.Series = None  # in m3/day
        self.spill: pd.Series = None  # in m3/day
        self.min_flow: float = None  # in m3/day
        self.daily_hydropower: pd.Series = None  # in MW-day

        # These policies are calculated based on the min_day and max_day
        self.target_level: pd.Series = None  # in meters
        self.target_storage: pd.Series = None  # in m3

        ############################
        # Reoperated values
        ############################

        self.reop_upstream_flow: pd.Series = pd.Series(
            np.nan, index=range(1, self.sim_horizon + 1)
        )
        self.reop_storage: pd.Series = pd.Series(
            np.nan, index=range(1, self.sim_horizon + 1)
        )
        self.reop_release: pd.Series = pd.Series(
            np.nan, index=range(1, self.sim_horizon + 1)
        )
        self.reop_spill: pd.Series = pd.Series(
            np.nan, index=range(1, self.sim_horizon + 1)
        )
        self.reop_level: pd.Series = pd.Series(
            np.nan, index=range(1, self.sim_horizon + 1)
        )
        self.reop_daily_hydropower: pd.Series = pd.Series(
            np.nan, index=range(1, self.sim_horizon + 1)
        )

    def set_upstream_flow(self, upstream_flow: pd.Series) -> None:
        """Set the upstream flow of the reservoir."""
        # Check the index of upstream_flow is between 1 and sim_horizon
        if (upstream_flow.index[0] != 1) or (
            upstream_flow.index[-1] != self.sim_horizon
        ):
            raise ValueError("Index of upstream flow should be in [1, 365].")
        # Length of upstream flow should be equal to the simulation horizon
        if len(upstream_flow) != self.sim_horizon:
            raise ValueError(
                "Length of upstream flow should be equal to the simulation horizon."
            )
        self.upstream_flow = upstream_flow

    def load_flows(self) -> None:
        """Load inflow and mean annual flow from CSV files.
        The files are located in model_library/model_name/reservoir/.
        """
        # Inflow (m3/day)
        inflow_data = pd.read_csv(
            get_reservoir_file(model_name=self.model_name, filename="inflow.csv")
        )
        self.inflow = remove_29feb(inflow_data)
        self.inflow = self.inflow[self.name]

        # Mean annual flow (m3/day)
        mean_annual_flow_data = pd.read_csv(
            get_reservoir_file(
                model_name=self.model_name, filename="mean_annual_flow.csv"
            )
        )
        self.mean_annual_flow = remove_29feb(mean_annual_flow_data)
        self.mean_annual_flow = self.mean_annual_flow[self.name]

    def load_reservoir_params(self) -> None:
        """Load reservoir parameters from reservoir.csv."""
        reservoir_params = (
            pd.read_csv(
                os.path.join(
                    get_model_dir(), self.model_name, "reservoir", "reservoir.csv"
                ),
                header=0,
            )
            .set_index("name")
            .loc[self.name]
        )
        self.min_day = int(reservoir_params["min_day"])
        self.max_day = int(reservoir_params["max_day"])
        self.min_level = reservoir_params["min_level"]
        self.max_level = reservoir_params["max_level"]
        self.max_head = reservoir_params["max_head"]
        self.max_storage = reservoir_params["max_storage"]
        self.max_release = reservoir_params["max_release"]
        self.max_generation = reservoir_params["max_generation"]
        self.cascade_level = reservoir_params["cascade_level"]
        self.turbine_factor = reservoir_params["turbine_factor"]

    def load_from_csv(
        self,
    ) -> None:
        """Load reservoir parameters from /model_name/reservoir/reservoir.csv.

        Args:
            model_name (str): The name of the model
            reservoir_name (str): The name of the reservoir
            upstream_flow (pd.Series): The inflow from upstream reservoirs

        Returns:
            None
        """
        self.load_flows()
        self.load_reservoir_params()

    def simulate(self):
        """Simulate the operation of the reservoir."""
        # Minimum flow
        self.min_flow = calc_min_flow(
            inflow=self.inflow,
            mean_annual_flow=self.mean_annual_flow,
            max_release=self.max_release,
        )
        # Calculate the target storage and level
        self.target_level = calc_target_level(
            min_day=self.min_day,
            max_day=self.max_day,
            min_level=self.min_level,
            max_level=self.max_level,
        )
        self.target_storage = calc_target_storage(
            target_level=self.target_level,
            min_level=self.min_level,
            max_level=self.max_level,
            max_storage=self.max_storage,
        )

        # Get reservoir timeseries values
        self.release, self.spill, self.storage, _ = solve_release_from_target_storage(
            reservoir_name=self.name,
            start_day=1,
            end_day=self.sim_horizon,
            max_release=self.max_release,
            max_storage=self.max_storage,
            initial_storage=self.target_storage[
                1
            ],  # Assume the initial storage is the target storage of the first day
            target_storage=self.target_storage,
            min_flow=self.min_flow,
            total_inflow=self.inflow + self.upstream_flow,
        )

        self.level = calc_level_from_storage(
            storage=self.storage,
            min_level=self.min_level,
            max_level=self.max_level,
            max_storage=self.max_storage,
        )

        self.mid_level = (self.level + self.level.shift(1)) / 2
        # Assume the mid_level of the first day is the target level of the first day
        self.mid_level[1] = self.target_level[1]

        self.daily_hydropower = calc_daily_hydropower(
            release=self.release,
            mid_level=self.mid_level,
            max_generation=self.max_generation,
            turbine_factor=self.turbine_factor,
            max_head=self.max_head,
            max_level=self.max_level,
        )

    def reoperate(
        self, day: int, daily_dispatch: float, upstream_flow: float
    ) -> pd.DataFrame:
        """Reoperate the reservoir based on the daily dispatch of the power system model.
        There are seven cases which are outlined in the code.
        Note t-1 is denoted as t0; t is denoted as t; t+1 is denoted as t1.

        Args:
            day (int): The current day for which the reoperation is being calculated.
            daily_dispatch (float): The daily dispatch value from the power system model.
            upstream_flow (float): The flow of water from upstream.

        Returns:
            pd.DataFrame: A DataFrame containing the reoperation results for the reservoir.
        """
        # Upstream flow may change every reoperation iteration because
        # reservoirs located upstream may reoperate.
        self.reop_upstream_flow.loc[day] = upstream_flow

        # Since release is fixed on the first day, we do not reoperate and
        # return the original dispatch.
        if day == 1:
            self.reop_release.loc[day] = self.release.loc[day]
            self.reop_spill.loc[day] = self.spill.loc[day]
            self.reop_storage.loc[day] = self.storage.loc[day]
            self.reop_level.loc[day] = calc_level_from_storage(
                storage=self.reop_storage.loc[day],
                min_level=self.min_level,
                max_level=self.max_level,
                max_storage=self.max_storage,
            )
            self.reop_daily_hydropower.loc[day] = self.daily_hydropower.loc[day]
            return daily_dispatch

        # Values for calculations are from previous reoperation attemps
        total_inflow_t = self.inflow.loc[day] + upstream_flow
        release_t0 = self.reop_release.loc[day - 1]
        storage_t0 = self.reop_storage.loc[day - 1]
        level_t0 = calc_level_from_storage(
            storage=storage_t0,
            min_level=self.min_level,
            max_level=self.max_level,
            max_storage=self.max_storage,
        )
        min_flow_t = self.min_flow.loc[day]

        #########################################################
        ##### Max release and its corresponding values
        #########################################################
        # Change in release is limited to 15% of the maximum release
        hydropeak_factor = 0.15
        max_release_t = calc_max_release(
            total_inflow_t=total_inflow_t,
            release_t0=release_t0,
            storage_t0=storage_t0,
            min_flow_t=min_flow_t,
            max_release=self.max_release,
            hydropeak_factor=hydropeak_factor,
        )
        # Reservoir state due to max_release_t
        (
            spill_from_max_release_t,
            storage_from_max_release_t,
            level_from_max_release_t,
            max_daily_hydropower_t,
        ) = calc_release_impact(
            release_t=max_release_t,
            storage_t0=storage_t0,
            total_inflow_t=total_inflow_t,
            min_level=self.min_level,
            max_level=self.max_level,
            max_storage=self.max_storage,
            level_t0=level_t0,
            max_generation=self.max_generation,
            turbine_factor=self.turbine_factor,
            max_head=self.max_head,
        )

        #########################################################
        ##### Min release and its corresponding values
        #########################################################
        min_release_t = calc_min_release(
            total_inflow_t=total_inflow_t,
            release_t0=release_t0,
            storage_t0=storage_t0,
            min_flow_t=min_flow_t,
            max_release=self.max_release,
            hydropeak_factor=hydropeak_factor,
        )
        # Reservoir state due to min_release_t
        (
            spill_from_min_release_t,
            storage_from_min_release_t,
            level_from_min_release_t,
            min_daily_hydropower_t,
        ) = calc_release_impact(
            release_t=min_release_t,
            storage_t0=storage_t0,
            total_inflow_t=total_inflow_t,
            min_level=self.min_level,
            max_level=self.max_level,
            max_storage=self.max_storage,
            level_t0=level_t0,
            max_generation=self.max_generation,
            turbine_factor=self.turbine_factor,
            max_head=self.max_head,
        )

        ##############################
        ##### Reoperation cases
        ##############################

        # Define the previous guesses of daily_hydropower
        daily_hydropower_rule_curve = self.daily_hydropower.loc[day]
        previous_reop_daily_hydropower = self.reop_daily_hydropower.loc[day]

        # Two values are equal when they are within 0.1% of daily max capacity (MW-day)
        tolerance = 0.001 * self.max_generation * 24

        # Case 1: If dispatch is equal to the previous guess from reoperation,
        # then terminate.
        if math.isclose(
            daily_dispatch, previous_reop_daily_hydropower, abs_tol=tolerance
        ):
            return daily_dispatch

        # Case 2: If dispatch is equal to min daily_hydropower,
        # set release to min release
        elif math.isclose(daily_dispatch, min_daily_hydropower_t, abs_tol=tolerance):
            self.reop_release.loc[day] = min_release_t
            self.reop_spill.loc[day] = spill_from_min_release_t
            self.reop_storage.loc[day] = storage_from_min_release_t
            self.reop_level.loc[day] = level_from_min_release_t
            self.reop_daily_hydropower.loc[day] = min_daily_hydropower_t
            return daily_dispatch

        # Case 3: If dispatch is equal to max daily_hydropower,
        # set release to max release.
        elif math.isclose(daily_dispatch, max_daily_hydropower_t, abs_tol=tolerance):
            self.reop_release.loc[day] = max_release_t
            self.reop_spill.loc[day] = spill_from_max_release_t
            self.reop_storage.loc[day] = storage_from_max_release_t
            self.reop_level.loc[day] = level_from_max_release_t
            self.reop_daily_hydropower.loc[day] = max_daily_hydropower_t
            return daily_dispatch

        # Case 4: Release cannot be less than the minimum flow.
        # Likewise, set release to min release.
        elif daily_dispatch < min_daily_hydropower_t:
            self.reop_release.loc[day] = min_release_t
            self.reop_spill.loc[day] = spill_from_min_release_t
            self.reop_storage.loc[day] = storage_from_min_release_t
            self.reop_level.loc[day] = level_from_min_release_t
            self.reop_daily_hydropower.loc[day] = min_daily_hydropower_t
            # Return the original dispatch to get convergence
            # for the reoperation
            return min_daily_hydropower_t

        # Case 5: Dismatch cannot be greater than max daily_hydropower,
        # therefore set release to its maximum value.
        elif daily_dispatch > max_daily_hydropower_t:
            self.reop_release.loc[day] = max_release_t
            self.reop_spill.loc[day] = spill_from_max_release_t
            self.reop_storage.loc[day] = storage_from_max_release_t
            self.reop_level.loc[day] = level_from_max_release_t
            self.reop_daily_hydropower.loc[day] = max_daily_hydropower_t
            return max_daily_hydropower_t

        # Case 6: If the reoperation is the first iteration, dispatch can be
        # limited by the rule curve. Therefore, the new estimated release
        # should be the maximum release to bypass the limit.
        elif math.isclose(
            daily_dispatch,
            daily_hydropower_rule_curve,
            abs_tol=tolerance,
        ):
            self.reop_release.loc[day] = max_release_t
            self.reop_spill.loc[day] = spill_from_max_release_t
            self.reop_storage.loc[day] = storage_from_max_release_t
            self.reop_level.loc[day] = level_from_max_release_t
            self.reop_daily_hydropower.loc[day] = max_daily_hydropower_t
            return max_daily_hydropower_t

        # Case 7: If dispatch is between min_daily_hydropower and max_daily_hydropower,
        # then solve for release from dispatch using an optimization algorithm.
        elif min_daily_hydropower_t < daily_dispatch < max_daily_hydropower_t:
            (
                reop_release_t,
                reop_spill_t,
                reop_storage_t,
                reop_level_t,
                reop_hourly_hydropower_t,
                reop_daily_hydropower_t,
                reop_mismatch_t,
            ) = solve_release_from_dispatch(
                reservoir_name=self.name,
                dispatch=daily_dispatch,
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
            )

            ##############################
            # Ensure that equations in the optimization problem
            # are correct by comparing the results with values
            # from manual calculations.
            ##############################
            (
                _,
                temp_storage,
                temp_level,
                temp_daily_hydropower,
            ) = calc_release_impact(
                release_t=reop_release_t,
                storage_t0=storage_t0,
                total_inflow_t=total_inflow_t,
                min_level=self.min_level,
                max_level=self.max_level,
                max_storage=self.max_storage,
                level_t0=level_t0,
                max_generation=self.max_generation,
                turbine_factor=self.turbine_factor,
                max_head=self.max_head,
            )

            comparisons = [
                (temp_storage, reop_storage_t),
                (temp_level, reop_level_t),
                (temp_daily_hydropower, reop_daily_hydropower_t),
            ]
            if not all(math.isclose(a, b, rel_tol=tolerance) for a, b in comparisons):
                raise ValueError("Optimization did not produce the correct values.")

            # Update the reoperation values
            self.reop_release.loc[day] = reop_release_t
            self.reop_spill.loc[day] = reop_spill_t
            self.reop_storage.loc[day] = reop_storage_t
            self.reop_level.loc[day] = reop_level_t
            self.reop_daily_hydropower.loc[day] = reop_daily_hydropower_t
            return reop_daily_hydropower_t

        # Catch other cases.
        else:
            raise ValueError(
                f"Unknown case: {daily_dispatch} vs. {daily_hydropower_rule_curve}"
            )

    def plot_state(self, output_folder: str = None) -> None:
        fig, ax = plt.subplots(figsize=(13, 7), layout="constrained", dpi=350)
        ax.plot(self.inflow + self.upstream_flow, label="Inflow (m3/day)")
        ax.plot(self.release, label="Release (m3/day)")
        ax.plot(self.spill, label="Spill (m3/day)", linestyle="dotted", linewidth=2)
        ax.plot(
            self.release + self.spill,
            label="Outflow (m3/day)",
            linestyle="dotted",
        )
        ax.set_xlabel("Day")
        ax.set_ylabel("Flow rate (m3/day)")
        ax.set_title(self.name)

        ax2 = ax.twinx()
        ax2.plot(self.storage, label="Storage (m3)", color="k", linewidth=1)
        ax2.plot(
            self.target_storage,
            label="Target Storage (m3)",
            linestyle="--",
            color="k",
            linewidth=5,
            alpha=0.5,
        )
        ax2.set_ylabel("Storage (m3)")
        fig.legend(loc="outside right upper")

        # Save figure
        if output_folder is not None:
            fig.savefig(os.path.join(output_folder, f"{self.name}.png"))

        plt.show()

    def get_hourly_hydropower(self) -> pd.Series:
        return convert_to_hourly_hydropower(self.daily_hydropower)

    def get_daily_hydropower(self) -> pd.Series:
        """Return the daily hydropower values."""
        return self.daily_hydropower

    def get_reop_daily_hydropower(self) -> pd.Series:
        """Return the reoperated daily hydropower values."""
        return self.reop_daily_hydropower
