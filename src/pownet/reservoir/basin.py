""" basin.py: Basin class
"""

import os

import pandas as pd

from pownet.folder_utils import get_reservoir_file
from .reservoir import Reservoir


class Basin:
    def __init__(
        self,
        model_name: str,
        basin_name: str,
        sim_horizon: int = 365,
    ) -> None:
        """
        A class to manage reservoirs in a basin.
        """

        self.model_name: str = model_name
        self.basin_name: str = basin_name
        self.sim_horizon: int = sim_horizon

        # Reservoir names in the basin
        self.reservoir_names: list[str] = []
        # The largest cascade level in the basin
        self.max_cascade: int = 0
        # Map cascade level to its list of reservoir names {cascade_lvl: [name1, name2]}
        self.map_cascade: dict[int, list[str]] = {}

        # Upstream flow for each cascade level
        # Each column represents outflow from reservoirs at the previous cascade level
        # Ending index has +2 because
        # (+1) Python indexing excludes the last index
        # (+1) Outflow from the last cascade level
        self.cascade_flow = pd.DataFrame()
        self.reop_cascade_flow = pd.DataFrame()

        # Dict of reservoir objects based on their cascasde level
        # {cascade_level: [Reservoir1, Reservoir2]}
        self.reservoirs: dict[int, Reservoir] = {}

    def load_csv(self) -> None:
        """Load Basin information from a CSV file."""

        # User must specify reservoirs and their parameters in a CSV file
        reservoirs = pd.read_csv(get_reservoir_file(self.model_name, "reservoir.csv"))

        # Filter to only reservoirs of the basin
        if self.basin_name not in reservoirs.basin.unique():
            raise ValueError("Basin not found. Check basin name.")
        reservoirs = reservoirs[reservoirs["basin"] == self.basin_name]
        self.reservoir_names = reservoirs["name"].tolist()

        # Map cascade level to its list of reservoir names {cascade_lvl: [name1, name2]}
        # Cascade level starts from 0 (most upstream)
        self.map_cascade = (
            reservoirs[["cascade_level", "name"]]
            .groupby("cascade_level")["name"]
            .apply(list)
            .to_dict()
        )

        # Largest cascade level in the basin
        self.max_cascade = reservoirs["cascade_level"].max()
        self.reservoirs: dict[int, Reservoir] = {
            i: [] for i in range(self.max_cascade + 1)
        }
        self.cascade_flow = pd.DataFrame(
            0, columns=range(self.max_cascade + 2), index=range(1, self.sim_horizon + 1)
        )

    def simulate(self) -> None:
        """Simulate the basin to fill in values of reservoirs."""
        # Initialize the upstream flow for each cascade level
        for cascade_lv in range(self.max_cascade + 1):
            reservoir_names = self.map_cascade[cascade_lv]
            for reservoir_name in reservoir_names:
                reservoir = Reservoir(
                    model_name=self.model_name,
                    reservoir_name=reservoir_name,
                    sim_horizon=self.sim_horizon,
                    upstream_flow=self.cascade_flow.loc[:, cascade_lv],  # Upstream flow
                )
                reservoir.load_from_csv()
                reservoir.simulate()
                self.reservoirs[cascade_lv].append(reservoir)

                # The outflow from this reservoir is becomes part of inflow
                # of the next cascade level. Hence, add 1 to the cascade level.
                self.cascade_flow.loc[:, cascade_lv + 1] += (
                    +reservoir.release + reservoir.spill
                )

    def _get_hydropower_data(self, get_hydropower_func) -> pd.DataFrame:
        """Helper function to get hydropower data from reservoirs sharing
        the same cascade level."""
        df = pd.DataFrame()
        for cascade_level in range(self.max_cascade + 1):
            reservoirs = self.reservoirs[cascade_level]
            temp_df = pd.DataFrame(
                {
                    reservoir.name: get_hydropower_func(reservoir)
                    for reservoir in reservoirs
                }
            )
            df = pd.concat([df, temp_df], axis=1)
        return df

    def get_basin_hydropower(self, timestep: str) -> pd.DataFrame:
        """Return a dataframe of hydropower by each reservoir.

        Args:
            timestep (str): The timestep of the data. Either "daily" or "hourly".

        Returns:
            pd.DataFrame: A dataframe with hydropower data
        """
        # Map timestep to the corresponding function
        hydropower_funcs = {
            "daily": lambda reservoir: reservoir.get_daily_hydropower(),
            "hourly": lambda reservoir: reservoir.get_hourly_hydropower(),
        }

        # Check if the timestep is valid
        if timestep not in hydropower_funcs:
            raise ValueError("Unknown timestep")

        # Get the hydropower data using the mapped function
        return self._get_hydropower_data(hydropower_funcs[timestep])

    def init_reop_cascade_flow(self) -> None:
        """Initialize cascade flow for the reservoir operation."""
        self.reop_cascade_flow = pd.DataFrame(
            0, columns=range(self.max_cascade + 2), index=range(1, self.sim_horizon + 1)
        )
