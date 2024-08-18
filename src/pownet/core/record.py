""" record.py: This module contains the SystemRecord class, which processes stores the modeling outputs from each iteration.
"""

from __future__ import annotations
import os

import pandas as pd
import numpy as np

from pownet.modeling import PowerSystemModel
from pownet.folder_utils import get_output_dir


def write_df_to_output_dir(
    df: pd.DataFrame,
    output_name: str,
    model_id: str,
) -> None:
    """Write a dataframe to the output folder.

    Args:
        df: The dataframe to write.
        output_name: The name of the output file.
        model_id: The model ID.

    Returns:
        None
    """
    df.to_csv(
        os.path.join(
            get_output_dir(),
            f"{model_id}_{output_name}.csv",
        ),
        index=False,
    )


def calc_remaining_duration(
    solution: pd.DataFrame,
    sim_horizon: int,
    thermal_units: list[str],
    duration_dict: dict[str, int],  # Generic for TU or TD
    vartype: str,  # 'startup' or 'shutdown'
) -> dict[str, int]:
    """Calculates the remaining duration (on or off) for each thermal unit.

    This function analyzes the provided solution DataFrame to determine the latest
    timestep at which a specified event (startup or shutdown) occurred for each
    thermal unit. It then calculates the remaining duration based on the simulation
    horizon and the unit's minimum required duration.

    Args:
        solution: A DataFrame containing the solution of the optimization model.
        sim_horizon: The length of the simulation horizon.
        thermal_units: A list of thermal unit names.
        duration_dict: A dictionary mapping unit names to their respective minimum durations.
        vartype: The type of event to analyze. Either 'startup' or 'shutdown'.

    Returns:
        A dictionary mapping unit names to their remaining durations.

    Raises:
        ValueError: If the simulation horizon is shorter than the maximum duration of any thermal unit.
    """

    # This logic does not work if sim_horizon is shorter than the duration
    if sim_horizon < max(duration_dict.values()):
        raise ValueError(
            "The simulation horizon is shorter than the maximum duration of the thermal units."
        )

    remaining_durations = {}

    for unit in thermal_units:
        subset = (
            solution[(solution["node"] == unit) & (solution["vartype"] == vartype)]
            .set_index("timestep")
            .drop(["vartype", "node"], axis=1)
        )

        filtered_df = subset[subset["value"] == 1]
        if len(filtered_df) > 0:
            latest_event_timestep = filtered_df.index.max()
        else:
            latest_event_timestep = -sim_horizon

        remaining_durations[unit] = max(
            0, duration_dict[unit] - (sim_horizon - latest_event_timestep) - 1
        )

    return remaining_durations


def calc_remaining_on_duration(
    solution: pd.DataFrame,
    sim_horizon: int,
    thermal_units: list[str],
    TU: dict[str, int],
) -> dict[str, int]:
    """Calculate the remaining online duration for each thermal unit."""
    return calc_remaining_duration(solution, sim_horizon, thermal_units, TU, "startup")


def calc_remaining_off_duration(
    solution: pd.DataFrame,
    sim_horizon: int,
    thermal_units: list[str],
    TD: dict[str, int],
) -> dict[str, int]:
    """Calculate the remaining shutdown duration for each thermal unit."""
    return calc_remaining_duration(solution, sim_horizon, thermal_units, TD, "shutdown")


