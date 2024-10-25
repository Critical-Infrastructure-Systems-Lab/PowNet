""" reservoir_operator.py: Defines the ReservoirOperator class """

import os

import numpy as np
import pandas as pd

from pownet.folder_utils import get_reservoir_file

from .basin import Basin
from .reservoir import Reservoir
from .reservoir_functions import convert_to_hourly_hydropower


class ReservoirOperator:
    def __init__(
        self,
        model_name: str,
        sim_horizon: int = 365,
    ) -> None:
        """A class that manages the operation of multiple basins."""

        self.model_name: str = model_name
        self.sim_horizon: int = sim_horizon

        # Basin information
        self.basin_names: list[str] = []
        self.reservoir_names: list[str] = []

        # Basins in the system
        self.basins: list[Basin] = []
        self.reservoirs: list[Reservoir] = []

        # Hydropower timeseries
        self.daily_hydropower: pd.DataFrame = pd.DataFrame()
        self.hourly_hydropower: pd.DataFrame = pd.DataFrame()

    def load_csv(self) -> None:
        """
        Load information from a CSV file.
        """
        # Basin names
        self.basin_names = (
            pd.read_csv(
                get_reservoir_file(self.model_name, "reservoir.csv"),
                header=0,
            )["basin"]
            .unique()
            .tolist()
        )
        # All reservoir names in the system
        self.reservoir_names.extend(
            name for basin in self.basins for name in basin.reservoir_names
        )

    def simulate(self):
        """Simulate the operation of the reservoirs."""
        # Create Basin objects
        for basin_name in self.basin_names:
            basin = Basin(model_name=self.model_name, basin_name=basin_name)
            basin.load_csv()
            basin.simulate()
            self.basins.append(basin)

            # Get the reservoirs in the basin
            self.reservoirs.extend(
                [res for res_lists in basin.reservoirs.values() for res in res_lists]
            )

            # Get the hydropower timeseries
            self.daily_hydropower = pd.concat(
                [self.daily_hydropower, basin.get_basin_hydropower(timestep="daily")],
                axis=1,
            )
            self.hourly_hydropower = convert_to_hourly_hydropower(self.daily_hydropower)

    def get_daily_hydropower(self) -> pd.DataFrame:
        return self.daily_hydropower

    def get_hourly_hydropower(self) -> pd.DataFrame:
        return self.hourly_hydropower

    def export_hydropower_csv(self, timestep: str, output_folder: str) -> None:
        csv_name = "pownet_hydropower.csv"

        # Check if the timestep is valid
        if timestep not in ["daily", "hourly"]:
            raise ValueError("Unknown timestep")

        # Map timestep to the corresponding DataFrame
        hydropower_data = {
            "daily": self.daily_hydropower,
            "hourly": self.hourly_hydropower,
        }
        # Export the DataFrame to CSV
        hydropower_data[timestep].to_csv(os.path.join(output_folder, csv_name))

    def get_plots(self, output_folder: str = None) -> None:
        """Plot daily storage, release, and spill of each reservoir."""
        for reservoir in self.reservoirs:
            reservoir.plot_state(output_folder=output_folder)

    def export_state(self, output_folder: str = None) -> None:
        """Export the daily values of storage, release, and spill of each reservoir."""
        for reservoir in self.reservoirs:
            df = pd.DataFrame(
                {
                    "inflow": reservoir.inflow,
                    "upstream_flow": reservoir.upstream_flow,
                    "storage": reservoir.storage,
                    "release": reservoir.release,
                    "spill": reservoir.spill,
                    "level": reservoir.level,
                    "mid_level": reservoir.mid_level,
                    "min_flow": reservoir.min_flow,
                    "target_storage": reservoir.target_storage,
                }
            )
            df.to_csv(
                os.path.join(output_folder, f"{reservoir.name}_state.csv"),
                index=False,
            )

    def export_reop_state(self, output_folder: str = None) -> None:
        for reservoir in self.reservoirs:
            df = pd.DataFrame(
                {
                    "inflow": reservoir.inflow,
                    "upstream_flow": reservoir.reop_upstream,
                    "storage": reservoir.reop_storage,
                    "release": reservoir.reop_release,
                    "spill": reservoir.reop_spill,
                    "level": reservoir.reop_level,
                    "mid_level": reservoir.mid_level,
                    "min_flow": reservoir.min_flow,
                    "target_storage": reservoir.target_storage,
                }
            )
            df.to_csv(
                os.path.join(output_folder, f"reop_{reservoir.name}_state.csv"),
                index=False,
            )

    def reoperate_basins(
        self, day: int, daily_dispatch: dict[str, float]
    ) -> dict[str, float]:
        """Reoperate the reservoirs based on the daily dispatch of the power system model.
        Note that we don't reoperate on the first day of the simulation period.
        """
        daily_hydropower_capacity = {}

        for basin in self.basins:
            # Reset reoperated downstream flow
            basin.init_reop_cascade_flow()
            for cascade_lv in range(basin.max_cascade + 1):
                for reservoir in basin.reservoirs[cascade_lv]:
                    reservoir_daily_dispatch = daily_dispatch[reservoir.name]
                    daily_hydropower_capacity[reservoir.name] = reservoir.reoperate(
                        day=day,
                        daily_dispatch=reservoir_daily_dispatch,
                        upstream_flow=basin.cascade_flow.loc[day, cascade_lv],
                    )
                    # Update downstream flow
                    basin.cascade_flow.loc[day, cascade_lv + 1] += (
                        +reservoir.reop_release[day] + reservoir.reop_spill[day]
                    )

        return daily_hydropower_capacity
