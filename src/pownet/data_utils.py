"""data_utils.py: functions for processing user inputs"""

import re
import datetime
import os

import numpy as np
import pandas as pd
from pownet.folder_utils import get_database_dir, get_output_dir


def get_dates(year):
    """Return a dataframe of dates for the given year. The dataframe will have
    365 rows, one for each day of the year. The columns are 'date' and 'hour'.
    """
    # Create dates to concatenate with the new dataframes
    dates = pd.DataFrame(
        {"date": pd.date_range(start=str(year), periods=366, freq="D")}
    )
    # Remove 29th Feb because we do not deal with them
    dates = dates.loc[dates.date.dt.strftime("%m-%d") != "02-29"]
    # Remove 1st Jan of the next year in case it is included when it is not a leap year
    dates = dates.loc[dates.date.dt.strftime("%Y-%m-%d") != f"{year+1}-01-01"]

    # In case we need three columns: date, hour, and day
    dates = dates.loc[dates.index.repeat(24)]
    dates["hour"] = np.tile(range(1, 25), 365)
    dates = dates.reset_index(drop=True)
    return dates


def create_init_condition(thermal_units: list) -> dict[(str, int), dict]:
    """Return dicts of system statuses in the format {(unit, hour): value}"""
    # Assume thermal units in the systems are offline at the beginning
    initial_p = {unit_g: 0 for unit_g in thermal_units}
    initial_u = initial_p.copy()
    initial_v = initial_p.copy()
    initial_w = initial_p.copy()

    # Thermal units do not carry any minimum up and down time at the beginning
    initial_min_on = {unit_g: 0 for unit_g in thermal_units}
    initial_min_off = initial_min_on.copy()

    return {
        "initial_p": initial_p,
        "initial_u": initial_u,
        "initial_v": initial_v,
        "initial_w": initial_w,
        "initial_min_on": initial_min_on,
        "initial_min_off": initial_min_off,
    }


def get_node_hour_from_flow_constraint(constraint_name: str) -> tuple[str, int]:
    """Get the node and hour from the flow constraint name.

    Args:
        constraint_name: The name of the constraint.

    Returns:
        The node and hour.

    """
    flow_constraint_pattern = re.compile(r"flowBal\[(\w+),(\d+)\]")
    match = flow_constraint_pattern.match(constraint_name)
    if match:
        node = match.group(1)
        hour = int(match.group(2))
        return node, hour
    else:
        return None, None


def get_unit_hour_from_varnam(var_name: str) -> tuple[str, int]:
    """Get the unit and hour from the variable name.

    Args:
        var_name: The name of the variable.

    Returns:
        The unit and hour.

    """
    node_var_pattern = re.compile(r"(\w+)\[(\w+),(\d+)\]")
    match = node_var_pattern.match(var_name)
    if match:
        unit = match.group(2)
        hour = int(match.group(3))
        return unit, hour
    else:
        raise ValueError("Invalid variable name format")


def get_edge_hour_from_varname(var_name: str) -> tuple[tuple[str, str], int]:
    """Get the edge and hour from the variable name: flow[a,b,t].

    Args:
        var_name: The name of the variable.

    Returns:
        The edge and hour.

    """
    edge_var_pattern = re.compile(r"flow\[(\w+),(\w+),(\d+)\]")
    match = edge_var_pattern.match(var_name)
    if match:
        edge = (match.group(1), match.group(2))
        hour = int(match.group(3))
        return edge, hour
    else:
        raise ValueError("Invalid variable name format")


def get_current_time() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M")


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


