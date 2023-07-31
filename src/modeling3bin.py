'''This is an implementation of the Tight formulation'''

# TODO: Support running simulation
# TODO: Fix c_trajec_up_bound and the two related constraints


from math import floor, pi

import gurobipy as gp
from gurobipy import GRB
import pandas as pd


from process_data import (
    process_transmission_data, get_arcs, 
    create_init_condition, get_fuel_prices
    )


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

thermal_econ_params = pd.read_csv(
    '..\\data\\user_inputs\\generators.csv', 
    header = 0, index_col = 'name', 
    usecols = ['name', 'operation_cost', 'fixed_cost', 'heat_rate']
    )


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

# Get the initial conditions
(
 initial_p, initial_u, initial_v, initial_min_on, initial_min_off
 ) = create_init_condition()


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

re_cap = pd.read_csv(
    '..\\data\\user_inputs\\renewables.csv', 
    header = 0).drop(DATE_COLS, axis=1)

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
p = model.addVars(thermal_units, range(1,T+1), vtype=GRB.CONTINUOUS, lb=0, name='p')

# The maximum power available above minimum capacity is in MW
pbar = model.addVars(thermal_units, timesteps, vtype=GRB.CONTINUOUS, lb=0, name='pbar')

# Separate the renewable dispatch variable
prnw = model.addVars(
    re_units, range(1,T+1), vtype=GRB.CONTINUOUS, lb=0, name='prnw')

# p2 = model.addVars(thermal_units, range(1,T+1), vtype=GRB.CONTINUOUS, lb=0, name='p2')

# Spinning reserve is in MW
spin = model.addVars(thermal_units, timesteps, vtype=GRB.CONTINUOUS, lb=0, name='spin')

# System reserve is in MW
rsys = model.addVars(timesteps, vtype=GRB.CONTINUOUS, lb=0, name='rsys')

# The flow variable f(a,b,t) represents the flow in the
# line segment (a,b) at hour t in MW/hr).
# If the flow is positive, then energy flows
# from a to b. In contrast, a negative value represents energy
# flowing from b to a.
# We set the bounds based on the largest transmission line.
flow = model.addVars(
    arcs, timesteps,
    lb = -max_linecap,
    ub = max_linecap,
    vtype = GRB.CONTINUOUS,
    name = 'flow'
    )

# We adopt the 2-bin formulation with unit status and switch-on variables
u = model.addVars(thermal_units, timesteps, vtype=GRB.BINARY, name='status')
v = model.addVars(thermal_units, timesteps, vtype=GRB.BINARY, name='on')
w = model.addVars(thermal_units, timesteps, vtype=GRB.BINARY, name='shut')

# The volt angles are in radians
# theta = model.addVars(
# nodes, timesteps, vtype=GRB.CONTINUOUS, lb=-pi, ub=pi, name='volt_angle')

theta = model.addVars(
    nodes, timesteps, lb=-2000000000, vtype=GRB.CONTINUOUS, name='volt_angle'
    )

# Load mismatch variables
s_pos = model.addVars(
    nodes, timesteps, vtype=GRB.CONTINUOUS, lb = 0, name='s_pos')

s_neg = model.addVars(
    nodes, timesteps, vtype=GRB.CONTINUOUS, lb = 0, name='s_neg')

# System wide excess. I don't think we need this
# sys_shortfall = model.addVars(timesteps, vtype=GRB.CONTINUOUS, lb = 0, name='load_under')

model.update()


