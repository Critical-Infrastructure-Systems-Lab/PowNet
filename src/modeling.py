'''This is an implementation of the Tight formulation'''

# TODO: Support running simulation
# TODO: Fix c_trajec_up_bound and the two related constraints


from math import floor, pi

import gurobipy as gp
from gurobipy import GRB
import pandas as pd

from process_data import process_transmission_data, get_arcs



'''
Style guide: 
    * Parameters are capitalized letters or full name. A parameter is a dict class
      unless it represents time series.
    * Variables are uncapitalized letters
'''


HOURLY_TRANSMISSION_AVAI = False


DATE_COLS = ['year', 'month', 'day', 'hour']

#---- Create a Gurobipy environment
model = gp.Model('tight_formulation')



#---- Section: System parameters

T = 24
timesteps = range(1, T+1) # Be careful with Python indexing!

thermal_units = pd.read_csv(
    '..\\data\\user_inputs\\generators.csv', 
    header = 0, index_col='name', usecols = ['name']).index.tolist()

re_units = pd.read_csv(
    '..\\data\\user_inputs\\renewables.csv', 
    header = 0).columns.tolist()
re_units = [col for col in re_units if col not in DATE_COLS]

all_units = set(thermal_units).union(set(re_units))


nodes = pd.read_csv(
    '..\\data\\user_inputs\\transmission.csv', 
    header = 0, usecols = ['source', 'sink'])
nodes = set(nodes.source).union(set(nodes.sink))

arcs = get_arcs()


# Define the neighbors of each node
node_neighbors = {a:[] for (a, b) in arcs}

for (a, b) in arcs:
    node_neighbors[a].append(b)


max_node = pd.read_csv(
    '..\\data\\user_inputs\\demand.csv', header = 0)\
    .drop(DATE_COLS, axis=1).idxmax().idxmax()

nodes_w_demand = pd.read_csv(
    '..\\data\\user_inputs\\demand.csv', header = 0)\
    .drop(DATE_COLS, axis=1).columns.tolist()

#---- Section: Thermal unit parameters

# Treat the initial dispatched power as a constant that will be updated
# at every simulation period
initial_p = pd.read_csv(
    '..\\data\\user_inputs\\initial_condition.csv', 
    header=0, index_col='name', usecols=['name', 'init_p']).to_dict()['init_p']

initial_u = pd.read_csv(
    '..\\data\\user_inputs\\initial_condition.csv', 
    header=0, index_col='name', usecols=['name', 'init_u']).to_dict()['init_u']

initial_v = None


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

# Max/min capacity of thermal units
max_cap = pd.read_csv(
    '..\\data\\user_inputs\\generators.csv', 
    header=0, index_col='name', usecols=['name', 'max_capacity'])\
    .to_dict()['max_capacity']

min_cap = pd.read_csv(
    '..\\data\\user_inputs\\generators.csv', 
    header=0, index_col='name', usecols=['name', 'min_capacity'])\
    .to_dict()['min_capacity']

# Minimum down/up time of units
TD = pd.read_csv(
    '..\\data\\user_inputs\\generators.csv', 
    header=0, index_col='name', usecols=['name', 'min_downtime'])\
    .to_dict()['min_downtime']

TU = pd.read_csv(
    '..\\data\\user_inputs\\generators.csv', 
    header=0, index_col='name', usecols=['name', 'min_uptime'])\
    .to_dict()['min_uptime']

# Start-up rate (MW/hr) and shutdown rate (MW/hr)
SD = pd.read_csv(
    '..\\data\\user_inputs\\generators.csv', 
    header=0, index_col='name', usecols=['name', 'min_capacity'])\
    .to_dict()['min_capacity']
# Due to the lack of data, we assume the shutdown rate is equal to the start-up rate
SU = SD.copy()

# Ramp up/down rate (MW/hr)
RD = pd.read_csv(
    '..\\data\\user_inputs\\generators.csv', 
    header=0, index_col='name', usecols=['name', 'ramp_rate'])\
    .to_dict()['ramp_rate']
RU = RD.copy()



#---- Section: Timeseries-based parameters

demand = pd.read_csv('..\\data\\user_inputs\\demand.csv', header = 0)\
    .drop(DATE_COLS, axis=1)

spin_req = demand.sum(axis=1) * 0.15

