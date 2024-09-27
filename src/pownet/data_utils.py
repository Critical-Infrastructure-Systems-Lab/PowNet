<<<<<<< HEAD
'''This script contains functions for processing user inputs'''
import datetime

import gurobipy as gp
import numpy as np
import pandas as pd



def get_dates(year):
    # Create dates to concatenate with the new dataframes
    dates = pd.DataFrame(
        {'date': pd.date_range(start=str(year), periods=366, freq='D')}
        )
    # Remove 29th Feb because we do not deal with them
    dates = dates.loc[dates.date.dt.strftime('%m-%d') != '02-29']
    # Remove 1st Jan of the next year in case it is included when it is not a leap year
    dates = dates.loc[dates.date.dt.strftime('%Y-%m-%d') != f'{year+1}-01-01']
    
    # In case we need three columns
    dates = dates.loc[dates.index.repeat(24)]
    dates['hour'] = np.tile(range(1, 25), 365)
=======
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
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0
    dates = dates.reset_index(drop=True)
    return dates


<<<<<<< HEAD
def get_arcs(transmission: pd.DataFrame, reverse_flow: bool = False) -> gp.tuplelist:
    if not reverse_flow:
        return gp.tuplelist(
            transmission.set_index(['source', 'sink']).index.tolist())
    else:
        arcs = gp.tuplelist(
            transmission.set_index(['source', 'sink']).index.tolist()
            )
        arcs.extend(
            transmission.set_index(['sink', 'source']).index.tolist()
            )


def get_cycles(transmission: pd.DataFrame, reverse_flow: bool =  False) -> gp.tuplelist:
    if not reverse_flow:
        pass
    else:
        raise NotImplementedError('Not yet implement cycles for reverse flow formulation.')


def get_suscept(
        transmission: pd.DataFrame,
        reverse_flow: bool = False
        ) -> pd.DataFrame:
    '''Return the hourly susceptance values as a dataframe'''
    # Arcs form an undirected graph
    arcs = get_arcs(transmission, reverse_flow=reverse_flow)
    
    # Create the susceptance file
    suscept = pd.DataFrame(
        transmission.pownet_susceptance.values, 
        index = pd.MultiIndex.from_tuples(arcs, name=['source', 'sink']),
        columns = ['susceptance']
        ).T
    
    if reverse_flow:
        # Append the suscept dataframe with segments from b to a
        suscept_rev = pd.DataFrame(
                transmission.pownet_susceptance.values, 
                index = pd.MultiIndex.from_tuples([(b,a) for (a,b) in arcs], name=['source', 'sink']),
                columns = ['susceptance']
                ).T
        suscept = pd.concat([suscept, suscept_rev], axis=1)
    
    suscept = suscept.loc[suscept.index.repeat(365*24)].reset_index(drop=True)
    return suscept
        

def get_linecap(transmission: pd.DataFrame, reverse_flow: bool = False) -> pd.DataFrame:
    arcs = get_arcs(transmission, reverse_flow=reverse_flow)
    
    # Create the line-capacity file
    linecap = pd.DataFrame(
        transmission.pownet_line_capacity.values, 
        index = pd.MultiIndex.from_tuples(arcs, name=['source', 'sink']),
        columns = ['linecap']
        ).T
    linecap = linecap.loc[linecap.index.repeat(365*24)].reset_index(drop=True)
    
    if not reverse_flow:
        return linecap
    else:
        # Reverse source-sink to get capacity for the reverse flow
        linecap_rev = pd.DataFrame(
            transmission.pownet_line_capacity.values, 
            index = pd.MultiIndex.from_tuples([(b,a) for (a,b) in arcs], name=['source', 'sink']),
            columns = ['linecap']
            ).T
        linecap_rev = linecap_rev.loc[linecap_rev.index.repeat(365*24)].reset_index(drop=True)
        return pd.concat([linecap, linecap_rev], axis=1)
        

def create_init_condition(
        thermal_units: list, 
        T: int
        ) -> dict[(str, int), dict]:
    "Return dicts of system statuses in the format {unit: {t:value}}"
    # If the user does not specify the initial condition, then we assume 
    # the system will start from a blank state with every units off.
    initial_p = {(unit_g, t): 0 for unit_g in thermal_units for t in range(1, T+1)}
=======
def get_datetime_index(year: int) -> pd.DatetimeIndex:
    dates = pd.date_range(start=f"{year}-01-01", end=f"{year+1}-01-01", freq="H")
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


def create_init_condition(thermal_units: list) -> dict[(str, int), dict]:
    """Return dicts of system statuses in the format {(unit, hour): value}"""
    # Assume thermal units in the systems are offline at the beginning
    initial_p = {unit_g: 0 for unit_g in thermal_units}
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0
    initial_u = initial_p.copy()
    initial_v = initial_p.copy()
    initial_w = initial_p.copy()

<<<<<<< HEAD
    initial_min_on = {unit_g: 0 for unit_g in thermal_units}
    initial_min_off = initial_min_on.copy()
    
    return {
        'initial_p': initial_p, 
        'initial_u': initial_u, 
        'initial_v': initial_v,
        'initial_w': initial_w,
        'initial_min_on': initial_min_on, 
        'initial_min_off': initial_min_off
        }


def get_fuel_prices(df: pd.DataFrame) -> pd.DataFrame:
    fuel_types = df.columns.to_list()
    fuel_prices = {
        (fuel_type, t): df.loc[t, fuel_type] 
        for t in range(1, 25) for fuel_type in fuel_types
        }
    return fuel_prices


def get_nodehour(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Extract the node and hour information
    pat_node_time = r'(\w+)\[(.+),(\d+)\]'
    out_df = df['varname'].str.extract(pat_node_time, expand=True)
    out_df.columns = ['vartype', 'node', 'hour']
    out_df['hour'] = out_df['hour'].astype('int')
    out_df = pd.concat([out_df, df['value']], axis=1)
    return out_df


def get_nodehour_flow(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Flow is in the (node_a, node_b, t) format
    pat_node_time = r'flow\[(.+),(.+),(\d+)\]'
    out_df = df['varname'].str.extract(pat_node_time, expand=True)
    out_df.columns = ['node_a', 'node_b', 'hour']
    out_df['hour'] = out_df['hour'].astype('int')
    out_df = pd.concat([out_df, df['value']], axis=1)
    return out_df


def get_nodehour_sys(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Extract the node and hour information
    pat_node_time = r'(.+)\[(\d+)\]'
    out_df = df['varname'].str.extract(pat_node_time, expand=True)
    out_df.columns = ['vartype', 'hour']
    out_df['hour'] = out_df['hour'].astype('int')
    out_df = pd.concat([out_df, df['value']], axis=1)
    return out_df
=======
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
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0


def get_current_time() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M")
<<<<<<< HEAD
        

=======


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
    # First check that the output directory exists. If not, create it.
    if not os.path.exists(get_output_dir()):
        os.makedirs(get_output_dir())
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
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0