#---- Section: Objective function
def set_objective():
    '''The objective function has four components: fixed cost, variable cost,
    start-up cost, and shortfall cost.
    '''
    fuel_prices = pd.read_csv(
        '..\\data\\user_inputs\\fuel_price.csv', header = 0
        ).drop(DATE_COLS, axis=1)
    
    econ_params = pd.read_csv(
        '..\\data\\user_inputs\\generators.csv', 
        header = 0, index_col = 'name', 
        usecols = ['name', 'operation_cost', 'fixed_cost', 'startup_cost']
        )
    
    heat_rates = pd.read_csv(
        '..\\data\\user_inputs\\generators.csv', 
        header = 0, index_col = 'name', 
        usecols = ['name', 'heat_rate']
        )
    
    opex_coeffs = {
        (unit_g, t): (fuel_prices.loc[t, unit_g] * heat_rates.loc[unit_g])[0]
            + econ_params.loc[unit_g, 'operation_cost']
        for t in range(1, 25) for unit_g in thermal_units
        }
    
    fixed_coeffs = {
        (unit_g, t): max_cap[unit_g] * econ_params.loc[unit_g, 'fixed_cost']
        for t in range(1, 25) for unit_g in thermal_units
        }
    
    startup_coeffs = {
        (unit_g, t): max_cap[unit_g] * econ_params.loc[unit_g, 'startup_cost']
        for t in range(1, 25) for unit_g in thermal_units
        }
    
    # Define costs
    operation_expr = p.prod(opex_coeffs)
    fixed_expr = u.prod(fixed_coeffs)
    startup_expr = v.prod(startup_coeffs)
    shortfall_expr = (
        fuel_prices.loc[0, 'shortfall'] * (gp.quicksum(s_pos) + gp.quicksum(s_neg))
        )
    
    model.setObjective(
        operation_expr + fixed_expr + startup_expr + shortfall_expr,
        sense = GRB.MINIMIZE)
    
    

#---- Section: Ramping limits   

def c_get_p():
    ''' A variable in case we do not want to manually dispatch'''
    model.addConstrs(
        (
            p2[unit_g, t] == p[unit_g, t] + min_cap[unit_g] * u[unit_g, t]
            for unit_g in thermal_units for t in timesteps
            ),
        name = 'get_p'
        )
    
    
def c_link_pu():
    model.addConstrs(
        (
            p2[unit_g, t] <= max_cap[unit_g] * u[unit_g, t]
            for unit_g in thermal_units for t in timesteps
            ),
        name = 'link_pu'
        )
    

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
            u[unit_g, 1] - initial_u[unit_g][T] # Last hour of the previous iteration
            <= initial_v[unit_g][T]
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
        min_UT = min(initial_min_on[unit_g][T], T)
        model.addConstr(
            u.sum(unit_g, range(1, min_UT+1)) == min_UT,
            name = 'minUpInit'
            )


