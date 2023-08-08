from math import floor

from gurobipy import GRB
import gurobipy as gp

from core.input import SystemInput



#---- Section: 
class ModelBuilder():
    def __init__(self, inputs: SystemInput) -> None:

        self.model = None
        
        # Variables
        self.p = None
        self.pbar = None
        
        self.prnw = None # renewables
        self.pimp = None # import
        
        self.spin = None
        self.rsys = None

        self.s_pos = None
        self.s_neg = None
        self.sys_shortfall = None
        
        self.u = None
        self.v = None
        self.w = None
        
        self.flow = None
        self.theta = None
        
        # Parameters
        # SystemInput contains the model parameters
        self.inputs = inputs
        self.T = self.inputs.T
        
        self.initial_p = None
        self.initial_u = None
        self.initial_v = None
        self.initial_min_on = None
        self.initial_min_off = None
        
        # Timesteps t are in [1, 24]. The intial condition is defined at t=0
        self.timesteps = range(1, self.inputs.T+1)
        self.k = None
    
    
    def _set_objective(self) -> None:
        '''The objective function has four components: fixed cost, variable cost,
        start-up cost, and shortfall cost.
        '''
        
        # Use indexing of [0] to access the value of a dataframe
        opex_coeffs = {
            (unit_g, t): (self.inputs.fuelprice.loc[t + self.k*self.T, unit_g] * self.inputs.heat_rate.loc[unit_g])[0]
                + self.inputs.unit_econ.loc[unit_g, 'operation_cost']
            for t in self.timesteps for unit_g in self.inputs.thermal_units
            }
        
        fixed_coeffs = {
            (unit_g, t): self.inputs.max_cap[unit_g] * self.inputs.unit_econ.loc[unit_g, 'fixed_cost']
            for t in self.timesteps for unit_g in self.inputs.thermal_units
            }
        
        startup_coeffs = {
            (unit_g, t): self.inputs.max_cap[unit_g] * self.inputs.unit_econ.loc[unit_g, 'startup_cost']
            for t in self.timesteps for unit_g in self.inputs.thermal_units
            }
        
        rnw_coeffs = {
            (rnw_unit, t): self.inputs.fuelprice.loc[t + self.k*self.T, rnw_unit]
            for t in self.timesteps for rnw_unit in self.inputs.rnw_units
            }
        
        import_coeffs = {
            (import_node, t): self.inputs.fuelprice.loc[t + self.k*self.T, import_node]
            for t in self.timesteps for import_node in self.inputs.nodes_import
            }
        
        # Define costs
        operation_expr = self.p.prod(opex_coeffs)
        fixed_expr = self.u.prod(fixed_coeffs)
        startup_expr = self.v.prod(startup_coeffs)
        rnw_expr = self.prnw.prod(rnw_coeffs)
        import_expr = self.pimp.prod(import_coeffs)
        
        # The cost of shortfall is the slack variable (s_pos) needed to meet demand
        shortfall_expr = (
            self.inputs.fuelprice.loc[1, 'shortfall'] * (gp.quicksum(self.s_pos))
            )
        
        self.model.setObjective(
            (
                operation_expr + fixed_expr + startup_expr
                    + rnw_expr 
                    + import_expr
                    + shortfall_expr
                ),
            sense = GRB.MINIMIZE)
        
    
    def _c_link_p(self) -> None:
        # Link p, pbar, and spin together
        self.model.addConstrs(
            (
                self.pbar[unit_g, t] == self.p[unit_g, t] + self.spin[unit_g, t]
                for unit_g in self.inputs.thermal_units for t in self.timesteps
                ),
            name = 'link_p'
            )
    
    
    def _c_link_unit_status(self) -> None:
        # At t=1, the variables are linked to the initial_v
        self.model.addConstrs(
            (
                self.u[unit_g, 1] - self.initial_u[unit_g, self.T] # Last hour of the previous iteration
                <= self.initial_v[unit_g, self.T]
                for unit_g in self.inputs.thermal_units
                ),
            name = 'link_uv_init'
            )
        # When t in [2, 24]
        self.model.addConstrs(
            (
                self.u[unit_g, t] - self.u[unit_g, t-1] 
                <= self.v[unit_g, t] 
                for t in range(2, self.T+1) for unit_g in self.inputs.thermal_units
                ),
            name = 'link_uv'
            )
        
        
    def _c_min_up_init(self) -> None:
        for unit_g in self.inputs.thermal_units:
            # Find the min between the required uptime and the simulation horizon
            min_UT = min(self.initial_min_on[unit_g], self.T)
            self.model.addConstr(
                self.u.sum(unit_g, range(1, min_UT+1)) == min_UT,
                name = 'minUpInit'
                )
            
            
    def _c_min_down_init(self) -> None:
        for unit_g in self.inputs.thermal_units:
            # Find the min between the required downtime and the simulation horizon
            min_DT = min(self.initial_min_off[unit_g], self.T)
            self.model.addConstr(
                self.u.sum(unit_g, range(1, min_DT+1)) == 0,
                name = 'minDownInit'
                )
    
    def _c_min_up(self) -> None:
        for unit_g in self.inputs.thermal_units:
            TU_g = self.inputs.TU[unit_g]
            for t in range(TU_g, self.T+1):
                LHS =  gp.quicksum([self.v[unit_g, i] for i in range(t-TU_g+1, t+1)])
                self.model.addConstr(LHS <= self.u[unit_g, t], name='minUp' + f'_{unit_g}_{t}')
    
    
    def _c_min_down(self) -> None:
        for unit_g in self.inputs.thermal_units:
            TD_g = self.inputs.TD[unit_g]
            
            # When t = TD, the inequality contains the initial condition u[g, 0],
            # which we treat as a parameter
            t = TD_g
            LHS =  gp.quicksum([self.w[unit_g, i] for i in range(t-TD_g+1, t+1)])
            self.model.addConstr(
                LHS <= 1 - self.initial_u[unit_g, self.T], 
                name = 'minDown' + f'_{unit_g}_{t}')
            
            for t in range(TD_g+1, self.T+1):
                LHS =  gp.quicksum([self.w[unit_g, i] for i in range(t-TD_g+1, t+1)])
                self.model.addConstr(
                    LHS <= 1 - self.u[unit_g, t], 
                    name = 'minDown' + f'_{unit_g}_{t}')
    
    
    def _c_p_bound(self) -> None:
        self.model.addConstrs(
            (
                self.p[unit_g, t] <= self.pbar[unit_g, t]
                for t in self.timesteps for unit_g in self.inputs.thermal_units
                ),
            name = 'upper_p'
            )
    
    
    def _c_peak_up_bound(self) -> None:
        # Equation 23a applies when TU == 1
        # Enforced for t in [1, 23] because the constraints involved w at t+1
        self.model.addConstrs(
            (
                self.p[unit_g, t] + self.spin[unit_g, t]
                <= (self.inputs.max_cap[unit_g] - self.inputs.min_cap[unit_g]) * self.u[unit_g, t]
                    - (self.inputs.max_cap[unit_g] - self.inputs.SU[unit_g]) * self.v[unit_g, t]
                    - max(0, (self.inputs.SU[unit_g] - self.inputs.SD[unit_g])) * self.w[unit_g, t+1]
                for t in range(1, self.T) for unit_g in self.inputs.thermal_units if self.inputs.TU[unit_g] == 1
             ),
            name = 'peakUpBnd'
            )
    
    
    def _c_peak_down_bound(self) -> None:
        # Equation 23b applies when TU == 1
        self.model.addConstrs(
            (
                self.p[unit_g, t] + self.spin[unit_g, t]
                <= (self.inputs.max_cap[unit_g] - self.inputs.min_cap[unit_g]) * self.u[unit_g, t]
                    - (self.inputs.max_cap[unit_g] - self.inputs.SD[unit_g]) * self.w[unit_g, t+1]
                    - max(0, (self.inputs.SD[unit_g] - self.inputs.SU[unit_g])) * self.v[unit_g, t]
                for t in range(1, self.T) for unit_g in self.inputs.thermal_units if self.inputs.TU[unit_g] == 1
             ),
            name = 'peakDownBnd'
            )
    
    
    def _c_trajec_up_bound(self):
        # Equation 38
        for unit_g in self.inputs.thermal_units:
            # Calculate the time to full ramp-up
            time_RU = floor(
                (self.inputs.max_cap[unit_g] - self.inputs.SU[unit_g])/self.inputs.RU[unit_g])
            
            if self.inputs.TU[unit_g]-2 >= time_RU:
                # The min of (TU - 2, TRU) is the number of periods in the previous
                # simulation that must be traced back to address the changing
                # upper bound due to ramping.
                min_val = min(self.inputs.TU[unit_g]-2, time_RU)
                
                # Since the ineqalities involve t+1 index, we only iterate thru T-1
                for t in range(1, self.T):
                    # Define the summation term
                    sum_term = 0
                    for i in range(0, min_val+1):
                        # Decide if we need to refer back to the previous iteration
                        if t-i > 0:
                            sum_term += (
                                (self.inputs.max_cap[unit_g] - self.inputs.SU[unit_g] - i*self.inputs.RU[unit_g]) 
                                    * self.v[unit_g, t-i]
                                )
                        else:
                            sum_term += (
                                (self.inputs.max_cap[unit_g] - self.inputs.SU[unit_g] - i*self.inputs.RU[unit_g]) 
                                    * self.initial_v[unit_g, self.T + t - i]
                                )
                    
                    self.model.addConstr(
                        (
                            self.pbar[unit_g, t] + self.inputs.min_cap[unit_g] * self.u[unit_g, t]
                            <= self.inputs.max_cap[unit_g] * self.u[unit_g, t]
                                - (self.inputs.max_cap[unit_g] - self.inputs.SD[unit_g]) * self.w[unit_g, t+1]
                                - sum_term
                                ),
                        name = 'trajecUpBnd' + f'_{unit_g}_{t}'
                        )
        

            # When UT-2 < time_RU, the above inequalities do not cover
            # the entire start-up and ramping trajectory. Hence, we can
            # cover an additional time period with additional inequalities
            # up to the last hour of T.
            if self.inputs.TU[unit_g]-2 < time_RU:
                
                # Note TU_g - 1, which is different from the above
                min_val = min(self.inputs.TU[unit_g]-1, time_RU)
                
                for t in self.timesteps:
                    # Define the summation term
                    sum_term = 0
                    for i in range(0, min_val+1):
                        # Decide if we need to refer back to the previous iteration
                        if t-i > 0:
                            sum_term += (
                                (self.inputs.max_cap[unit_g] - self.inputs.SU[unit_g] - i*self.inputs.RU[unit_g]) 
                                    * self.v[unit_g, t-i]
                                )
                        else:
                            sum_term += (
                                (self.inputs.max_cap[unit_g] - self.inputs.SU[unit_g] - i*self.inputs.RU[unit_g]) 
                                    * self.initial_v[unit_g, self.T + t - i]
                                )
                
                self.model.addConstr(
                    (
                        self.pbar[unit_g, t] + self.inputs.min_cap[unit_g] * self.u[unit_g, t]
                        <= self.inputs.max_cap[unit_g] * self.u[unit_g, t]
                            - sum_term
                            ),
                    name = 'trajecUpBnd2' + f'_{unit_g}_{t}'
                    )
    

    def _c_trajec_down_bound(self):
        for unit_g in self.inputs.thermal_units:
            
            time_RU = floor(
                (self.inputs.max_cap[unit_g] - self.inputs.SU[unit_g]) / self.inputs.RU[unit_g])
            
            time_RD = floor(
                (self.inputs.max_cap[unit_g] - self.inputs.SU[unit_g]) / self.inputs.RD[unit_g])
            
            for t in self.timesteps:
                KSD_t = min(
                    time_RD, self.inputs.TU[unit_g]-1, self.T-t-1)
                
                # Omit adding inequalities if KSD < 0 because
                # c_trajec_up_bound dominates.
                if KSD_t <= 0:
                    continue
                
                # KSD_t must be positive, but we have already checked above
                KSU_t = min( time_RU, self.inputs.TU[unit_g] - 2 - KSD_t, t-1 )
                
                # First summation term
                sum_1 = 0
                for i in range(KSD_t+1):    
                    sum_1 += (
                        (
                            self.inputs.max_cap[unit_g] - self.inputs.SD[unit_g]
                            - i*self.inputs.RD[unit_g]
                            ) * self.w[unit_g, t+1+i]
                        )
                
                # Second summation term
                sum_2 = 0
                for i in range(KSU_t+1):
                    sum_2 += (
                        (self.inputs.max_cap[unit_g] - self.inputs.SU[unit_g] - i*self.inputs.RU[unit_g])*self.v[unit_g, t-i]
                        )
                
                self.model.addConstr(
                    (
                        self.p[unit_g, t] + self.inputs.min_cap[unit_g] * self.u[unit_g, t]
                        <= (
                            self.inputs.max_cap[unit_g] - self.inputs.min_cap[unit_g]) * self.u[unit_g, t]
                            - sum_1 - sum_2
                        ),
                    name = 'trajecDownBnd'
                    )


    def _c_ramp_up(self):
        # Ramp up when t=1 is dependent on the initial condition at t=0
        t = 1
        self.model.addConstrs(
            (
                self.pbar[unit_g, t] - self.initial_p[unit_g, self.T] 
                <= (self.inputs.SU[unit_g] - self.inputs.min_cap[unit_g] - self.inputs.RU[unit_g]) * self.v[unit_g, t]
                    + self.inputs.RU[unit_g] * self.u[unit_g, t]
                for unit_g in self.inputs.thermal_units
                ),
            name = 'rampUpInit'
            )
        
        self.model.addConstrs(
            (
                self.pbar[unit_g, t] - self.p[unit_g, t-1] 
                <= (self.inputs.SU[unit_g] - self.inputs.min_cap[unit_g] - self.inputs.RU[unit_g]) * self.v[unit_g, t]
                    + self.inputs.RU[unit_g] * self.u[unit_g, t]
                for t in range(2, self.T+1) for unit_g in self.inputs.thermal_units
                ),
            name = 'rampUp'
            )


    def _c_ramp_down(self):
        # Ramping when t=1 is dependent on the initial condition at t=0
        t = 1
        self.model.addConstrs(
            (
                self.initial_p[unit_g, self.T+t-1] - self.p[unit_g, t]
                <= (self.inputs.SD[unit_g] - self.inputs.min_cap[unit_g] - self.inputs.RD[unit_g]) * self.w[unit_g, t]
                    + self.inputs.RD[unit_g] * self.initial_u[unit_g, self.T]
                for unit_g in self.inputs.thermal_units
                ),
            name = 'rampDownInit'
            )
        
        # Ramping at other TIMESTEPS
        self.model.addConstrs(
            (
                self.p[unit_g, t-1] - self.p[unit_g, t]
                <= (self.inputs.SD[unit_g] - self.inputs.min_cap[unit_g] - self.inputs.RD[unit_g]) * self.w[unit_g, t]
                    + self.inputs.RD[unit_g] * self.u[unit_g, t-1]
                for t in range(2, self.T+1) for unit_g in self.inputs.thermal_units
                ),
            name = 'rampDown'
            )


    def _c_flow_bound(self):
        self.model.addConstrs(
            (
                self.flow[a, b, t] <= self.inputs.linecap[(a, b)]
                for (a, b) in self.inputs.arcs for t in self.timesteps
                ),
            name = 'maxFlow'
            )
        self.model.addConstrs(
            (
                self.flow[a, b, t] >= -1 * self.inputs.linecap[(a, b)]
                for (a, b) in self.inputs.arcs for t in self.timesteps
                ),
            name = 'minFlow'
            )


    def _c_angle_dff(self):
        # Note the indexing of the susceptance dataframe is incremented
        # along with the simulation step k
        self.model.addConstrs(
            (
                self.flow[a, b, t] == self.inputs.suscept.loc[t + self.T*self.k, (a, b)] 
                    * (self.theta[a, t] - self.theta[b, t])
                for (a, b) in self.inputs.arcs for t in self.timesteps
            ),
            name = 'angleDiffForward'
            )

    def _c_ref_node(self):
        self.model.addConstrs(
            (self.theta[self.inputs.max_node, t] == 0 for t in self.timesteps), 
            name='refNode'
            )


    def _c_flow_balance(self):
        # TODO: FIX IMPLEMENTATION
        # this allows flow_ab + flow_ba = 0 with non-zero flows
        # In reality, if the demand is zero, then there should be no flow
        # Must link flow to generation...
        for t in self.timesteps:
            for node in self.inputs.nodes:
                # If n is a thermal unit, then it can generate energy
                if node in self.inputs.thermal_units:
                    thermal_gen = self.p[node, t] + self.inputs.min_cap[node] * self.u[node, t]
                else: 
                    thermal_gen = 0
                
                # If n has renewables, then it can generate energy
                if node in self.inputs.rnw_units:
                    re_gen = self.prnw[node, t]
                else:
                    re_gen = 0
                    
                # If n is an import node, then it can generate energy
                if node in self.inputs.nodes_import:
                    imp_gen = self.pimp[node, t]
                else:
                    imp_gen = 0
                    
                # Get the demand of node n at time t
                if node in self.inputs.nodes_w_demand:
                    demand_n_t = self.inputs.demand.loc[t + self.T*self.k, node]
                    shortfall = self.s_pos[node, t] - self.s_neg[node, t]
                else:
                    demand_n_t = 0
                    shortfall = 0
                    
                # Flow into a node is positive, while flow out is negative
                arc_flow = 0
                for (x, y) in self.inputs.arcs: 
                    if x == node:
                        arc_flow -= self.flow[x, y, t]
                    elif y == node:
                        arc_flow += self.flow[x, y, t]
                
                # Given the above terms, we can specify the energy balance
                self.model.addConstr(
                    thermal_gen + re_gen + imp_gen + arc_flow + shortfall
                    == demand_n_t
                    )


    def _c_reserve_req(self):
        # Modified equation 67 but exclude the system-wide shortfall
        self.model.addConstrs(
            (
                gp.quicksum(self.pbar[unit_g, t] for unit_g in self.inputs.thermal_units)
                    + self.rsys[t]
                >= gp.quicksum(
                    self.inputs.demand.loc[t + self.T*self.k, n] for n in self.inputs.nodes_w_demand)
                        + self.inputs.spin_req[t + self.T*self.k]
                for t in self.timesteps
                ),
            name = 'reserveReq'
            )
    
    
    def _c_renewables_bound(self):
        self.model.addConstrs(
            (
                self.prnw[unit_w, t] <= self.inputs.rnw_cap.loc[t + self.T*self.k, unit_w]
                for t in self.timesteps for unit_w in self.inputs.rnw_units
                ),
            name = 'renewLimit'
            )
        
    def _c_import_bound(self):
        self.model.addConstrs(
            (
                self.pimp[import_node, t] <= self.inputs.p_import.loc[t + self.T*self.k, import_node]
                for t in self.timesteps for import_node in self.inputs.nodes_import
                ),
            name = 'importLimit'
            )
    

    def build(
            self,
            k: int,
            init_conds: dict[str, dict],
            ) -> gp.Model:

        self.k = k
        
        self.initial_p = init_conds['initial_p']
        self.initial_u = init_conds['initial_u']
        self.initial_v = init_conds['initial_v']
        self.initial_min_on = init_conds['initial_min_on']
        self.initial_min_off = init_conds['initial_min_off']
        
        self.model = gp.Model('UCED_Simulation')
        
        #---------------- Section: Variables
        # Relative dispatch of thermal units. Unit: MW
        self.p = self.model.addVars(
            self.inputs.thermal_units, self.timesteps, 
            vtype = GRB.CONTINUOUS, lb = 0, name = 'p')
        
        # The maximum power available above minimum capacity. Unit: MW
        # Formula: pbar = p + spin
        self.pbar = self.model.addVars(
            self.inputs.thermal_units, self.timesteps, 
            vtype = GRB.CONTINUOUS, lb=0, name = 'pbar')

        # The dispatch from renewables is in absolute term. Unit: MW
        self.prnw = self.model.addVars(
            self.inputs.rnw_units, self.timesteps, 
            vtype = GRB.CONTINUOUS, lb = 0, name = 'prnw')
        
        # The import from neighboring system in absolute term. Unit: MW
        self.pimp = self.model.addVars(
            self.inputs.nodes_import, self.timesteps, 
            vtype = GRB.CONTINUOUS, lb = 0, name = 'pimp')
        
        # Spinning reserve. Unit: MW
        self.spin = self.model.addVars(
            self.inputs.thermal_units, self.timesteps, 
            vtype = GRB.CONTINUOUS, lb = 0, name = 'spin')
        
        # Reserve of the overall system. Unit: MW
        self.rsys = self.model.addVars(
            self.timesteps, vtype = GRB.CONTINUOUS, lb = 0, name = 'rsys')
        
        # Positive/Negative load mismatch. Unit: MW
        self.s_pos = self.model.addVars(
            self.inputs.nodes, self.timesteps, 
            vtype = GRB.CONTINUOUS, lb = 0, name = 's_pos')
        
        self.s_neg = self.model.addVars(
            self.inputs.nodes, self.timesteps, 
            vtype = GRB.CONTINUOUS, lb = 0, name = 's_neg')
        
        # System-wide shortfall. Unit: MW. (Might not need this variable)
        # self.sys_shortfall = self.model.addVars(
        # timesteps, vtype = GRB.CONTINUOUS, lb = 0, name = 'load_under')
        
        # Unit status
        self.u = self.model.addVars(
            self.inputs.thermal_units, self.timesteps, 
            vtype = GRB.BINARY, name = 'status')
        
        # Switch-on
        self.v = self.model.addVars(
            self.inputs.thermal_units, self.timesteps, 
            vtype=GRB.BINARY, name = 'on')
        
        # Switch-off
        self.w = self.model.addVars(
            self.inputs.thermal_units, self.timesteps, 
            vtype = GRB.BINARY, name = 'shut')
        
        # The flow variable f(a,b,t) represents the flow in the
        # line segment (a,b) at hour t in MW/hr). If the flow is positive, 
        # then energy flows from a to b. 
        # We set the bounds based on the largest transmission line.
        self.flow = self.model.addVars(
            self.inputs.arcs, self.timesteps,
            lb = -1 * self.inputs.max_linecap,
            ub = self.inputs.max_linecap,
            vtype = GRB.CONTINUOUS,
            name = 'flow'
            )
        
        # Volt angle. Unit: radians
        # self.theta = self.model.addVars(
        # nodes, timesteps, vtype=GRB.CONTINUOUS, lb=-pi, ub=pi, name='volt_angle')
        self.theta = self.model.addVars(
            self.inputs.nodes, self.timesteps,
            vtype = GRB.CONTINUOUS, lb = -5e10, name = 'volt_angle')
        
        self.model.update()
        
        
        #---------------- Section: Objective function
        self._set_objective()
        
        #---------------- Section: Constraints
        self._c_link_p()
        self._c_link_unit_status()
        
        self._c_p_bound()
        
        self._c_reserve_req()
        self._c_renewables_bound()
        
        self._c_flow_bound()
        self._c_ref_node()
        self._c_angle_dff()
        self._c_flow_balance()
        
        self._c_min_up_init()
        self._c_min_down_init()
        self._c_min_up()
        self._c_min_down()
        
        self._c_peak_up_bound()
        self._c_peak_down_bound()
        
        self._c_trajec_up_bound()
        self._c_trajec_down_bound()
        
        self._c_ramp_up()
        self._c_ramp_down()
        
        return self.model
        