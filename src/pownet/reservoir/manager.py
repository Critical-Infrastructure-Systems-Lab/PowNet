import os

import networkx as nx
import pandas as pd

from .reservoir import Reservoir
from ..data_model import ReservoirParams
from .reservoir_functions import (
    find_upstream_units,
    find_downstream_flow_fractions,
    find_simulation_order,
)


class ReservoirManager:
    def __init__(self):
        self.reservoirs: dict[str, Reservoir] = {}
        self.simulation_order: list[str] = []

    def load_reservoirs_from_csv(self, input_folder: str) -> None:
        """Load Basin information from a CSV file."""

        ###############################################################################
        # Read CSV files
        ###############################################################################

        # Reservoir units
        reservoir_data = pd.read_csv(
            os.path.join(input_folder, "reservoir_unit.csv"), header=0
        )

        # Flow paths
        filepath = os.path.join(input_folder, "flow_path.csv")
        if os.path.exists(filepath):
            flow_paths = pd.read_csv(filepath, header=0)
            flow_paths = flow_paths

        # Inflow and minimum flow time series
        inflow_ts = pd.read_csv(os.path.join(input_folder, "inflow.csv"), header=0)
        inflow_ts.index += 1

        minflow_ts = pd.read_csv(
            os.path.join(input_folder, "minimum_flow.csv"), header=0
        )
        minflow_ts.index += 1  # Time series indexing starts at 1

        ################################################################################
        # Instantiate Reservoir objects
        ################################################################################
        for _, row in reservoir_data.iterrows():
            unit_name = row["name"]

            upstream_units = find_upstream_units(flow_paths, unit_name)
            downstream_flow_fracs = find_downstream_flow_fractions(
                flow_paths, unit_name
            )

            params = ReservoirParams(
                name=unit_name,
                min_day=int(row["min_day"]),
                max_day=int(row["max_day"]),
                min_level=float(row["min_level"]),
                max_level=float(row["max_level"]),
                max_head=float(row["max_head"]),
                max_storage=float(row["max_storage"]),
                max_release=float(row["max_release"]),
                max_generation=float(row["max_generation"]),
                turbine_factor=float(row["turbine_factor"]),
                inflow_ts=inflow_ts[row["name"]],
                minflow_ts=minflow_ts[row["name"]],
                upstream_units=upstream_units,
                downstream_flow_fracs=downstream_flow_fracs,
            )
            # Create a new Reservoir object and add it to the list
            reservoir = Reservoir(params)
            self.reservoirs[unit_name] = reservoir

        #############################################################################
        # Process the network topology
        ##############################################################################
        self.simulation_order = find_simulation_order(flow_paths)
        # Ensure that all reservoirs are in the simulation order // The two sets must be equal
        if set(self.simulation_order) != set(self.reservoirs.keys()):
            raise ValueError(
                "The simulation order does not include all reservoirs: "
                f"{set(self.simulation_order) - set(self.reservoirs.keys())}"
            )

    def simulate(self) -> None:
        """Simulate the reservoir operations to get hydropower time series."""
        for unit_name in self.simulation_order:
            reservoir = self.reservoirs[unit_name]
            # Find the upstream flow
            total_upstream_flow = pd.Series(
                0, index=range(1, reservoir.sim_days + 1), name="upstream_flow"
            )

            for upstream_unit in reservoir.upstream_units:
                upstream_reservoir = self.reservoirs[upstream_unit]
                # Get the release and spill from the upstream reservoir
                total_upstream_flow += (
                    upstream_reservoir.release + upstream_reservoir.spill
                ) * upstream_reservoir.downstream_flow_fracs[unit_name]

            # Simulate
            reservoir.set_upstream_flow(total_upstream_flow)
            reservoir.simulate()

    def get_hydropower_ts(self) -> pd.DataFrame:
        """Get the hydropower time series for all reservoirs."""
        df = pd.DataFrame()
        for unit_name in self.simulation_order:
            reservoir = self.reservoirs[unit_name]
            temp_df = pd.DataFrame(
                {
                    unit_name: reservoir.daily_hydropower.values,
                }
            )
            df = pd.concat([df, temp_df], axis=1)

        df.index = range(1, len(df) + 1)
        return df

    def write_hydropower_to_csv(self, output_filepath: str) -> None:
        """Write the hydropower time series to CSV files."""
        os.makedirs(output_filepath, exist_ok=True)
        for reservoir in self.reservoirs:
            reservoir.hydropower.to_csv(output_filepath, index=False)
