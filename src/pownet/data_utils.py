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
    dates = dates.reset_index(drop=True)
    return dates


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
    initial_u = initial_p.copy()
    initial_v = initial_p.copy()
    initial_w = initial_p.copy()

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


def get_current_time() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M")
        