re_cap = None

# Transmission parameters
if HOURLY_TRANSMISSION_AVAI:
    # Line susceptance in each arc (unit??)
    suscept = pd.read_csv(
        '..\\data\\user_inputs\\susceptance.csv', 
        header=0, index_col=['source', 'sink'], usecols=['source', 'sink', 'susceptance'])
    
    # Line capacity in MW/hr
    linecap = pd.read_csv(
        '..\\data\\user_inputs\\line_cap.csv', 
        header=0, index_col=['source', 'sink'], usecols=['source', 'sink', 'line_cap'])
else:
    suscept, linecap = process_transmission_data()

# Only test with the first 24 hours for now
suscept = suscept.iloc[:24]
suscept.index = suscept.index+1

# Need the maximum line capacity to define the bounds of a variable
max_linecap = linecap.max().max()



#---- Section: Variables
# The power above minimum capacity is in MW
p = model.addVars(all_units, range(1,T+1), vtype=GRB.CONTINUOUS, lb=0, name='p')

# The maximum power available above minimum capacity is in MW
pbar = model.addVars(all_units, timesteps, vtype=GRB.CONTINUOUS, lb=0, name='pbar')

# Spinning reserve is in MW
spin = model.addVars(thermal_units, timesteps, vtype=GRB.CONTINUOUS, lb=0, name='spin')

# The flow variable f(a,b,t) represents the flow in the
# line segment (a,b) at hour t in MW/hr).
# If the flow is positive, then energy flows
# from a to b. In contrast, a negative value represents energy
# flowing from b to a.
# We set the bounds based on the largest transmission line.
flow = model.addVars(
    arcs, timesteps,
    lb = 0,
    ub = max_linecap,
    vtype = GRB.CONTINUOUS,
    name = 'flow'
    )

# We adopt the 2-bin formulation with unit status and switch-on variables
u = model.addVars(thermal_units, timesteps, vtype=GRB.BINARY, name='status')
v = model.addVars(thermal_units, timesteps, vtype=GRB.BINARY, name='on')

# The volt angles are in radians
theta = model.addVars(nodes, timesteps, vtype=GRB.CONTINUOUS, lb=-pi, ub=pi, name='volt_angle')

# Load mismatch variables
load_over = model.addVars(
    nodes, timesteps, vtype=GRB.CONTINUOUS, lb = 0, name='load_over')

load_under = model.addVars(
    nodes, timesteps, vtype=GRB.CONTINUOUS, lb = 0, name='load_under')

# System wide excess. I don't think we need this
# sys_shortfall = model.addVars(timesteps, vtype=GRB.CONTINUOUS, lb = 0, name='load_under')

model.update()



#---- Section: Ramping limits

def c_link_p():
    # Linking the p, pbar, and spin together
    model.addConstrs(
        (
            pbar[unit_g, t] == p[unit_g, t] + spin[unit_g, t]
            for unit_g in thermal_units for t in timesteps
            ),
        name = 'link_p'
        )


def c_link_unit_status():
    # At t=1, the variables are linked to constants that describe
    # the system at t=0
    model.addConstrs(
        (
            u[unit_g, 1] - initial_p[unit_g] 
            <= initial_min_on[unit_g] 
            for unit_g in thermal_units
            ),
        name = 'link_uv_init'
        )
    # For timesteps t in [2, 24]
    model.addConstrs(
        (
            u[unit_g, t] - u[unit_g, t-1] 
            <= v[unit_g, t] 
            for t in range(2, T+1) for unit_g in thermal_units
            ),
        name = 'link_uv'
        )


def c_min_up_init():
    for unit_g in thermal_units:
        # Find the min between the required uptime and the simulation horizon
        min_UT = min(initial_min_on[unit_g], T)
        model.addConstr(
            u.sum(unit_g, range(1, min_UT+1)) == min_UT,
            name = 'minUpInit'
            )


def c_min_down_init():
    for unit_g in thermal_units:
        # Find the min between the required downtime and the simulation horizon
        min_DT = min(initial_min_off[unit_g], T)
        model.addConstr(
            u.sum(unit_g, range(1, min_DT+1)) == 0,
            name = 'minDownInit'
            )


