### Deprecated code which might be useful

# Treat the initial dispatched power as a constant that will be updated
# at every simulation period
initial_p = pd.read_csv(
    '..\\data\\user_inputs\\initial_condition.csv', 
    header=0, index_col='name', usecols=['name', 'init_p']).to_dict()['init_p']

initial_u = pd.read_csv(
    '..\\data\\user_inputs\\initial_condition.csv', 
    header=0, index_col='name', usecols=['name', 'init_u']).to_dict()['init_u']

# When the units are on at t=0, then the minimum uptime takes effect
initial_min_on = pd.read_csv(
    '..\\data\\user_inputs\\initial_condition.csv', 
    header=0, index_col='name', usecols=['name', 'init_min_uptime'])\
    .to_dict()['init_min_uptime']

# When the units are initially off, then the minimum downtime takes effect
# At the first simulation, the units are all off and can be switched on immediately
initial_min_off = pd.read_csv(
    '..\\data\\user_inputs\\initial_condition.csv', 
    header=0, index_col='name', usecols=['name', 'init_min_downtime'])\
    .to_dict()['init_min_downtime']