def parse_node_variables(
    solution: pd.DataFrame, sim_horizon: int, step_k: int
) -> pd.DataFrame:
    """Node variables are in the (node, t) format."""

    node_var_pattern = r"(\w+)\[(\w+),(\d+)\]"
    current_node_vars = solution[solution["varname"].str.match(node_var_pattern)].copy()

    current_node_vars[["node", "timestep"]] = current_node_vars["varname"].str.extract(
        node_var_pattern, expand=True
    )[[1, 2]]

    current_node_vars["timestep"] = current_node_vars["timestep"].astype(int)

    current_node_vars["hour"] = current_node_vars["timestep"] + sim_horizon * (
        step_k - 1
    )

    # Rounding binary values
    current_node_vars.loc[
        np.isclose(current_node_vars["value"], 0, atol=1e-4), "value"
    ] = 0
    current_node_vars.loc[
        np.isclose(current_node_vars["value"], 1, atol=1e-4), "value"
    ] = 1
    return current_node_vars


def parse_flow_variables(
    solution: pd.DataFrame, sim_horizon: int, step_k: int
) -> pd.DataFrame:
    """
    The flow variables are in the (node, node, t) format.
    """
    flow_var_pattern = r"flow\[(\w+),(\w+),(\d+)\]"
    cur_flow_vars = solution[solution["varname"].str.match(flow_var_pattern)].copy()

    cur_flow_vars[["node_a", "node_b", "timestep"]] = cur_flow_vars[
        "varname"
    ].str.extract(flow_var_pattern, expand=True)

    cur_flow_vars["timestep"] = cur_flow_vars["timestep"].astype(int)
    cur_flow_vars["hour"] = cur_flow_vars["timestep"] + sim_horizon * (step_k - 1)
    cur_flow_vars = cur_flow_vars.drop("varname", axis=1)
    return cur_flow_vars


def parse_syswide_variables(
    solution: pd.DataFrame, sim_horizon: int, step_k: int
) -> pd.DataFrame:
    """
    The system-wide variables are in the (t) format.
    """
    syswide_var_pattern = r"(\w+)\[(\d+)\]"
    cur_syswide_vars = solution[
        solution["varname"].str.match(syswide_var_pattern)
    ].copy()

    cur_syswide_vars["timestep"] = cur_syswide_vars["varname"].str.extract(
        syswide_var_pattern, expand=True
    )[1]
    cur_syswide_vars["timestep"] = cur_syswide_vars["timestep"].astype(int)
    cur_syswide_vars["hour"] = cur_syswide_vars["timestep"] + sim_horizon * (step_k - 1)
    cur_syswide_vars = cur_syswide_vars.drop("varname", axis=1)
    return cur_syswide_vars


def parse_lmp(lmp: dict[str, float], sim_horizon: int, step_k: int) -> pd.DataFrame:
    lmp_df = pd.DataFrame.from_dict(lmp, orient="index", columns=["value"])
    lmp_df = lmp_df.reset_index().rename(columns={"index": "name"})
    lmp_df[["node", "timestep"]] = lmp_df["name"].str.extract(r"flowBal\[(.*),(\d+)\]")
    lmp_df["timestep"] = lmp_df["timestep"].astype(int)
    lmp_df["hour"] = lmp_df["timestep"] + sim_horizon * (step_k - 1)
    # Keep only the first 24-hours of the simulation
    lmp_df = lmp_df[lmp_df["timestep"] <= 24]
    lmp_df = lmp_df.drop(["name"], axis=1)
    return lmp_df


def get_fuel_mix_order() -> list[str]:
    """Return the order of fuel mix for plotting.
    We use this list to order the node variables dataframe.

    Returns
        list[str]: The order of fuel mix.
    -------
    """
    return pd.read_csv(
        os.path.join(get_database_dir(), "fuels.csv"),
        header=0,
    )["name"].tolist()


def get_fuel_color_map() -> dict:
    """Return a map of fuel type to its color. This is defined in the database folder."""
    fuel_color_map = (
        pd.read_csv(
            os.path.join(get_database_dir(), "fuels.csv"),
            header=0,
            usecols=["name", "color"],
        )
        .set_index("name")
        .to_dict()["color"]
    )
    return fuel_color_map