def c_min_down_init():
    for unit_g in thermal_units:
        # Find the min between the required downtime and the simulation horizon
        min_DT = min(initial_min_off[unit_g][T], T)
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
        LHS =  gp.quicksum([w[unit_g, i] for i in range(t-TD_g+1, t+1)])
        model.addConstr(
            LHS <= 1 - initial_u[unit_g][T], 
            name = 'minDown' + f'_{unit_g}_{t}')
        
        for t in range(TD_g+1, T+1):
            LHS =  gp.quicksum([w[unit_g, i] for i in range(t-TD_g+1, t+1)])
            model.addConstr(
                LHS <= 1 - u[unit_g, t], 
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



def c_peak_up_bound():
    # Equation 23a
    
    # The inequalities apply when TU == 1
    model.addConstrs(
        (
            p[unit_g, t] + spin[unit_g, t]
            <= (max_cap[unit_g] - min_cap[unit_g]) * u[unit_g, t]
                - (max_cap[unit_g] - SU[unit_g]) * v[unit_g, t]
                - max(0, (SU[unit_g] - SD[unit_g])) * w[unit_g, t+1]
            for t in range(1, T) for unit_g in thermal_units if TU[unit_g] == 1
         ),
        name = 'peakUpBnd'
        )


def c_peak_down_bound():
    # Equation 23b
    # The inequalities apply when TU == 1
    model.addConstrs(
        (
            p[unit_g, t] + spin[unit_g, t]
            <= (max_cap[unit_g] - min_cap[unit_g]) * u[unit_g, t]
                - (max_cap[unit_g] - SD[unit_g]) * w[unit_g, t+1]
                - max(0, (SD[unit_g] - SU[unit_g])) * v[unit_g, t]
            for t in range(1, T) for unit_g in thermal_units if TU[unit_g] == 1
         ),
        name = 'peakDownBnd'
        )


def c_trajec_up_bound():
    # Equation 38
    for unit_g in thermal_units:
        # Calculate the time to full ramp-up
        time_RU = floor((max_cap[unit_g] - SU[unit_g])/RU[unit_g])
        
        if TU[unit_g]-2 >= time_RU:
            # The min of (TU - 2, TRU) is the number of periods in the previous
            # simulation that must be traced back to address the changing
            # upper bound due to ramping.
            min_val = min(TU[unit_g]-2, time_RU)
            
            # Since the ineqalities involve t+1 index, we only iterate thru T-1
            for t in range(1, T):
                # Define the summation term
                sum_term = 0
                for i in range(0, min_val+1):
                    # Decide if we need to refer back to the previous iteration
                    if t-i > 0:
                        sum_term += (
                            (max_cap[unit_g] - SU[unit_g] - i*RU[unit_g]) 
                                * v[unit_g, t-i]
                            )
                    else:
                        sum_term += (
                            (max_cap[unit_g] - SU[unit_g] - i*RU[unit_g]) 
                                * initial_v[unit_g][T + t - i]
                            )
                
                model.addConstr(
                    (
                        pbar[unit_g, t] + min_cap[unit_g]*u[unit_g, t]
                        <= max_cap[unit_g]*u[unit_g, t]
                            - (max_cap[unit_g] - SD[unit_g])*w[unit_g, t+1]
                            - sum_term
                            ),
                    name = 'trajecUpBnd' + f'_{unit_g}_{t}'
                    )
            
        # When UT-2 < time_RU, the above inequalities do not cover
        # the entire start-up and ramping trajectory. Hence, we can
        # cover an additional time period with additional inequalities
        # up to the last hour of T.
        if TU[unit_g]-2 < time_RU:
            
            # Note TU_g - 1, which is different from the above
            min_val = min(TU[unit_g]-1, time_RU)
            
            for t in timesteps:
                # Define the summation term
                sum_term = 0
                for i in range(0, min_val+1):
                    # Decide if we need to refer back to the previous iteration
                    if t-i > 0:
                        sum_term += (
                            (max_cap[unit_g] - SU[unit_g] - i*RU[unit_g]) 
                                * v[unit_g, t-i]
                            )
                    else:
                        sum_term += (
                            (max_cap[unit_g] - SU[unit_g] - i*RU[unit_g]) 
                                * initial_v[unit_g][T + t - i]
                            )
            
            model.addConstr(
                (
                    pbar[unit_g, t] + min_cap[unit_g]*u[unit_g, t]
                    <= max_cap[unit_g]*u[unit_g, t]
                        - sum_term
                        ),
                name = 'trajecUpBnd2' + f'_{unit_g}_{t}'
                )


def c_trajec_down_bound():
    for unit_g in thermal_units:
        
        time_RU = floor((max_cap[unit_g] - SU[unit_g])/RU[unit_g])
        time_RD = floor((max_cap[unit_g] - SU[unit_g])/RD[unit_g])
        
        for t in timesteps:
            KSD_t = min(time_RD, TU[unit_g]-1, T-t-1)
            
            # Omit adding inequalities if KSD < 0 because
            # c_trajec_up_bound dominates.
            if KSD_t <= 0:
                continue
            
            # KSD_t must be positive, but we have already checked above
            KSU_t = min( time_RU, TU[unit_g] - 2 - KSD_t, t-1 )
            
            # First summation term
            sum_1 = 0
            for i in range(KSD_t+1):    
                sum_1 += (
                    (max_cap[unit_g] - SD[unit_g] - i*RD[unit_g])*w[unit_g, t+1+i]
                    )
            
            # Second summation term
            sum_2 = 0
            for i in range(KSU_t+1):
                sum_2 += (
                    (max_cap[unit_g] - SU[unit_g] - i*RU[unit_g])*v[unit_g, t-i]
                    )
            
            model.addConstr(
                (
                    p[unit_g, t] + min_cap[unit_g]*u[unit_g, t]
                    <= (
                        max_cap[unit_g] - min_cap[unit_g])*u[unit_g, t]
                        - sum_1 - sum_2
                    ),
                name = 'trajecDownBnd'
                )
            
            

#---- Section: Ramp limits

def c_ramp_up():
    # Ramp up when t=1 is dependent on the initial condition at t=0
    t = 1
    model.addConstrs(
        (
            pbar[unit_g, t] - initial_p[unit_g][T] 
            <= (SU[unit_g] - min_cap[unit_g] - RU[unit_g]) * v[unit_g, t]
                + RU[unit_g] * u[unit_g, t]
            for unit_g in thermal_units
            ),
        name = 'rampUpInit'
        )
    
    model.addConstrs(
        (
            pbar[unit_g, t] - p[unit_g, t-1] 
            <= (SU[unit_g] - min_cap[unit_g] - RU[unit_g]) * v[unit_g, t]
                + RU[unit_g] * u[unit_g, t]
            for t in range(2, T+1) for unit_g in thermal_units
            ),
        name = 'rampUp'
        )


def c_ramp_down():
    # Ramping when t=1 is dependent on the initial condition at t=0
    t = 1
    model.addConstrs(
        (
            initial_p[unit_g][T+t-1] - p[unit_g, t]
            <= (SD[unit_g] - min_cap[unit_g] - RD[unit_g]) * w[unit_g, t]
                + RD[unit_g] * initial_u[unit_g][T]
            for unit_g in thermal_units
            ),
        name = 'rampDownInit'
        )
    
    # Ramping at other timesteps
    model.addConstrs(
        (
            p[unit_g, t-1] - p[unit_g, t]
            <= (SD[unit_g] - min_cap[unit_g] - RD[unit_g]) * w[unit_g, t]
                + RD[unit_g] * u[unit_g, t-1]
            for t in range(2, T+1) for unit_g in thermal_units
            ),
        name = 'rampDown'
        )



#---- Section: System constraints
def c_flow_bound():
    model.addConstrs(
        (
            flow[a, b, t] <= linecap[(a, b)]
            for (a, b) in arcs for t in timesteps
            ),
        name = 'maxFlow'
        )
    model.addConstrs(
        (
            flow[a, b, t] >= -linecap[(a, b)]
            for (a, b) in arcs for t in timesteps
            ),
        name = 'minFlow'
        )
    

def c_angle_dff():
    model.addConstrs(
        (
            flow[a, b, t] == suscept.loc[t, (a, b)] * (theta[a, t] - theta[b, t])
            for (a, b) in arcs for t in timesteps
        ),
        name = 'angleDiffForward'
        )
    
    model.addConstrs(
        (
            flow[a, b, t] == suscept.loc[t, (a, b)] * (theta[a, t] - theta[b, t])
            for (a, b) in arcs for t in timesteps
        ),
        name = 'angleDiffBack'
        )
    

def c_ref_node():
    model.addConstrs(
        (theta[max_node, t] == 0 for t in timesteps), 
        name='refNode'
        )


def c_flow_balance():
    # TODO: FIX IMPLEMENTATION
    # this allows flow_ab + flow_ba = 0 with non-zero flows
    # In reality, if the demand is zero, then there should be no flow
    # Must link flow to generation...
    for t in timesteps:
        for (a, b) in arcs:
            # If n is a thermal unit, then it can generate energy
            if a in thermal_units:
                thermal_gen = p[a, t] + min_cap[a]*u[a, t]
            else: 
                thermal_gen = 0
            
            # If n has renewables, then it can generate energy
            if a in re_units:
                re_gen = prnw[a, t]
            else:
                re_gen = 0
                
            # Get the demand of node n at time t
            if a in nodes_w_demand:
                demand_a_t = demand.loc[t, a]
                shortfall = s_pos[a, t] - s_neg[a, t]
            else:
                demand_a_t = 0
                shortfall = 0
            
            model.addConstr(
                thermal_gen + re_gen 
                    - gp.quicksum(
                        flow[x, y, t] for (x, y) in arcs if (x==a)
                        )
                    + gp.quicksum(
                        flow[x, y, t] for (x, y) in arcs if (y==a)
                        )
                    + shortfall
                == demand_a_t
                )
        

def c_reserve_req():
    # Modified equation 67 but exclude the system-wide shortfall
    model.addConstrs(
        (
            gp.quicksum(pbar[unit_g, t] for unit_g in thermal_units)
                + rsys[t]
            >= gp.quicksum(demand.loc[t, n] for n in nodes_w_demand) + spin_req[t]
            for t in timesteps
            ),
        name = 'reserveReq'
        )


def c_renewables_bound():
    model.addConstrs(
        (
            prnw[unit_w, t] <= re_cap.loc[t, unit_w]
            for t in timesteps for unit_w in re_units
            ),
        name = 'renewLimit'
        )


#---- Section: Update parameters for the next simulation
# initial_min_on = None
# initial_min_off = None

# initial_u = None

# initial_p = None
# initial_pbar = None




if __name__ == '__main__':
    print('Jigglypuff')
