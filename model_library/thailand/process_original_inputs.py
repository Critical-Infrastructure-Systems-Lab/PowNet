# This script processes the inputs of the original PowNet to the format
# required by the new PowNet.
import pandas as pd
import numpy as np


#%% Creating transmission.csv
# The original implementation aggregate thermal units to a node.
# We will disaggregate them into their own node by connecting a thermal
# unit to their original node using a high capacity transmission line.
# -- Susceptance of 1 and MVA of NAN


new_colnames = ['source', 'sink', 'susceptance', 'line_cap']
transmission_old = pd.read_csv('./originals/transmission_2016.csv', header=0)
transmission_old.columns = new_colnames

thermal_units = pd.read_csv('./originals/thermal_2016.csv', header=0, usecols=['name', 'node'])

# Process only thermal units that have been aggregated to a bus
unit_mask = thermal_units['name'] != thermal_units['node']
transmission_new = thermal_units[unit_mask].copy()
transmission_new.columns = ['source', 'sink']
transmission_new['susceptance'] = 1
transmission_new['line_cap'] = 9999 

transmission_new = pd.concat([transmission_old, transmission_new], axis=0)

transmission_new.to_csv('transmission.csv', index=False)



#%% Creating fuel_price.csv
# Need to create a csv of hourly prices for solar, wind, hydro, import_hydro, 
# import_thermal, thermal_units, accordingly.

# We use dates as a basis to start a new dataframe
DATES = pd.read_csv('demand_export.csv', header=0, usecols=['year', 'month', 'day', 'hour'])
COLS2DROP = ['Year', 'Month', 'Day', 'Hour']

# filename = 'solar_2016.csv'

def get_price_df(filename, price):
    new_cols = pd.read_csv(f'./originals/{filename}', header=0)
    new_cols = new_cols.drop(COLS2DROP, axis=1).columns
    # Repeat the rows 8760 times (every hour for 365 days)
    price_array = np.ones((8760, len(new_cols))) * price
    df_out = pd.DataFrame(price_array, columns=new_cols)
    return df_out


solar_prices = get_price_df('solar_2016.csv', 0)
wind_prices = get_price_df('wind_2016.csv', 0)
hydro_prices = get_price_df('hydro_2016.csv', 0)
hydro_import_prices = get_price_df('hydro_import_2016.csv', 40)

rnw_prices = pd.concat(
    [solar_prices, wind_prices, hydro_prices, hydro_import_prices],
    axis = 1
    ).reset_index(drop=True)


# The prices for thermal units are based on its unit type
thermal_price_map = pd.read_csv('./originals/fuel_price_map.csv', header=0)
thermal_price_map = {row[1]['fuel_type']: row[1]['price'] for row in thermal_price_map.iterrows()}

thermal_units = thermal_units = pd.read_csv('./originals/thermal_2016.csv', header=0, usecols=['name', 'typ'])
thermal_units['price'] = thermal_units['typ'].map(thermal_price_map)

thermal_prices = thermal_units.drop('typ', axis=1).T.reset_index().drop('index', axis=1)
thermal_prices.columns = thermal_prices.iloc[0]
thermal_prices = thermal_prices.iloc[1:]
thermal_prices = pd.concat([thermal_prices]*8760, axis=0).reset_index(drop=True)

fuel_price = pd.concat([DATES, rnw_prices, thermal_prices], axis=1)

fuel_price['shortfall'] = 1000

fuel_price.to_csv('fuel_price.csv', index=False)


#%% Creating the fuel_map.csv
# The file maps a generator to its unit_type and fuel_type.
# We obtain the list of all generators from different files.
# Note that demand nodes are considered a generator because each has a slack variable
# Start collecting data in the following order: demand/import, solar, wind
# hydro, hydro_import, thermal_units
generators = []
unit_type = []
fuel_type = []

# Demand/Import
demand_import_nodes = pd.read_csv('./originals/load_2016.csv', header=0)
demand_import_nodes = demand_import_nodes.drop(COLS2DROP, axis=1).columns
generators.extend(demand_import_nodes)

unit_type.extend(['shortfall']*len(demand_import_nodes))
fuel_type.extend(['shortfall']*len(demand_import_nodes))

# Solar
generators.extend(solar_prices.columns)
unit_type.extend(['solar']*len(solar_prices.columns))
fuel_type.extend(['solar']*len(solar_prices.columns))

# Wind
generators.extend(wind_prices.columns)
unit_type.extend(['wind']*len(wind_prices.columns))
fuel_type.extend(['wind']*len(wind_prices.columns))

# Hydro
generators.extend(hydro_prices.columns)
unit_type.extend(['hydro']*len(hydro_prices.columns))
fuel_type.extend(['hydro']*len(hydro_prices.columns))

# Hydro_import
generators.extend(hydro_import_prices.columns)
unit_type.extend(['import']*len(hydro_import_prices.columns))
fuel_type.extend(['import']*len(hydro_import_prices.columns))

# Thermal units
thermal_units = pd.read_csv(
    'unit_param.csv', 
    header = 0, 
    usecols = ['name', 'fuel_type', 'unit_type'])

for row in thermal_units.iterrows():
    row = row[1]
    generators.append(row['name'])
    unit_type.append(row['unit_type'])
    fuel_type.append(row['fuel_type'])
    
    
fuel_map = pd.DataFrame({
    'name': generators,
    'unit_type': unit_type,
    'fuel_type': fuel_type
    })

fuel_map.to_csv('fuel_map.csv', index=True)
