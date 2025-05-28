"""power_trade.py: PowerTradeParams dataclass for electricity system trading"""

import dataclasses
import math

import pandas as pd


@dataclasses.dataclass()
class PowerTradeParams:
    """
    Data class to hold static parameters for electricity trading among power systems.

    Attributes:
        intertie_points (list[tuple[str, str]]): List of tuples representing intertie points between balancing areas (Node-Node).
        intertie_capacities (dict[tuple[str, str], float]): Dictionary mapping intertie points to their capacities in MW.
        connected_ba (list[tuple[str, str]]): List of tuples representing connected balancing authorities (BA-BA).
        total_transfer_limits (dict[tuple[str, str], float]): Dictionary mapping trading corridors (BA-BA) to their total transfer limits in MW.
    """

    intertie_points: list[tuple[str, str]] = dataclasses.field(default_factory=list)
    intertie_capacities: dict[tuple[str, str], float] = dataclasses.field(default_factory=dict)

    connected_ba: list[tuple[str, str]] = dataclasses.field(default_factory=list)
    total_transfer_limits: dict[tuple[str, str], float] = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        # Ensure capacities are positive
        for intertie, capacity in self.intertie_capacities.items():
            if capacity < 0:
                raise ValueError(f"Intertie capacity for {intertie} cannot be negative: {capacity} MW")
        
        # Ensure there are no self-loops in intertie_points
        for intertie in self.intertie_points:
            if intertie[0] == intertie[1]:
                raise ValueError(f"Self-loop intertie found: {intertie[0]} to {intertie[1]} in intertie points: {self.intertie_points}")

        # Ensure there is no reverse intertie_points
        for intertie in self.intertie_points:
            if (intertie[1], intertie[0]) in self.intertie_points:
                raise ValueError(f"Reverse intertie {intertie[1]}, {intertie[0]} found in intertie points: {self.intertie_points}")
            
        # Ensure connected_ba are unique pairs
        unique_ba_pairs = set()
        for ba_pair in self.connected_ba:
            if (ba_pair[1], ba_pair[0]) in unique_ba_pairs:
                raise ValueError(f"Reverse BA pair {ba_pair[1]}, {ba_pair[0]} found in connected BA: {self.connected_ba}")
            unique_ba_pairs.add(ba_pair)

    @classmethod
    def from_csv(cls, csv_file: str):
        """
        Factory method to create a PowerTradeParams instance from a CSV file.
        The CSV should have columns: intertie_1_ba, intertie_1_node, intertie_2_ba, intertie_2_node, capacity_mw.

        Args:
            csv_file (str): Path to the CSV file containing trading parameters.

        Returns:
            PowerTradeParams: A fully populated PowerTradeParams instance.

        Raises:
            ValueError: If the CSV file does not contain the required columns or invalid data.
        """
        df = pd.read_csv(csv_file, header=0)

        # --- Check for required columns ---
        required_columns = [
            "intertie_1_ba",
            "intertie_1_node",
            "intertie_2_ba",
            "intertie_2_node",
            "capacity_mw",
        ]
        if not all(col in df.columns for col in required_columns):
            raise ValueError(
                f"CSV file must contain the following columns: {', '.join(required_columns)}"
            )
        
        # --- Collect attributes from the DataFrame ---
        # Initialize temporary lists/dicts to build the data
        temp_intertie_points = []
        temp_intertie_capacities = {}
        temp_connected_ba = []
        temp_total_transfer_limits = {}

        for _, row in df.iterrows():
            intertie_1_node = row["intertie_1_node"]
            intertie_1_ba = row["intertie_1_ba"]
            intertie_2_node = row["intertie_2_node"]
            intertie_2_ba = row["intertie_2_ba"]
            capacity = float(row["capacity_mw"])

            # Intertie Points and Capacities
            intertie_tuple = (intertie_1_node, intertie_2_node)
            if intertie_tuple in temp_intertie_capacities:
                raise ValueError(
                    f"Duplicate intertie point found: {intertie_tuple} with capacity {capacity} MW. "
                    "Each intertie point must be unique."
                )
            else:
                temp_intertie_points.append(intertie_tuple)
                temp_intertie_capacities[intertie_tuple] = capacity

            # Connected BAs and Total Transfer Limits
            ba_corridor = (intertie_1_ba, intertie_2_ba)
            if ba_corridor not in temp_connected_ba:
                temp_connected_ba.append(ba_corridor)

            temp_total_transfer_limits[ba_corridor] = temp_total_transfer_limits.get(ba_corridor, 0.0) + capacity

        # Instantiate the dataclass with the collected data
        # __post_init__ will be called automatically after this
        return cls(
            intertie_points=temp_intertie_points,
            intertie_capacities=temp_intertie_capacities,
            connected_ba=temp_connected_ba,
            total_transfer_limits=temp_total_transfer_limits,
        )