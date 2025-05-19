"""reservoir.py"""

import dataclasses
import math

import pandas as pd


@dataclasses.dataclass()
class ReservoirParams:
    """
    Data class to hold static parameters and initial timeseries data for a reservoir.

    Attributes:
        name (str): The unique name of the reservoir.
        min_day (int): The day of the year when the target level is typically at its minimum.
        max_day (int): The day of the year when the target level is typically at its maximum.
        min_level (float): The minimum operational water level (meters).
        max_level (float): The maximum operational water level (meters).
        max_head (float): The maximum hydraulic head difference available for generation (meters).
        max_storage (float): The maximum storage capacity of the reservoir (m³).
        max_release (float): The maximum allowable daily release rate (m³/day).
        max_generation (float): The maximum power generation capacity (MW).
        turbine_factor (float): The efficiency factor of the turbine(s).
        inflow_ts (pd.Series): Timeseries of daily natural inflow into the reservoir (m³/day), indexed from 1.
        minflow_ts (pd.Series): Minimum environmental flow (m³/day), indexed from 1.
        upstream_units (list[str]): List of upstream reservoir names that feed into this reservoir.
        downstream_flow_fracs (dict[str, float]): Dictionary mapping downstream reservoir names to their respective flow fractions (0-1).
    """

    name: str
    min_day: int
    max_day: int
    min_level: float
    max_level: float
    max_head: float
    max_storage: float
    max_release: float
    max_generation: float
    turbine_factor: float
    inflow_ts: pd.Series
    minflow_ts: pd.Series
    upstream_units: list[str]
    downstream_flow_fracs: dict[str, float]

    def __post_init__(self):
        """Perform basic validation after initialization."""
        # Flow fractions of downstream units should sum to 1
        if self.downstream_flow_fracs:
            if not math.isclose(
                sum(self.downstream_flow_fracs.values()), 1.0, abs_tol=1e-4
            ):
                raise ValueError(
                    f"Downstream units for {self.name} do not sum to 1: "
                    f"{self.downstream_flow_fracs}"
                )

        # Check that inflow and minflow timeseries are indexed correctly
        if not self.inflow_ts.index.equals(self.minflow_ts.index):
            raise ValueError(
                f"Inflows and minflows for {self.name} are not indexed the same: "
                f"{self.inflow_ts.index} vs {self.minflow_ts.index}"
            )

        # Indexing starts at 1
        if self.inflow_ts.index[0] != 1:
            raise ValueError(
                f"Inflows for {self.name} do not start at 1: {self.inflow_ts.index[0]}"
            )
        if self.minflow_ts.index[0] != 1:
            raise ValueError(
                f"Minflows for {self.name} do not start at 1: {self.minflow_ts.index[0]}"
            )

        # Inflow must be greater than minflow for all days
        if not all(self.inflow_ts >= self.minflow_ts):
            raise ValueError(
                f"Inflows for {self.name} are less than minflows on some days: "
                f"{(self.inflow_ts < self.minflow_ts).sum()} days"
            )
