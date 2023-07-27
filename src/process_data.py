'''This script contains functions for processing user inputs'''

import gurobipy as gp
import numpy as np
import pandas as pd


# TODO: Map units to fuel type such that we can price the fuel cost per type and operation



DATE_COLS = ['year', 'month', 'day', 'hour']
DATE_START = '2016-01-01'
DATE_END = '2016-12-31'




# Process hourly transmission data
def process_transmission_data(save_file=False):
    """Create new data files with each file containing susceptance and line capacity"""
    
    transmission = pd.read_csv('..//data//user_inputs//transmission.csv', header=0)
    
    transmission.head()
    arcs = list(zip(transmission['source'], transmission['sink']))
    
    # Create dates to concatenate with the new dataframes
    dates = pd.DataFrame({'date':pd.date_range(start=DATE_START, end=DATE_END)})
    
    # Remove 29th Feb
    dates = dates.loc[dates.date.dt.strftime('%m-%d') != '02-29']
    
    # In case we need three columns
    # dates = pd.DataFrame({'year': dates.year, 'month':dates.month, 'day':dates.day})
    
    dates = dates.loc[dates.index.repeat(24)]
    
    dates['hour'] = np.tile(range(1, 25), 365)
    dates = dates.reset_index(drop=True)
    
    # Create the susceptance file
    suscept = pd.DataFrame(
        transmission.susceptance.values, 
        index = pd.MultiIndex.from_tuples(arcs, name=['source', 'sink']),
        columns = ['susceptance']
        ).T
    
    # Append the suscept dataframe with segments from b to a
    suscept_rev = pd.DataFrame(
            transmission.susceptance.values, 
            index = pd.MultiIndex.from_tuples([(b,a) for (a,b) in arcs], name=['source', 'sink']),
            columns = ['susceptance']
            ).T
    
    suscept = pd.concat([suscept, suscept_rev], axis=1)
    
    suscept = suscept.loc[suscept.index.repeat(365*24)].reset_index(drop=True)
    
    
    # suscept = pd.concat([dates, suscept], axis=1)
    
    # Create the line-capacity file
    linecap = pd.DataFrame(
        transmission.line_cap.values, 
        index = pd.MultiIndex.from_tuples(arcs, name=['source', 'sink']),
        columns = ['linecap']
        ).T
    
    # Reverse source-sink to get capacity for the reverse flow
    linecap_rev = pd.DataFrame(
        transmission.line_cap.values, 
        index = pd.MultiIndex.from_tuples([(b,a) for (a,b) in arcs], name=['source', 'sink']),
        columns = ['linecap']
        ).T
    
    linecap = pd.concat([linecap, linecap_rev], axis=1)
    
    if save_file:
        # Save the dataframes as pickles
        output_path = '..\\data\\processed_inputs\\'
        suscept.to_pickle(output_path + 'susceptance.pkl')
        linecap.to_pickle(output_path + 'line_cap.pkl')
    
    return suscept, linecap


def get_arcs():
    arcs_ab = pd.read_csv(
        '..\\data\\user_inputs\\transmission.csv', 
        header = 0, index_col = ['source', 'sink'], usecols=['source', 'sink']
        ).index.tolist()

    arcs_ba = pd.read_csv(
        '..\\data\\user_inputs\\transmission.csv', 
        header = 0, index_col = ['sink', 'source'], usecols=['source', 'sink']
        ).index.tolist()

    return gp.tuplelist(arcs_ab + arcs_ba)


def create_init_condition():
    "Return dicts of system statuses in the format {unit: {t:value}}"

    thermal_units = pd.read_csv(
        '..\\data\\user_inputs\\initial_condition.csv', 
        header=0, usecols=['name']).name.tolist()
    
    # If the user does not specify the initial condition, then we assume 
    # the system will start from a blank state with every units off.
    initial_p = {unit_g: {t: 0 for t in range(1,25)} for unit_g in thermal_units}
    initial_u = initial_p.copy()
    initial_v = initial_p.copy()
    initial_min_on = initial_p.copy()
    initial_min_off = initial_p.copy()
    
    return initial_p, initial_u, initial_v, initial_min_on, initial_min_off


def get_fuel_prices():
    df = pd.read_csv(
        '..\\data\\user_inputs\\fuel_price.csv', header = 0
        ).drop(DATE_COLS, axis=1)
    
    df = df.iloc[:24]
    df.index = df.index+1
    
    fuel_types = df.columns.to_list()
    
    fuel_prices = {
        (fuel_type, t): df.loc[t, fuel_type] 
        for t in range(1, 25) for fuel_type in fuel_types
        }
    
    return fuel_prices