class SystemRecord:
    """This class stores modeling outputs from each iteration. The results are stored
    in three dataframes: node_vars, flow_vars, and syswide_vars. The initial conditions
    are also stored in the class.
    """

    def __init__(self, system_input: "SystemInput") -> None:

        self.inputs = system_input

        # Format of variable name: var(node, t)
        self.node_vars: pd.DataFrame = pd.DataFrame()
        # Format of variable name: flow(node_a, node_b, t)
        self.flow_vars: pd.DataFrame = pd.DataFrame()
        # Format of variable name: var(t)
        self.syswide_vars: pd.DataFrame = pd.DataFrame()

        self.objvals: list = []
        self.runtimes: list = []

        # These are vpower, unit status, unit switching, etc.
        self.current_p: dict[str, float] = {}
        self.current_u: dict[str, int] = {}
        self.current_v: dict[str, int] = {}
        self.current_w: dict[str, int] = {}
        self.current_min_on: dict[str, int] = {}
        self.current_min_off: dict[str, int] = {}

    def _parse_node_variables(
        self, solution: pd.DataFrame, step_k: int
    ) -> pd.DataFrame:
        """Node variables are in the (node, t) format."""

        node_var_pattern = r"(\w+)\[(\w+),(\d+)\]"
        current_node_vars = solution[
            solution["varname"].str.match(node_var_pattern)
        ].copy()

        current_node_vars[["node", "timestep"]] = current_node_vars[
            "varname"
        ].str.extract(node_var_pattern, expand=True)[[1, 2]]

        current_node_vars["timestep"] = current_node_vars["timestep"].astype(int)

        current_node_vars["hour"] = current_node_vars[
            "timestep"
        ] + self.inputs.sim_horizon * (step_k - 1)

        # Rounding binary values
        current_node_vars.loc[
            np.isclose(current_node_vars["value"], 0, atol=1e-4), "value"
        ] = 0
        current_node_vars.loc[
            np.isclose(current_node_vars["value"], 1, atol=1e-4), "value"
        ] = 1
        return current_node_vars

    def _parse_flow_variables(
        self, solution: pd.DataFrame, step_k: int
    ) -> pd.DataFrame:
        """
        The flow variables are in the (node, node, t) format.
        """
        flow_var_pattern = r"flow\[(\w+),(\w+),(\d+)\]"
        cur_flow_vars = solution[solution["varname"].str.match(flow_var_pattern)].copy()

        cur_flow_vars[["node_a", "node_b", "hour"]] = cur_flow_vars[
            "varname"
        ].str.extract(flow_var_pattern, expand=True)

        cur_flow_vars["hour"] = cur_flow_vars["hour"].astype(int)
        cur_flow_vars["hour"] = cur_flow_vars["hour"] + self.inputs.sim_horizon * (
            step_k - 1
        )
        return cur_flow_vars

    def _parse_syswide_variables(
        self, solution: pd.DataFrame, step_k: int
    ) -> pd.DataFrame:
        """
        The system-wide variables are in the (t) format.
        """
        syswide_var_pattern = r"(\w+)\[(\d+)\]"
        cur_syswide_vars = solution[
            solution["varname"].str.match(syswide_var_pattern)
        ].copy()

        cur_syswide_vars["hour"] = cur_syswide_vars["varname"].str.extract(
            syswide_var_pattern, expand=True
        )[1]
        cur_syswide_vars["hour"] = cur_syswide_vars["hour"].astype(int)
        cur_syswide_vars["hour"] = cur_syswide_vars[
            "hour"
        ] + self.inputs.sim_horizon * (step_k - 1)

    def keep(
        self,
        power_system_model: PowerSystemModel,
        step_k: int,
    ) -> None:
        """Keep the simulation results at the current simulation period step_k"""

        def _extract_vartype_data(df: pd.DataFrame, vartype: str) -> dict[str, float]:
            """Extracts data for a specific 'vartype' from the DataFrame and converts it to a dictionary."""
            return (
                df[
                    (df["vartype"] == vartype)
                    & (df["timestep"] == self.inputs.sim_horizon)
                ]  # Only considers values of the last hour
                .drop("vartype", axis=1)
                .set_index(["node", "timestep"])
                .to_dict()["value"]
            )

        self.runtimes.append(power_system_model.get_runtime())
        self.objvals.append(power_system_model.get_objval())

        solution = pd.DataFrame(power_system_model.get_solution())
        # Create a col of variable types for filtering
        pat_vartype = r"(\w+)\["
        solution[["vartype"]] = solution["varname"].str.extract(
            pat_vartype, expand=True
        )

        current_node_vars = self._parse_node_variables(solution, step_k)

        ##################
        # Initial conditions: vpower (p), commitment (u),
        # startup (v), and shutdown (w).
        ##################
        self.current_p = _extract_vartype_data(current_node_vars, "vpower")
        self.current_u = _extract_vartype_data(current_node_vars, "status")
        self.current_v = _extract_vartype_data(current_node_vars, "startup")
        self.current_w = _extract_vartype_data(current_node_vars, "shutdown")

        # Need to calculate the minimum time on/off
        self.current_min_on = calc_remaining_on_duration(
            current_node_vars,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
            TU=self.inputs.TU,
        )
        self.current_min_off = calc_remaining_off_duration(
            current_node_vars,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
            TD=self.inputs.TD,
        )

        ##################
        # Append results to the existing dataframes
        ##################
        current_node_vars = current_node_vars.drop("timestep", axis=1)
        self.node_vars = pd.concat([self.node_vars, current_node_vars], axis=0)
        self.flow_vars = pd.concat(
            [
                self.flow_vars,
                self._parse_flow_variables(solution=solution, step_k=step_k),
            ],
            axis=0,
        )
        self.syswide_vars = pd.concat(
            [
                self.syswide_vars,
                self._parse_syswide_variables(solution=solution, step_k=step_k),
            ],
            axis=0,
        )

    def get_init_conds(self) -> dict[str, dict]:
        return {
            "initial_p": self.current_p,
            "initial_u": self.current_u,
            "initial_v": self.current_v,
            "initial_w": self.current_w,
            "initial_min_on": self.current_min_on,
            "initial_min_off": self.current_min_off,
        }

    def get_node_variables(self) -> pd.DataFrame:
        """Return node-specific variables. These variables include
        dispatch, unit status, unit switching, etc.
        """
        return self.node_vars

    def get_flow_variables(self) -> pd.DataFrame:
        """Return the flow variables."""
        return self.flow_vars

    def get_systemwide_variables(self) -> pd.DataFrame:
        """Return the system variables. We currently only have the
        system-wide spinning reserve shortfall.
        """
        return self.syswide_vars

    def get_runtimes(self) -> list[float]:
        return self.runtimes

    def get_objvals(self) -> list[float]:
        return self.objvals

    def write_simulation_results(self) -> None:
        """
        Write 4 CSV files containing modeling results to the output directory.
        """
        data_to_write = [
            (self.node_vars, "node_variables"),
            (self.flow_vars, "flow_variables"),
            (self.syswide_vars, "system_variables"),
            (
                pd.DataFrame({"objval": self.objvals, "runtime": self.runtimes}),
                "model_stats",
            ),
        ]

        for df, output_name in data_to_write:
            write_df_to_output_dir(
                df,
                output_name=output_name,
                model_id=self.inputs.model_id,  # Use model_name as the identifier
            )
