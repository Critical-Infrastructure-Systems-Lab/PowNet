"""reservoir.py: Reservoir class"""

import math
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..data_model import ReservoirParams

from .solve_release import (
    solve_release_from_target_storage,
    solve_release_from_dispatch,
)
from .reservoir_functions import (
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
    """
    Simulates the operation of a single reservoir, initialized using ReservoirParams.
    The simulation horizon is set to 365 days with a daily time step.
    """

    def __init__(self, params: ReservoirParams) -> None:
        """
        Initialize the Reservoir object.

        Args:
            params: A dataclass instance containing all static parameters
                              and initial inflow timeseries for the reservoir.
        """
        self.sim_days = 365  # days in a year
        self._time_index = pd.RangeIndex(start=1, stop=self.sim_days + 1, step=1)

        # --- Unpack parameters from the dataclass ---
        self.name: str = params.name
        self.min_day: int = params.min_day
        self.max_day: int = params.max_day
        self.min_level: float = params.min_level
        self.max_level: float = params.max_level
        self.max_head: float = params.max_head
        self.max_storage: float = params.max_storage
        self.max_release: float = params.max_release
        self.max_generation: float = params.max_generation
        self.turbine_factor: float = params.turbine_factor

        self.upstream_units: list[str] = params.upstream_units
        self.downstream_flow_fracs: dict[str, float] = params.downstream_flow_fracs

        # --- Set timeseries data ---
        self.inflow_ts: pd.Series = params.inflow_ts
        self.minflow_ts: pd.Series = params.minflow_ts

        # --- Initialize upstream flow (can be set later) ---
        self.outflow: pd.Series = pd.Series(0.0, index=self._time_index, dtype=float)

        # --- Initialize calculated/simulated state variables ---
        self.level: pd.Series = pd.Series(np.nan, index=self._time_index, dtype=float)
        self.mid_level: pd.Series = pd.Series(
            np.nan, index=self._time_index, dtype=float
        )
        self.storage: pd.Series = pd.Series(np.nan, index=self._time_index, dtype=float)
        self.release: pd.Series = pd.Series(np.nan, index=self._time_index, dtype=float)
        self.spill: pd.Series = pd.Series(np.nan, index=self._time_index, dtype=float)

        self.daily_hydropower: pd.Series = pd.Series(
            np.nan, index=self._time_index, dtype=float
        )
        self.target_level: pd.Series = pd.Series(
            np.nan, index=self._time_index, dtype=float
        )
        self.target_storage: pd.Series = pd.Series(
            np.nan, index=self._time_index, dtype=float
        )

        # --- Initialize re-operation state variables ---
        self.reop_upstream_flow: pd.Series = pd.Series(
            np.nan, index=self._time_index, dtype=float
        )
        self.reop_storage: pd.Series = pd.Series(
            np.nan, index=self._time_index, dtype=float
        )
        self.reop_release: pd.Series = pd.Series(
            np.nan, index=self._time_index, dtype=float
        )
        self.reop_spill: pd.Series = pd.Series(
            np.nan, index=self._time_index, dtype=float
        )
        self.reop_level: pd.Series = pd.Series(
            np.nan, index=self._time_index, dtype=float
        )
        self.reop_daily_hydropower: pd.Series = pd.Series(
            np.nan, index=self._time_index, dtype=float
        )

    def set_upstream_flow(self, upstream_flow: pd.Series) -> None:
        """Set the upstream flow for the reservoir.

        Args:
            upstream_flow (pd.Series): The upstream flow for the reservoir.

        Raises:
            ValueError: If the upstream flow is negative or if the index is not in the expected range.

        """
        # Check if the index matches the expected range [1, sim_horizon]
        expected_index = pd.RangeIndex(start=1, stop=self.sim_days + 1, step=1)
        if not upstream_flow.index.equals(expected_index):
            # Provide a more informative error message if possible
            idx_min = upstream_flow.index.min()
            idx_max = upstream_flow.index.max()
            idx_len = len(upstream_flow.index)
            raise ValueError(
                f"Index of upstream_flow is invalid for reservoir '{self.name}'. "
                f"Expected index from 1 to {self.sim_days} (Length: {self.sim_days}), "
                f"but received index from {idx_min} to {idx_max} (Length: {idx_len})."
            )

        if (upstream_flow < 0).any():
            raise ValueError("Upstream flow cannot be negative.")

        self.upstream_flow = upstream_flow

    def simulate(self, initial_storage: float = None) -> None:
        """Simulate the operation of the reservoir. This method calculates the release,
        spill, storage, level, and daily hydropower.
        """
        # Target level
        self.target_level = calc_target_level(
            min_day=self.min_day,
            max_day=self.max_day,
            min_level=self.min_level,
            max_level=self.max_level,
        )
        # Target storage
        self.target_storage = calc_target_storage(
            target_level=self.target_level,
            min_level=self.min_level,
            max_level=self.max_level,
            max_storage=self.max_storage,
        )

        # Simulate the reservoir operation to extract the release, spill, and storage
        # Assume the initial storage equals to the target storage in the first day

        if initial_storage is None:
            initial_storage = self.target_storage[1]

        self.release, self.spill, self.storage, _ = solve_release_from_target_storage(
            reservoir_name=self.name,
            start_day=1,
            end_day=self.sim_days,
            max_release=self.max_release,
            max_storage=self.max_storage,
            initial_storage=initial_storage,
            target_storage=self.target_storage,
            minflow=self.minflow_ts,
            total_inflow=self.inflow_ts + self.upstream_flow,
        )

        # Calculate the level of the reservoir based on the storage
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
        self,
        day: int,
        daily_dispatch: float,
        upstream_flow_t: float,
        hydropeak_factor: float = 0.15,
    ) -> float:
        """Reoperate the reservoir based on the daily dispatch of the power system model.
        There are seven cases which are outlined in the code.
        Note t-1 is denoted as t0; t is denoted as t; t+1 is denoted as t1.

        Args:
            day (int): The current day for which the reoperation is being calculated.
            daily_dispatch (float): The daily dispatch value from the power system model.
            upstream_flow (float): The flow of water from upstream.
            hydropeak_factor (float): The hydropeak factor for the reservoir.

        Returns:
            float: New daily hydropower value after reoperation.
        """
        # Upstream flow may change every reoperation iteration because
        # reservoirs located upstream may reoperate.
        self.reop_upstream_flow.loc[day] = upstream_flow_t

        # Since release is fixed on the first day, we do not reoperate and
        # return the original dispatch.
        if day == 1:
            self.reop_release.loc[day] = self.release.loc[day]
            self.reop_spill.loc[day] = self.spill.loc[day]
            self.reop_storage.loc[day] = self.storage.loc[day]
            self.reop_level.loc[day] = self.level.loc[day]
            self.reop_daily_hydropower.loc[day] = self.daily_hydropower.loc[day]
            return daily_dispatch

        total_inflow_t = self.inflow_ts.loc[day] + upstream_flow_t
        minflow_t = self.minflow_ts.loc[day]

        # Previous values of release, storage, and level determine
        # the ability to reoperate the reservoir
        release_t0 = self.reop_release.loc[day - 1]
        storage_t0 = self.reop_storage.loc[day - 1]
        level_t0 = self.reop_level.loc[day - 1]

        #########################################################
        ##### Max release and its corresponding values
        #########################################################

        max_release_t = calc_max_release(
            total_inflow_t=total_inflow_t,
            release_t0=release_t0,
            storage_t0=storage_t0,
            minflow_t=minflow_t,
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
            minflow_t=minflow_t,
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
                daily_dispatch=daily_dispatch,
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

    def get_hourly_hydropower(self) -> pd.Series:
        return convert_to_hourly_hydropower(self.daily_hydropower)

    def get_daily_hydropower(self) -> pd.Series:
        """Return the daily hydropower values."""
        return self.daily_hydropower

    def get_operation_timeseries(self) -> pd.DataFrame:
        """Return the timeseries of the reservoir."""
        return pd.DataFrame(
            {
                "total_inflow": self.inflow_ts + self.upstream_flow,
                "release": self.release,
                "spill": self.spill,
                "outflow": self.release + self.spill,
                "storage": self.storage,
                "level": self.level,
                "target_level": self.target_level,
                "target_storage": self.target_storage,
                "daily_hydropower": self.daily_hydropower,
            },
            index=self._time_index,
        )

    def get_reop_daily_hydropower(self) -> pd.Series:
        """Return the reoperated daily hydropower values."""
        return self.reop_daily_hydropower

    def plot_state(self, year: int = None, output_folder: str = None) -> None:
        fig, ax = plt.subplots(figsize=(13, 7), layout="constrained", dpi=350)
        ax.plot(self.inflow_ts + self.upstream_flow, label="Total inflow (m3/day)")
        ax.plot(self.release, label="Release (m3/day)")
        ax.plot(self.spill, label="Spill (m3/day)", linestyle="dotted", linewidth=2)
        ax.plot(
            self.release + self.spill,
            label="Outflow (m3/day)",
            linestyle="dotted",
        )
        ax.set_xlabel("Day")
        ax.set_ylabel("Flow rate (m3/day)")
        ax.set_title(f"{self.name} {year}")

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
        if output_folder:
            fig.savefig(os.path.join(output_folder, f"{self.name}.png"))
        plt.show()
