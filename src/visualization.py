import pandas as pd
import matplotlib.pyplot as plt

from scratch3bin import build_model
from process_result import get_nodehour


###### Model Results
# Load parameters
min_cap = pd.read_csv(
    '..\\user_inputs\\unit_param.csv', 
    header=0, index_col='name', usecols=['name', 'min_capacity'])\
    .to_dict()['min_capacity']

fuel_map = pd.read_csv(
    '..\\user_inputs\\fuel_map.csv', 
    header = 0, index_col='name', usecols = ['name', 'fuel_type']).to_dict()['fuel_type']


# Load the model and results
model = build_model()

all_vars = model.getVars()
values = model.getAttr("X", all_vars)
names = model.getAttr("VarName", all_vars)


results = var_node_t.copy()
# results = pd.DataFrame({'varname':names, 'value':values})
# pat_vartype = r'(\w+)\['
# results[['vartype']] = results['varname'].str.extract(pat_vartype, expand=True)


###### Process variables
# Extract the unit status
on_df = results[results['vartype'] == 'status']
on_df = pd.concat(
    [get_nodehour(on_df, varname='on'), on_df[['varname', 'value']]], 
    axis=1)

on_map = on_df[['node', 'hour', 'value']].set_index(['node', 'hour']).to_dict()['value']


# Extract the thermal dispatch
p_df = results[results['vartype'] == 'p']
thermal_dispatch = get_nodehour(p_df, varname='p')
thermal_dispatch = pd.concat([thermal_dispatch, p_df[['varname', 'value']]], axis=1)
thermal_dispatch['dispatch'] = thermal_dispatch.apply(
    lambda x: x['value'] + min_cap[x['node']]*on_map[x['node'], x['hour']], axis=1)

thermal_dispatch = thermal_dispatch.set_index('varname')
thermal_dispatch = thermal_dispatch.drop('value', axis=1)


# Add the renewables dispatch
prnw_df = results[results['vartype'] == 'prnw']
rnw_dispatch = get_nodehour(prnw_df, varname='prnw')
rnw_dispatch = pd.concat([rnw_dispatch, prnw_df[['varname', 'value']]], axis=1)

rnw_dispatch = rnw_dispatch.set_index('varname')
rnw_dispatch = rnw_dispatch.rename(columns={'value':'dispatch'})


# Add the shortfall
shortfall_df = results[results['vartype'] == 's_pos']

sf_dispatch = get_nodehour(shortfall_df, varname='s_pos')
sf_dispatch = pd.concat([sf_dispatch, shortfall_df[['varname', 'value']]], axis=1)

sf_dispatch = sf_dispatch.set_index('varname')
sf_dispatch = sf_dispatch.rename(columns={'value':'dispatch'})


# Combine the thermal dispatch and the renewable dispatch
total_dispatch = pd.concat(
    [thermal_dispatch, rnw_dispatch, sf_dispatch], 
    axis=0)

total_dispatch['fuel_type'] = total_dispatch.apply(lambda x: fuel_map[x['node']], axis=1)


total_dispatch = total_dispatch.reset_index(drop=True)

total_dispatch = total_dispatch[['fuel_type', 'dispatch', 'hour']]\
    .groupby(['fuel_type', 'hour']).sum()
    
total_dispatch = total_dispatch.reset_index()
total_dispatch = total_dispatch.pivot(columns=['hour'], index=['fuel_type']).T

total_dispatch = total_dispatch.reset_index(drop=True)




###### Plot the fuel mix
# Plot the dispatch and status of each thermal unit
fig, ax = plt.subplots(figsize=(8, 5))
total_dispatch.plot.bar(
    stacked = True,
    ax = ax
    )
ax.legend(bbox_to_anchor=(1, 1))
ax.set_ylabel('Power (MW)')
ax.set_xlabel('Hour')
ax.set_ylim([0, 750])
plt.show()





###### Plot the on/off status of individual thermal units

# Check that each thermal unit satisfies the minimum on/off duration
for unit_g in thermal_dispatch.node.unique():
    # Extract the dispatch of each thermal unit and plot the value
    df1 = thermal_dispatch[thermal_dispatch.node == unit_g]
    df2 = on_df[on_df['node'] == unit_g]
    
    fig, ax1 = plt.subplots(figsize=(8, 5))
    ax2 = ax1.twinx()
    
    line1 = ax1.step(
        df1['hour'], df1['dispatch'], 
        where = 'mid', color = 'b', label = 'Power')
    line2 = ax2.bar(
        df2['hour'], df2['value'], 
        color='k', alpha=0.2,
        label='Unit status')
    
    ax1.set_xlabel('Hour')
    ax1.set_ylabel('Power (MW)')
    
    ax1.set_xticks(range(1,25))
    ax1.tick_params(axis='x', labelrotation=45)
    
    plt.title(unit_g)
    
    plt.show()
