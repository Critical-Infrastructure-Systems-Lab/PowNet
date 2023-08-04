import gurobipy as gp
import matplotlib.pyplot as plt
import pandas as pd

from process_result import get_nodehour_pn


##########
fuel_map = pd.read_csv(
    '..\\data\\user_inputs\\fuel_map.csv', 
    header = 0, index_col='name', usecols = ['name', 'fuel_type']).to_dict()['fuel_type']

model = gp.read('dummy_model.mps')
model.optimize()




###### Extract the results
all_vars = model.getVars()
values = model.getAttr("X", all_vars)
names = model.getAttr("VarName", all_vars)


results = pd.DataFrame({'varname':names, 'value':values})
pat_vartype = r'(\w+)\('
results[['vartype']] = results['varname'].str.extract(pat_vartype, expand=True)





###### Process variables
# Extract the unit status
on_df = results[results['vartype'] == 'on']
on_df = pd.concat(
    [get_nodehour_pn(on_df, varname='on'), on_df[['varname', 'value']]], 
    axis=1)

on_df = on_df[on_df['hour'] != 0]
on_df['hour'] = on_df['hour'] - 1

# Extract the dispatch
p_df = results[results['vartype'] == 'mwh']
dispatch = get_nodehour_pn(p_df, varname='mwh')
dispatch = pd.concat([dispatch, p_df[['varname', 'value']]], axis=1)
dispatch['fuel_type'] = dispatch.apply(lambda x: fuel_map[x['node']], axis=1)

# Ignore the first row because PowNet treats this as a variable
dispatch = dispatch.reset_index(drop=True)
dispatch = dispatch[dispatch['hour'] != 0]
dispatch['hour'] = dispatch['hour'] - 1



# Create the fuel mix dataframe
total_dispatch = dispatch[['fuel_type', 'value', 'hour']]\
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
for unit_g in on_df.node.unique():
    # Extract the dispatch of each thermal unit and plot the value
    df1 = dispatch[dispatch.node == unit_g]
    df2 = on_df[on_df['node'] == unit_g]
    
    fig, ax1 = plt.subplots(figsize=(8, 5))
    ax2 = ax1.twinx()
    
    line1 = ax1.step(
        df1['hour'], df1['value'], 
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