def c_min_up():
    for unit_g in thermal_units:
        TU_g = TU[unit_g]
        for t in range(TU_g, T+1):
            LHS =  gp.quicksum([v[unit_g, i] for i in range(t-TU_g+1, t+1)])
            model.addConstr(LHS <= u[unit_g, t], name='minUp' + f'_{unit_g}_{t}')


def c_min_down():
    for unit_g in thermal_units:
        TD_g = TD[unit_g]
        
        # When t = TD, the inequality contains the initial condition u[g, 0],
        # which we treat as a parameter
        t = TD_g
        LHS =  gp.quicksum([v[unit_g, i] for i in range(t-TD_g+1, t+1)])
        model.addConstr(
            LHS <= 1 - initial_u[unit_g], 
            name = 'minDown' + f'_{unit_g}_{t}')
        
        for t in range(TD_g+1, T+1):
            LHS =  gp.quicksum([v[unit_g, i] for i in range(t-TD_g+1, t+1)])
            model.addConstr(
                LHS <= 1 - u[unit_g, t-TD_g], 
                name = 'minDown' + f'_{unit_g}_{t}')



#---- Section: Generation limits

def c_p_bound():
    model.addConstrs(
        (
            p[unit_g, t] <= pbar[unit_g, t]
            for t in timesteps for unit_g in thermal_units
            ),
        name = 'upper_p'
        )


def c_switch_ramp_bound():
    # Note we exclude the last timestep of T. 
    # This constraint applies only when TU_g > 1 because the RHS can be negative
    # Also, RHS can be zero when a unit has been turned on which is incorrect.
    model.addConstrs(
        (
            p[unit_g, t] + spin[unit_g, t]
            <= (SD[unit_g] - min_cap[unit_g])*u[unit_g, t]
                + (SU[unit_g] - max_cap[unit_g])*v[unit_g, t]
                + (max_cap[unit_g] - SD[unit_g])*u[unit_g, t+1]
                + (SD[unit_g] - max_cap[unit_g])*v[unit_g, t+1]
            for t in range(1, 24) for unit_g in thermal_units if TU[unit_g] > 1
            ),
        name = 'switchBound'
        )


def c_peak_up_bound(unit_g):
    # The inequalities apply when TU == 1
    model.addConstrs(
        (
            p[unit_g, t] + spin[unit_g, t]
            <= (max_cap[unit_g] - min_cap[unit_g])*u[unit_g, t]
            for t in timesteps for unit_g in thermal_units if TU[unit_g] == 1
         ),
        name = 'peakUpBound'
        )


def c_peak_down_bound(unit_g):
    # The inequalities apply when TU == 1
    model.addConstrs(
        (
            p[unit_g, t] + spin[unit_g, t]
            <= (SD[unit_g] - min_cap[unit_g])*u[unit_g, t]
                + (max_cap[unit_g] - SD[unit_g])*u[unit_g, t+1]
                + (SD[unit_g] - max_cap[unit_g])*v[unit_g, t+1]
            for t in range(1, 24) for unit_g in thermal_units if TU[unit_g] == 1
         ),
        name = 'peakDownBound'
        )


def c_trajec_up_bound(unit_g):
    # When t=1, the inequalities involve an edge case when the system 
    # turns on the unit at the last time period
    
    for unit_g in thermal_units:
        # Calculate the time to full ramp-up
        time_RU = floor((max_cap[unit_g] - SU[unit_g])/RU[unit_g])
        
        # # The inequalities require taking the minimum val
        # min_val = min(TU[unit_g]-2, time_RU)

        
        # # Define the summation term
        # sum_term = gp.quicksum(
        #     (max_cap[unit_g] - SU[unit_g] - i*RU[unit_g])*v[unit_g, t-i]
        #     for i in range(0, min_val+1)
        #     )
        
        # (
        #  pbar[unit_g, t]
        #  <= (max_cap[unit_g] - 2*min_cap[unit_g] + SD[unit_g])*u[unit_g, t]
        #      + (max_cap[unit_g] - SD[unit_g])*u[unit_g, t+1]
        #      + (SD - max_cap[unit_g])*v[unit_g, t+1]
        #      - gp.quicksum((max_cap[ for i in range(0, min_val+1))
        #  ))


