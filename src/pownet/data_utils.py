"""data_utils.py: functions for processing user inputs"""

import re
import datetime
import os

import numpy as np
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point

from .folder_utils import get_database_dir


def get_dates(year, num_days=365):
    """Return a dataframe of dates for the given year. The dataframe will have
    365 rows, one for each day of the year. The columns are 'date' and 'hour'.
    Exclude 29th February.
    """
    # Create dates to concatenate with the new dataframes
    dates = pd.DataFrame(
        {"date": pd.date_range(start=str(year), periods=num_days + 1, freq="D")}
    )
    # Remove 29th Feb because we do not deal with them
    dates = dates.loc[dates.date.dt.strftime("%m-%d") != "02-29"]
    # Remove 1st Jan of the next year in case it is included when it is not a leap year
    dates = dates.loc[dates.date.dt.strftime("%Y-%m-%d") != f"{year + 1}-01-01"]

    # In case we need three columns: date, hour, and day
    dates = dates.loc[dates.index.repeat(24)]
    dates["hour"] = np.tile(range(1, 25), num_days)
    dates = dates.reset_index(drop=True)
    return dates


def get_datetime_index(year: int) -> pd.DatetimeIndex:
    """Return a datetime index for the given year. The index will have 8760 entries, one for each hour of the year. Exclude 29th February."""
    dates = pd.date_range(start=f"{year}-01-01", end=f"{year + 1}-01-01", freq="h")
    # Remove 29th February
    dates = dates[~((dates.month == 2) & (dates.day == 29))]
    return dates[dates.year == year]


def remove_29feb(timeseries: pd.Series) -> pd.Series:
    """Clean and reindex flow data by removing February 29th and resetting the index.

    Args:
        timeseries (pd.Series): Timeseries to be cleaned and reindexed.

    Returns:
        pd.Series: The cleaned and reindexed flow data.
    """

    # Remove 29th February from the dataset
    cleaned_data = timeseries[~((timeseries.month == 2) & (timeseries.day == 29))]
    # Index starts from 1
    cleaned_data = cleaned_data.reset_index(drop=True)
    cleaned_data.index += 1
    return cleaned_data


def create_init_condition(
    thermal_units: list,
    storage_units: list = None,
    ess_max_capacity: dict[str, float] = None,
) -> dict[(str, int), dict]:
    """Return dicts of system statuses in the format {(unit, hour): value}"""
    # Assume thermal units in the systems are offline at the beginning
    initial_p = {unit_g: 0 for unit_g in thermal_units}
    initial_u = initial_p.copy()
    initial_v = initial_p.copy()
    initial_w = initial_p.copy()

    # Thermal units do not carry any minimum up and down time at the beginning
    initial_min_on = {unit_g: 0 for unit_g in thermal_units}
    initial_min_off = initial_min_on.copy()

    # Energy storage systems start with zero charge
    if storage_units is None:
        initial_charge_state = {}
    elif len(storage_units) > 0:
        initial_charge_state = {unit: 0 for unit in storage_units}
        if ess_max_capacity is not None:
            for unit in ess_max_capacity:
                initial_charge_state[unit] = ess_max_capacity[unit]
    else:
        initial_charge_state = {}

    return {
        "initial_p": initial_p,
        "initial_u": initial_u,
        "initial_v": initial_v,
        "initial_w": initial_w,
        "initial_min_on": initial_min_on,
        "initial_min_off": initial_min_off,
        "initial_charge_state": initial_charge_state,
    }


def get_node_hour_from_flow_constraint(constraint_name: str) -> tuple[str, int]:
    """Get the node and hour from the flow constraint name.

    Args:
        constraint_name: The name of the constraint.

    Returns:
        The node and hour.

    """
    flow_constraint_pattern = re.compile(r"flowBal\[(.+),(\d+)\]")
    match = flow_constraint_pattern.match(constraint_name)
    if match:
        node = match.group(1)
        hour = int(match.group(2))
        return node, hour
    else:
        return None, None


def get_unit_hour_from_varname(var_name: str) -> tuple[str, int]:
    """Get the unit and hour from the variable name.

    Args:
        var_name: The name of the variable.

    Returns:
        The unit and hour.

    """
    node_var_pattern = re.compile(r"(\w+)\[(.+),(\d+)\]")
    match = node_var_pattern.match(var_name)
    if match:
        unit = match.group(2)
        hour = int(match.group(3))
        return unit, hour
    else:
        raise ValueError("Invalid variable name format")


def get_edge_hour_from_varname(var_name: str) -> tuple[tuple[str, str], int]:
    """Get the edge and hour from the variable name: flow_fwd[a,b,t] or flow_bwd[a,b,t].

    Args:
        var_name: The name of the variable.

    Returns:
        The edge (tuple of two strings) and hour (int).

    """
    edge_var_pattern = re.compile(r"flow_(?:fwd|bwd)\[([^,]+),([^,]+),(\d+)\]")
    match = edge_var_pattern.match(var_name)
    if not match:
        raise ValueError(f"Invalid variable name format: {var_name}")

    node1 = match.group(1)
    node2 = match.group(2)
    hour = int(match.group(3))
    edge = (node1, node2)
    return edge, hour


def get_current_time() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M")


def write_df(
    df: pd.DataFrame,
    output_folder: str,
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
    # First check that the output directory exists. If not, create it.
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    df.to_csv(
        os.path.join(output_folder, f"{model_id}_{output_name}.csv"),
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
    """Calculate the remaining online duration for each thermal unit.

    Args:
        solution: A DataFrame containing the solution of the optimization model.
        sim_horizon: The length of the simulation horizon.
        thermal_units: A list of thermal unit names.
        TU: A dictionary mapping unit names to their respective minimum online durations.

    Returns:
        A dictionary mapping unit names to their remaining online durations.
    """
    return calc_remaining_duration(solution, sim_horizon, thermal_units, TU, "startup")


def calc_remaining_off_duration(
    solution: pd.DataFrame,
    sim_horizon: int,
    thermal_units: list[str],
    TD: dict[str, int],
) -> dict[str, int]:
    """Calculate the remaining shutdown duration for each thermal unit.

    Args:
        solution: A DataFrame containing the solution of the optimization model.
        sim_horizon: The length of the simulation horizon.
        thermal_units: A list of thermal unit names.
        TD: A dictionary mapping unit names to their respective minimum offline durations.

    Returns:
        A dictionary mapping unit names to their remaining shutdown durations.
    """
    return calc_remaining_duration(solution, sim_horizon, thermal_units, TD, "shutdown")


def parse_node_variables(
    solution: pd.DataFrame, sim_horizon: int, step_k: int
) -> pd.DataFrame:
    """Parse the node variables from the solution DataFrame. Node variables are in the (node, t) format.
    Also, ensure binary values are rounded to 0 or 1.

    Args:
        solution: The solution DataFrame.
        sim_horizon: The length of the simulation horizon.
        step_k: The current simulation period.

    Returns:
        pd.DataFrame: The node variables DataFrame"""

    node_var_pattern = r"(\w+)\[(.+),(\d+)\]"
    current_node_vars = solution[solution["varname"].str.match(node_var_pattern)].copy()

    # Flow should not be included in the node variables
    current_node_vars = current_node_vars[
        ~current_node_vars["vartype"].isin(["flow_fwd", "flow_bwd"])
        ]

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
    Parses flow variables from the solution DataFrame.
    The flow variables are expected in the format:
    flow_fwd[node_a,node_b,t] or flow_bwd[node_a,node_b,t].

    Args:
        solution: The solution DataFrame with a 'varname' column.
        sim_horizon: The length of the simulation horizon for a single step_k (e.g., 24 hours).
        step_k: The current simulation period (1-indexed).

    Returns:
        pd.DataFrame: A DataFrame with parsed flow variables, including
                      columns for 'node_a', 'node_b', 'type' (fwd/bwd),
                      'value', 'timestep' (relative to step_k), and 'hour' (absolute).
    """
    # Matches flow_fwd[node_a,node_b,t] or flow_bwd[node_a,node_b,t]
    # It captures the type (fwd or bwd), node_a, node_b, and t.
    flow_var_pattern = r"flow_(fwd|bwd)\[([^,]+),([^,]+),(\d+)\]"

    # Filter rows that match the flow variable pattern
    flow_vars_mask = solution["varname"].str.contains(
        r"flow_(?:fwd|bwd)\[.+,.+,\d+\]", regex=True
    )
    cur_flow_vars = solution[flow_vars_mask].copy()

    if cur_flow_vars.empty:
        return pd.DataFrame(
            columns=["node_a", "node_b", "type", "value", "timestep", "hour"]
        )

    # Extract components from varname
    extracted_data = cur_flow_vars["varname"].str.extract(flow_var_pattern, expand=True)
    cur_flow_vars[["type", "node_a", "node_b", "timestep"]] = extracted_data

    # Convert timestep to integer
    cur_flow_vars["timestep"] = cur_flow_vars["timestep"].astype(int)

    # Calculate absolute hour
    # Assuming sim_horizon is the number of timesteps within one step_k
    # and step_k is 1-indexed.
    cur_flow_vars["hour"] = cur_flow_vars["timestep"] + sim_horizon * (step_k - 1)

    final_columns = ["node_a", "node_b", "value", "type", "timestep", "hour"]
    return cur_flow_vars[final_columns]


def parse_syswide_variables(
    solution: pd.DataFrame, sim_horizon: int, step_k: int
) -> pd.DataFrame:
    """
    The system-wide variables are in the (t) format.

    Args:
        solution: The solution DataFrame.
        sim_horizon: The length of the simulation horizon.
        step_k: The current simulation period.

    Returns:
        pd.DataFrame: The system-wide variables DataFrame
    """
    syswide_var_pattern = r"(.+)\[(\d+)\]"
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
    """Parse the LMP dictionary and return a DataFrame.

    Args:
        lmp: The dictionary of LMP values.
        sim_horizon: The length of the simulation horizon.
        step_k: The current simulation period.

    Returns:
        pd.DataFrame: The LMP DataFrame.
    """
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


def get_lines_params() -> pd.DataFrame:
    """Return a dataframe of line parameters, located in database/transmission_params.csv"""
    return pd.read_csv(
        os.path.join(get_database_dir(), "transmission_params.csv"),
        header=0,
    )


def create_geoseries_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["geometry"] = df.apply(
        lambda row: LineString(
            [(row["source_lon"], row["source_lat"]), (row["sink_lon"], row["sink_lat"])]
        ),
        axis=1,
    )

    df["source_location"] = df.apply(
        lambda row: Point(row["source_lon"], row["source_lat"]), axis=1
    )
    df["sink_location"] = df.apply(
        lambda row: Point(row["sink_lon"], row["sink_lat"]), axis=1
    )

    # Plotting the substations requires columns to be a GeoSeries
    df["source_location"] = gpd.GeoSeries(df["source_location"])
    df["sink_location"] = gpd.GeoSeries(df["sink_location"])
    return df


def get_capacity_value(t: int, unit: str, step_k: int, capacity_df) -> float:
    """Get the capacity value for a given unit and timestep.
    Args:
        t: The timestep.
        unit: The unit name.
        step_k: The current simulation period.
        capacity_df: The dataframe containing the capacity values.

    Returns:
        The capacity value for the given unit and timestep.
    """
    hours_per_timestep = 24  # For rolling horizon
    value = capacity_df.loc[t + (step_k - 1) * hours_per_timestep, unit]
    if isinstance(value, pd.Series):
        return value.iloc[0]
    return value