def c_trajec_up_bound_short(unit_g):
    for unit_g in thermal_units:
        time_RU = floor((max_cap[unit_g] - SU[unit_g])/RU[unit_g])
        min_val = min(TU[unit_g]-1, time_RU)
        
        model.addConstrs(
         (
             pbar[unit_g, t]
             <= (max_cap[unit_g] - min_cap[unit_g])*u[unit_g, t]
                 - gp.quicksum(
                     max_cap[unit_g] - SU[unit_g] - i*RU[unit_g]*v[unit_g, t-i]
                     for i in range(0, min_val+1)
                     )
            for t in timesteps
                 ),
         name = 'trajecUpBoundShort' + f'_{unit_g}'
         )


def c_trajec_down_bound(unit_g):
    pass



#---- Section: Ramp limits

def c_ramp_up(unit_g):
    model.addConstrs(
        (
            pbar[unit_g, t] - p[unit_g, t-1] 
            <= (SU[unit_g] - min_cap[unit_g] - RU[unit_g])
            * v[unit_g, t] + RU*u[unit_g, t]
            for t in range(2, T+1)
            ),
        name = 'rampUp'
        )


def c_ramp_down(unit_g):
    # Ramping when t=1 is dependent on the initial condition at t=0
    model.addConstrs(
        (
            p[unit_g, t-1] - pbar[unit_g, t]
            <= (SD[unit_g] - min_cap[unit_g] - RD[unit_g])
                * (u[unit_g, t] - u[unit_g, t+1] + v[unit_g, t+1])
                + RD[unit_g]*u[unit_g, t-1]
            for t in range(2, T+1)
            ),
        name = 'rampDownInit'
        )
    
    # Ramping at other timesteps
    model.addConstrs(
        (
            p[unit_g, t-1] - pbar[unit_g, t]
            <= (SD[unit_g] - min_cap[unit_g] - RD[unit_g])
                * (u[unit_g, t] - u[unit_g, t+1] + v[unit_g, t+1])
                + RD[unit_g]*u[unit_g, t-1]
            for t in range(2, T+1)
            ),
        name = 'rampDown'
        )



#---- Section: System constraints
def c_angle_dff():
    model.addConstrs(
        (
            flow[a, b, t] == suscept.loc[t, (a, b)] * (theta[a, t] - theta[b, t])
            for (a, b) in arcs for t in timesteps
        ),
        name = 'angleDiff'
        )


def c_max_flow():
    model.addConstrs(
        (
            flow[a, b, t] <= linecap[(a, b)]
            for (a, b) in arcs for t in timesteps
            ),
        name = 'maxFlow'
        )
    

def c_ref_node():
    model.addConstrs(
        (theta[max_node, t] == 0 for t in timesteps), 
        name='refNode'
        )


def c_flow_balance():
    
    for (a, b) in arcs:
        for t in timesteps:
            
            # If n is a thermal unit, then it can generate energy
            if a in thermal_units:
                thermal_gen = p[a, t] + min_cap[a]*u[a, t]
            else: 
                thermal_gen = 0
            
            # If n has renewables, then it can generate energy
            if a in re_units:
                re_gen = p[a, t]
            else:
                re_gen = 0
                
            # Get the demand of node n at time t
            if a in nodes_w_demand:
                demand_a_t = demand.loc[t, a]
            else:
                demand_a_t = 0
                
            model.addConstr(
                thermal_gen 
                    + re_gen 
                    + gp.quicksum(
                        flow[x, y, t] for (x, y) in arcs if (x==a) or (y==a)
                        )
                == demand_a_t
                )
        

def c_reserve_req():
    # Modified equation 67 but exclude the system-wide shortfall
    model.addConstrs(
        (
            gp.quicksum(pbar[unit_g, t] for unit_g in all_units)
            >= gp.quicksum(demand.loc[t, n] for n in nodes_w_demand) + spin_req[t]
            for t in timesteps
            ),
        name = 'reserveReq'
        )


def c_renewables_bound():
    model.addConstrs(
        (
            p[unit_w, t] <= re_cap.loc[t, unit_w]
            for t in timesteps for unit_w in re_units
            ),
        name = 'reLimit'
        )


#---- Section: Update parameters for the next simulation
initial_min_on = None
initial_min_off = None

initial_u = None

initial_p = None
initial_pbar = None




if __name__ == '__main__':
    print('Jigglypuff')
