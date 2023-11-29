import math
import os

from gurobipy import GRB
import gurobipy as gp
import networkx as nx
import pandas as pd

from pownet.config import (
    is_warmstart, 
    get_line_safety_factor, 
    get_line_loss_factor,
    get_shortfall_penalty,
    get_spin_reserve_penalty
    )
from pownet.core.input import SystemInput
from pownet.folder_sys import get_output_dir



class ModelBuilder():
    ''' Build the model by adding unit commitment constraints.
    '''
    def __init__(
            self,
            inputs: SystemInput,
            reverse_flow: bool = False
            ) -> None:

        self.model = None
        self.model_name = inputs.model_name
        
        # We allow two formulations at the moment
        if inputs.formulation not in ['voltage_angle', 'kirchhoff']:
            raise ValueError(
                f'Formulation is either "voltage_angle" or "kirchhoff", but given {inputs.formulation}.')
        else:
            self.formulation = inputs.formulation
        
        # reverse_flow is not implemented yet
        self.reverse_flow = reverse_flow
        if reverse_flow:
            raise NotImplementedError('Reverse flow is not implemented.')
        
        # Variables. See _add_variables for the descriptions.
        self.dispatch = None
        self.p = None
        self.pbar = None
        
        self.prnw = None # renewables
        self.pimp = None # import
        
        self.spin = None # unit-specific spinning reserve
        self.sys_spin = None # system-wide spinning reserve

        self.s_pos = None
        self.s_neg = None
        self.sys_shortfall = None # Not yet implemented
        
        self.u = None
        self.v = None
        self.w = None
        
        self.flow = None
        self.theta = None
        
        # Parameters
        self.inputs = inputs
        self.T = self.inputs.T
        
        self.initial_p = None
        self.initial_u = None
        self.initial_v = None
        self.initial_w = None
        self.initial_min_on = None
        self.initial_min_off = None
        
        # The indexing of timesteps begin at 1. If timestep is zero, then it is
        # last timestep of the previous simulation. This is important for
        # defining initial conditions.
        self.timesteps = range(1, self.inputs.T+1)
        self.k = None
    
    
    def _set_objective(self) -> None:
        '''The objective function has four components: fixed cost, variable cost,
        start-up cost, and shortfall cost.
        '''
        
        # Use indexing of [0] to access the value of a dataframe
        opex_coeffs = {
            (unit_g, t): (self.inputs.fuelprice.loc[t + self.k*self.T, unit_g] * self.inputs.heat_rate.loc[unit_g]).iloc[0]
                + self.inputs.unit_econ.loc[unit_g, 'operation_cost']
            for t in self.timesteps for unit_g in self.inputs.thermal_units
            }
        
        fixed_coeffs = {
            (unit_g, t): self.inputs.max_cap[unit_g][t] * self.inputs.unit_econ.loc[unit_g, 'fixed_cost']
            for t in self.timesteps for unit_g in self.inputs.thermal_units
            }
        
        startup_coeffs = {
            (unit_g, t): self.inputs.max_cap[unit_g][t] * self.inputs.unit_econ.loc[unit_g, 'startup_cost']
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
        operation_expr = self.dispatch.prod(opex_coeffs)
        fixed_expr = self.u.prod(fixed_coeffs)
        startup_expr = self.v.prod(startup_coeffs)
        rnw_expr = self.prnw.prod(rnw_coeffs)
        import_expr = self.pimp.prod(import_coeffs)
        
        # The cost of shortfall is the slack variable (s_pos) needed to meet demand
        shortfall_expr = (
            get_shortfall_penalty() * (gp.quicksum(self.s_pos) + gp.quicksum(self.s_neg))
            )
        
        # Penalize the system if it cannot meet the spinning reserve requirement
        spin_reserve_penalty_expr = get_spin_reserve_penalty() * gp.quicksum(self.sys_spin)
        
        self.model.setObjective(
            (
                operation_expr + fixed_expr + startup_expr
                    + rnw_expr 
                    + import_expr
                    + shortfall_expr
                    + spin_reserve_penalty_expr
                ),
            sense = GRB.MINIMIZE)
        
    
    def _c_link_uvw(self) -> None:
        '''Equation 2 of Kneuven et al (2019).
        Define the relationship among unit status, start-up, and shutdown
        '''
        # At t=1, the variables are linked to the initial_u
        self.model.addConstrs(
            (
                self.u[unit_g, 1] - self.initial_u[unit_g, self.T] # Last hour of the previous iteration
                    == self.v[unit_g, 1]  - self.w[unit_g, 1]
                for unit_g in self.inputs.thermal_units
                ),
            name = 'link_uvw_init'
            )
        # When t in [2, 24]
        self.model.addConstrs(
            (
                self.u[unit_g, t] - self.u[unit_g, t-1] 
                    == self.v[unit_g, t]  - self.w[unit_g, t] 
                for unit_g in self.inputs.thermal_units for t in range(2, self.T+1)
                ),
            name = 'link_uvw'
            )
        
    
    def _c_link_dispatch(self) -> None:
        '''Equation 12 of Kneuven et al (2019). The dispatched power is 
        a function of p and pbar.
        '''
        self.model.addConstrs(
            (
                self.dispatch[unit_g, t] == self.p[unit_g, t]
                    + self.inputs.min_cap[unit_g] * self.u[unit_g, t]
                for unit_g in self.inputs.thermal_units
                for t in self.timesteps
                ),
            name = 'link_dispatch'
            )
    
    
    def _c_link_p(self) -> None:
        ''' Equation 14 of Kneuven et al (2019).
        Establish the relationship among p, pbar, and spin together
        '''
        self.model.addConstrs(
            (
                self.pbar[unit_g, t] == self.p[unit_g, t] + self.spin[unit_g, t]
                for unit_g in self.inputs.thermal_units for t in self.timesteps
                ),
            name = 'link_p'
            )
    
    
    def _c_link_pu(self) -> None:
        '''Equation 18 of Kneuven et al (2019). 
        Establish the relationship among p, pbar, and status
        '''
        self.model.addConstrs(
            (
                self.inputs.min_cap[unit_g]*self.u[unit_g, t] <= self.dispatch[unit_g, t]
                for unit_g in self.inputs.thermal_units
                for t in self.timesteps
                ),
            name = 'p_lower_bound'
            )
        self.model.addConstrs(
            (
                self.pbar[unit_g, t] <= self.inputs.max_cap[unit_g][t]*self.u[unit_g, t]
                for unit_g in self.inputs.thermal_units
                for t in self.timesteps
                ),
            name = 'p_upper_bound'
            )


    def _c_min_down_init(self) -> None:
        '''Equation 3b of Kneuven et al (2019).
        Minimum downtime at the first time step
        '''
        for unit_g in self.inputs.thermal_units:
            # Find the min between the required downtime and the simulation horizon
            min_DT = min(self.initial_min_off[unit_g], self.T)
            self.model.addConstr(
                self.u.sum(unit_g, range(1, min_DT+1)) == 0,
                name = f'minDownInit[{unit_g}]'
                )


    def _c_min_up_init(self) -> None:
        '''Equation 3a of Kneuven et al (2019).
        Minimum uptime at the initial timestep
        '''
        for unit_g in self.inputs.thermal_units:
            # Find the min between the required uptime and the simulation horizon
            min_UT = min(self.initial_min_on[unit_g], self.T)
            self.model.addConstr(
                self.u.sum(unit_g, range(1, min_UT+1)) == min_UT,
                name = f'minUpInit[{unit_g}]'
                )
            
        
    def _c_min_down(self) -> None:
        '''Equation 5 of Kneuven et al (2019). Minimum downtime.
        This equation is stated to base on Malkin (2003) and
        Rajan and Takriti (2005).
        '''
        for unit_g in self.inputs.thermal_units:
            TD_g = self.inputs.TD[unit_g]
            for t in range(TD_g, self.T+1):
                LHS =  gp.quicksum([self.w[unit_g, i] for i in range(t-TD_g+1, t+1)])
                self.model.addConstr(
                    LHS <= 1 - self.u[unit_g, t], 
                    name = 'minDown' + f'[{unit_g},{t}]')


    def _c_min_up(self) -> None:
        '''Equation 4 of Kneuven et al (2019). Minimum uptime.
        This equation is stated to base on Malkin (2003) and
        Rajan and Takriti (2005).
        '''
        for unit_g in self.inputs.thermal_units:
            TU_g = self.inputs.TU[unit_g]
            for t in range(TU_g, self.T+1):
                LHS =  gp.quicksum([self.v[unit_g, i] for i in range(t-TU_g+1, t+1)])
                self.model.addConstr(
                    LHS <= self.u[unit_g, t],
                    name='minUp' + f'[{unit_g},{t}]')
    
    
    def _c_peak_down_bound(self) -> None:
        ''' Equation 23b of Kneuven et al (2019).
        This is the generation limit during the shutdown of
        a peaking unit. A peaking unit is a generator that is only required
        to be on for one hour or TU = 1.
        '''
        # Enforced for t in [1, 23] because the constraints involved w at t+1
        self.model.addConstrs(
            (
                self.p[unit_g, t] + self.spin[unit_g, t]
                <= (self.inputs.max_cap[unit_g][t] - self.inputs.min_cap[unit_g]) * self.u[unit_g, t]
                    - (self.inputs.max_cap[unit_g][t] - self.inputs.SD[unit_g]) * self.w[unit_g, t+1]
                    - max(0, (self.inputs.SD[unit_g] - self.inputs.SU[unit_g])) * self.v[unit_g, t]
                for unit_g in self.inputs.thermal_units if self.inputs.TU[unit_g] == 1
                for t in range(1, self.T)
             ),
            name = 'peakDownBnd'
            )

    
    def _c_peak_up_bound(self) -> None:
        '''Equation 23a of Kneuven et al (2019).
        This is the generation limit during the start-up of
        a peaking unit. A peaking unit is a generator that is only required
        to be on for one hour or TU = 1.
        '''
        # Enforced for t in [1, 23] because the constraints involved w at t+1
        self.model.addConstrs(
            (
                self.p[unit_g, t] + self.spin[unit_g, t]
                <= (self.inputs.max_cap[unit_g][t] - self.inputs.min_cap[unit_g]) * self.u[unit_g, t]
                    - (self.inputs.max_cap[unit_g][t] - self.inputs.SU[unit_g]) * self.v[unit_g, t]
                    - max(0, (self.inputs.SU[unit_g] - self.inputs.SD[unit_g])) * self.w[unit_g, t+1]
                for unit_g in self.inputs.thermal_units if self.inputs.TU[unit_g] == 1
                for t in range(1, self.T)
             ),
            name = 'peakUpBnd'
            )
        

    def _c_trajec_down_bound(self):
        '''Equation 41 of Kneuven et al (2019). This is the generation limit
        during a unit shutdown. Note that this has a similar purpose as Equation 23,
        which only addresses peaking units.
        '''
        for unit_g in self.inputs.thermal_units:
            for t in self.timesteps:
                time_RD = math.floor(
                    (self.inputs.max_cap[unit_g][t] - self.inputs.SU[unit_g]) / self.inputs.RD[unit_g])
                
                time_RU = math.floor(
                    (self.inputs.max_cap[unit_g][t] - self.inputs.SU[unit_g]) / self.inputs.RU[unit_g])
                
                KSD_t = min(
                    time_RD, self.inputs.TU[unit_g]-1, self.T-t-1)
                
                # Omit adding inequalities if KSD <= 0 because
                # c_trajec_up_bound dominates.
                if KSD_t <= 0:
                    continue
                
                # KSD_t must be positive, which we have already checked
                # Note that we use KSD_t instead of KSU_t on the RHS
                # as described in Kneuven et al (2019)
                KSU_t = min(time_RU, self.inputs.TU[unit_g] - 2 - KSD_t, t-1)
                
                # First summation term
                sum_1 = 0
                for i in range(KSD_t+1):    
                    sum_1 += (
                        (
                            self.inputs.max_cap[unit_g][t] - self.inputs.SD[unit_g]
                            - i*self.inputs.RD[unit_g]
                            ) * self.w[unit_g, t+1+i]
                        )
                
                # Second summation term
                sum_2 = 0
                for i in range(KSU_t+1):
                    sum_2 += (
                        (self.inputs.max_cap[unit_g][t] - self.inputs.SU[unit_g] - i*self.inputs.RU[unit_g])*self.v[unit_g, t-i]
                        )
                
                self.model.addConstr(
                    (
                        self.p[unit_g, t]
                        <= (
                            self.inputs.max_cap[unit_g][t] - self.inputs.min_cap[unit_g]) * self.u[unit_g, t]
                            - sum_1 - sum_2
                        ),
                    name = 'trajecDownBnd' + f'[{unit_g},{t}]'
                    )


    def _c_trajec_up_bound(self):
        '''Equation 38 or 40 of Kneuven et al (2019). This is the generation unit
        during unit start-up. This complements Equation 23a, which is the generation limit
        during start-up for a peaking unit.
        
        '''
        # Since the ineqalities involve t+1 index, we only iterate thru T-1
        for t in range(1, self.T):
            for unit_g in self.inputs.thermal_units:
                # Calculate the time to full ramp-up
                time_RU = math.floor(
                    (self.inputs.max_cap[unit_g][t] - self.inputs.SU[unit_g])/self.inputs.RU[unit_g])
                
                # Equation 38 - substitute in pbar
                if self.inputs.TU[unit_g]-2 >= time_RU:
                    # The min of (TU - 2, TRU) is the number of periods in the previous
                    # simulation that must be traced back to address the changing
                    # upper bound due to ramping.
                    min_val = min(self.inputs.TU[unit_g]-2, time_RU)
                    # Define the summation term
                    sum_term = 0
                    for i in range(0, min_val+1):
                        # Decide if we need to refer back to the previous iteration
                        if t-i > 0:
                            sum_term += (
                                (self.inputs.max_cap[unit_g][t] - self.inputs.SU[unit_g] - i*self.inputs.RU[unit_g]) 
                                    * self.v[unit_g, t-i]
                                )
                        else:
                            sum_term += (
                                (self.inputs.max_cap[unit_g][t] - self.inputs.SU[unit_g] - i*self.inputs.RU[unit_g]) 
                                    * self.initial_v[unit_g, self.T + t - i]
                                )
                    self.model.addConstr(
                        (
                            self.pbar[unit_g, t] + self.inputs.min_cap[unit_g] * self.u[unit_g, t]
                            <= self.inputs.max_cap[unit_g][t] * self.u[unit_g, t]
                                - (self.inputs.max_cap[unit_g][t] - self.inputs.SD[unit_g]) * self.w[unit_g, t+1]
                                - sum_term
                                ),
                        name = 'trajecUpBnd' + f'[{unit_g},{t}]'
                        )
                # Equation 40 - substitute in pbar
                # When TU - 2 < time_RU, the above inequalities do not cover
                # the entire start-up and ramping trajectory. Hence, we can
                # cover an additional time period with additional inequalities
                # up to the last hour of T.
                # In other words, when self.inputs.TU[unit_g]-2 < time_RU.
                else:
                    # Note TU_g - 1, which is different from the above
                    min_val = min(self.inputs.TU[unit_g]-1, time_RU)
                    
                    for tt in self.timesteps:
                        # Define the summation term
                        sum_term = 0
                        for i in range(0, min_val+1):
                            # Decide if we need to refer back to the previous iteration
                            if tt-i > 0:
                                sum_term += (
                                    (self.inputs.max_cap[unit_g][tt] - self.inputs.SU[unit_g] - i*self.inputs.RU[unit_g]) 
                                        * self.v[unit_g, tt-i]
                                    )
                            else:
                                sum_term += (
                                    (self.inputs.max_cap[unit_g][tt] - self.inputs.SU[unit_g] - i*self.inputs.RU[unit_g]) 
                                        * self.initial_v[unit_g, self.T + tt - i]
                                    )
                    self.model.addConstr(
                        (
                            self.pbar[unit_g, tt] + self.inputs.min_cap[unit_g] * self.u[unit_g, tt]
                            <= self.inputs.max_cap[unit_g][tt] * self.u[unit_g, tt]
                                - sum_term
                                ),
                        name = 'trajecUpBnd' + f'[{unit_g},{tt}]'
                        )


    # def _c_trajec_up_bound_original(self):
    #     '''Equation 38 or 40 of Kneuven et al (2019). This is the generation unit
    #     during unit start-up. This complements Equation 23a, which is the generation limit
    #     during start-up for a peaking unit.
        
    #     '''
    #     for unit_g in self.inputs.thermal_units:
    #         # Calculate the time to full ramp-up
    #         time_RU = math.floor(
    #             (self.inputs.full_max_cap[unit_g] - self.inputs.SU[unit_g])/self.inputs.RU[unit_g])
            
    #         # Equation 38 - substitute in pbar
    #         if self.inputs.TU[unit_g]-2 >= time_RU:
    #             # The min of (TU - 2, TRU) is the number of periods in the previous
    #             # simulation that must be traced back to address the changing
    #             # upper bound due to ramping.
    #             min_val = min(self.inputs.TU[unit_g]-2, time_RU)
                
    #             # Since the ineqalities involve t+1 index, we only iterate thru T-1
    #             for t in range(1, self.T):
    #                 # Define the summation term
    #                 sum_term = 0
    #                 for i in range(0, min_val+1):
    #                     # Decide if we need to refer back to the previous iteration
    #                     if t-i > 0:
    #                         sum_term += (
    #                             (self.inputs.max_cap[unit_g][t] - self.inputs.SU[unit_g] - i*self.inputs.RU[unit_g]) 
    #                                 * self.v[unit_g, t-i]
    #                             )
    #                     else:
    #                         sum_term += (
    #                             (self.inputs.max_cap[unit_g][t] - self.inputs.SU[unit_g] - i*self.inputs.RU[unit_g]) 
    #                                 * self.initial_v[unit_g, self.T + t - i]
    #                             )
    #                 self.model.addConstr(
    #                     (
    #                         self.pbar[unit_g, t] + self.inputs.min_cap[unit_g] * self.u[unit_g, t]
    #                         <= self.inputs.max_cap[unit_g][t] * self.u[unit_g, t]
    #                             - (self.inputs.max_cap[unit_g][t] - self.inputs.SD[unit_g]) * self.w[unit_g, t+1]
    #                             - sum_term
    #                             ),
    #                     name = 'trajecUpBnd' + f'[{unit_g},{t}]'
    #                     )

    #         # Equation 40 - substitute in pbar
    #         # When TU - 2 < time_RU, the above inequalities do not cover
    #         # the entire start-up and ramping trajectory. Hence, we can
    #         # cover an additional time period with additional inequalities
    #         # up to the last hour of T.
    #         if self.inputs.TU[unit_g]-2 < time_RU:
                
    #             # Note TU_g - 1, which is different from the above
    #             min_val = min(self.inputs.TU[unit_g]-1, time_RU)
                
    #             for t in self.timesteps:
    #                 # Define the summation term
    #                 sum_term = 0
    #                 for i in range(0, min_val+1):
    #                     # Decide if we need to refer back to the previous iteration
    #                     if t-i > 0:
    #                         sum_term += (
    #                             (self.inputs.max_cap[unit_g][t] - self.inputs.SU[unit_g] - i*self.inputs.RU[unit_g]) 
    #                                 * self.v[unit_g, t-i]
    #                             )
    #                     else:
    #                         sum_term += (
    #                             (self.inputs.max_cap[unit_g][t] - self.inputs.SU[unit_g] - i*self.inputs.RU[unit_g]) 
    #                                 * self.initial_v[unit_g, self.T + t - i]
    #                             )
    #             self.model.addConstr(
    #                 (
    #                     self.pbar[unit_g, t] + self.inputs.min_cap[unit_g] * self.u[unit_g, t]
    #                     <= self.inputs.max_cap[unit_g][t] * self.u[unit_g, t]
    #                         - sum_term
    #                         ),
    #                 name = 'trajecUpBnd' + f'[{unit_g},{t}]'
    #                 )
    

    def _c_ramp_down(self):
        '''Equation 36 of Kneuven et al (2019). Ramp-down constraint.
        '''
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
                for unit_g in self.inputs.thermal_units
                for t in range(2, self.T+1)
                ),
            name = 'rampDown'
            )


    def _c_ramp_up(self):
        '''Equation 35 of Kneuven et al (2019). Ramp-up constraint.
        '''
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
        # Ramping at other TIMESTEPS
        self.model.addConstrs(
            (
                self.pbar[unit_g, t] - self.p[unit_g, t-1] 
                <= (self.inputs.SU[unit_g] - self.inputs.min_cap[unit_g] - self.inputs.RU[unit_g]) * self.v[unit_g, t]
                    + self.inputs.RU[unit_g] * self.u[unit_g, t]
                for unit_g in self.inputs.thermal_units
                for t in range(2, self.T+1)
                ),
            name = 'rampUp'
            )


    def _c_ref_node(self):
        '''Equation 64d of Kneuven et al (2019).
        Set the voltage angle at a reference node to zero. We generally select
        a node with the largest demand.
        '''
        self.model.addConstrs(
            (self.theta[self.inputs.max_node, t] == 0 for t in self.timesteps), 
            name='refNode'
            )
        

    def _c_angle_diff(self):
        '''Equation 64a of Kneuven et al (2019).
        The total flow in a line segment is driven by the difference in
        the voltage angles between a source and a sink.
        '''
        # Note the indexing of the susceptance dataframe is incremented
        # along with the simulation step k
        self.model.addConstrs(
            (
                self.flow[a, b, t] == self.inputs.suscept.loc[t + self.T*self.k, (a, b)] 
                    * (self.theta[a, t] - self.theta[b, t])
                for (a, b) in self.inputs.arcs for t in self.timesteps
            ),
            name = 'angleDiff'
            )


    def _c_kirchhoff_voltage(self):
        ''' Equation 23b in Horsch et al (2018). Although the paper states
        that it is mathematically equivalent to the voltage-angle formulation,
        both formulations will likely not produce the same solution.
        '''
        cycle_incidence = pd.DataFrame(
            0,
            index = pd.MultiIndex.from_tuples(self.inputs.arcs, names=["source", "sink"]),
            columns = self.inputs.cycle_map.keys()
            )
        
        # The flow is positive with respect to the edges specified by the user
        for cycle_id, cycle in self.inputs.cycle_map.items():
            # Kirchhoff formulation requires summing along the loop direction.
            # If an arc is in cycle_graph and the input file, then 1. Otherwise, -1.
            cycle_graph = nx.path_graph(cycle)
            cycle_arcs = list(cycle_graph.edges)
            # Append the last arc connecting the last node to the first node
            cycle_arcs.append(
                (cycle_arcs[-1][-1], cycle_arcs[0][0]))
            
            # We also need the reactance (susceptance) to calculate the factors in the cycle-incidence
            cycle_susceptance = pd.DataFrame() 
            for flow in cycle_arcs:
                if flow in self.inputs.arcs:
                    cycle_incidence.loc[flow, cycle_id] = 1
                    cycle_susceptance = pd.concat(
                        [cycle_susceptance, self.inputs.suscept[flow]],
                        axis = 1
                        )
                else:
                    cycle_incidence.loc[(flow[1], flow[0]), cycle_id] = -1
                    cycle_susceptance = pd.concat(
                        [cycle_susceptance, self.inputs.suscept[(flow[1], flow[0])]],
                        axis = 1
                        )

            self.model.addConstrs(
                (
                 gp.quicksum(
                     (cycle_incidence.loc[(a, b), cycle_id]
                         * 1/cycle_susceptance.loc[t + self.T*self.k, [(a, b)]]
                         * self.flow[a, b, t])[0]
                         for (a, b) in cycle_susceptance.columns
                         ) 
                     == 0
                    for t in self.timesteps
                ),
                name = f'kirchhoff_{cycle_id}'
                )
        
        
    def _c_flow_balance(self):
        '''Equation 65 of Kneuven et al (2019).
        We do not aggregate thermal units to a node. A thermal unit is its own node.
        '''
        # We will tax all generators and import nodes with line loss
        line_efficiency = 1 - get_line_loss_factor()
        for t in self.timesteps:
            for node in self.inputs.nodes:
                # If n is a thermal unit, then it can generate energy
                if node in self.inputs.thermal_units:
                    thermal_gen = self.dispatch[node, t] * line_efficiency
                else: 
                    thermal_gen = 0
                
                # If n has renewables, then it can generate energy
                if node in self.inputs.rnw_units:
                    re_gen = self.prnw[node, t] * line_efficiency
                else:
                    re_gen = 0
                    
                # If n is an import node, then it can generate energy
                if node in self.inputs.nodes_import:
                    imp_gen = self.pimp[node, t] * line_efficiency
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
                    (
                        thermal_gen + re_gen + imp_gen + arc_flow + shortfall
                        == demand_n_t),
                    name = 'flowBal' + f'[{node},{t}]'
                    )


    def _c_reserve_req(self):
        '''Equation 67 of Kneuven et al (2019). System-wide spinning reserve requirement.
        '''
        self.model.addConstrs(
            (
                gp.quicksum(self.pbar[unit_g, t] for unit_g in self.inputs.thermal_units)
                    + self.sys_spin[t]
                >= gp.quicksum(
                    self.inputs.demand.loc[t + self.T*self.k, n] for n in self.inputs.nodes_w_demand)
                        + self.inputs.spin_req[t + self.T*self.k]
                for t in self.timesteps
                ),
            name = 'reserveReq'
            )
    

    def _add_variables(self) -> None:
        '''The lower and upper bounds of variables are defined here instead
        of defining them as constraints.
        '''
        # Dispatched power from a generator. Unit: MW
        self.dispatch = self.model.addVars(
            self.inputs.thermal_units, self.timesteps, 
            vtype = GRB.CONTINUOUS,
            lb = 0,
            name = 'dispatch'
            )
        # Power generated above minimum. Unit: MW
        self.p = self.model.addVars(
            self.inputs.thermal_units, self.timesteps, 
            lb = 0,
            vtype = GRB.CONTINUOUS,
            name = 'p'
            )
        # The maximum power available above the minimum capacity. Unit: MW
        # Formula: pbar = p + spin
        self.pbar = self.model.addVars(
            self.inputs.thermal_units, self.timesteps, 
            lb=0,
            vtype = GRB.CONTINUOUS,
            name = 'pbar')

        # The dispatch from renewables is in absolute term. Unit: MW
        self.prnw = self.model.addVars(
            self.inputs.rnw_units, self.timesteps, 
            lb = 0,
            ub = {
                (rnw_unit, t): self.inputs.rnw_cap.loc[t + self.T*self.k, rnw_unit]
                for t in self.timesteps
                for rnw_unit in self.inputs.rnw_cap.columns
                },
            vtype = GRB.CONTINUOUS,
            name = 'prnw')
        
        # The import from neighboring system in absolute term. Unit: MW
        self.pimp = self.model.addVars(
            self.inputs.nodes_import, self.timesteps,
            lb = 0,
            ub = {
                (import_node, t): self.inputs.p_import.loc[t + self.T*self.k, import_node]
                for t in self.timesteps
                for import_node in self.inputs.p_import.columns
                },
            vtype = GRB.CONTINUOUS, 
            name = 'pimp')
        
        # Spinning reserve. Unit: MW
        self.spin = self.model.addVars(
            self.inputs.thermal_units, self.timesteps,
            lb = 0,
            vtype = GRB.CONTINUOUS,
            name = 'spin')
        
        # Spinning reserve of the overall system. Unit: MW
        self.sys_spin = self.model.addVars(
            self.timesteps,
            lb = 0,
            vtype = GRB.CONTINUOUS,
            name = 'sys_spin')
        
        # Positive mismatch. Unit: MW
        self.s_pos = self.model.addVars(
            self.inputs.nodes_w_demand, self.timesteps, 
            lb = 0, 
            vtype = GRB.CONTINUOUS,
            name = 's_pos')
        
        # Negative mismatch. Unit: MW
        # Need to clarify when we have negative mismatch.
        self.s_neg = self.model.addVars(
            self.inputs.nodes_w_demand, self.timesteps,
            lb = 0,
            vtype = GRB.CONTINUOUS,
            name = 's_neg')
        
        # Unit status. On = 1 and off = 0
        self.u = self.model.addVars(
            self.inputs.thermal_units, self.timesteps, 
            vtype = GRB.BINARY, name = 'status')
        
        # Switch-on
        self.v = self.model.addVars(
            self.inputs.thermal_units, self.timesteps, 
            vtype=GRB.BINARY, name = 'start')
        
        # Switch-off
        self.w = self.model.addVars(
            self.inputs.thermal_units, self.timesteps, 
            vtype = GRB.BINARY, name = 'shut')
        
        # The flow variable f(a,b,t) represents the flow in the
        # line segment (a,b) at hour t in MW/hr). If the flow is positive, 
        # then energy flows from a to b. 
        # We set the bounds based on the transmission limit
        line_safety_factor = get_line_safety_factor()
        if not self.reverse_flow:
            self.flow = self.model.addVars(
                self.inputs.arcs, self.timesteps,
                lb = {
                    (source, sink, t): -1*line_safety_factor*self.inputs.linecap.loc[t + self.T*self.k, (source, sink)]
                    for source, sink in self.inputs.arcs
                    for t in self.timesteps
                    },
                ub = {(source, sink, t): line_safety_factor*self.inputs.linecap.loc[t + self.T*self.k, (source, sink)]
                      for source, sink in self.inputs.arcs
                      for t in self.timesteps
                    },
                vtype = GRB.CONTINUOUS,
                name = 'flow'
                )
        else:
            # We only deal with positive flows in this case
            self.flow = self.model.addVars(
                self.inputs.arcs, self.timesteps,
                lb = 0,
                ub = {(source, sink, t): line_safety_factor*self.inputs.linecap.loc[t + self.T*self.k, (source, sink)]
                      for source, sink in self.inputs.arcs
                      for t in self.timesteps
                    },
                vtype = GRB.CONTINUOUS,
                name = 'flow'
                )

        # Volt angle. Unit: radians
        # Not sure if we should do between -pi and pi or between 0 and 2*pi
        if self.formulation == 'voltage_angle':
            self.theta = self.model.addVars(
                self.inputs.nodes, 
                self.timesteps,
                lb = 0,
                ub = 2*math.pi,
                vtype = GRB.CONTINUOUS,
                name = 'volt_angle')
        
        self.model.update()


    def _add_constraints(self) -> None:
        #---------------- Section: Constraints
        self._c_link_uvw()
        self._c_link_dispatch()
        self._c_link_p()
        self._c_link_pu()

        self._c_min_down_init()
        self._c_min_up_init()

        self._c_min_down()
        self._c_min_up()
        
        # We do not have shut-down rate or start-up rate for thermal units
        # self._c_peak_down_bound()
        # self._c_peak_up_bound()
        # self._c_trajec_down_bound()
        # self._c_trajec_up_bound()

        self._c_ramp_down()
        self._c_ramp_up()
        
        if self.formulation == 'voltage_angle':
            self._c_ref_node()
            self._c_angle_diff()
        elif self.formulation == 'kirchhoff':
            self._c_kirchhoff_voltage()
        
        self._c_flow_balance()

        self._c_reserve_req()
        
        self.model.update()

    def build(
            self,
            k: int,
            init_conds: dict[str, dict],
            ) -> gp.Model:

        self.k = k
        
        self.initial_p = init_conds['initial_p']
        self.initial_u = init_conds['initial_u']
        self.initial_v = init_conds['initial_v']
        self.initial_w = init_conds['initial_w']
        
        # These two variables are scalar. Defining the remaining time required
        # to be on or off.
        self.initial_min_on = init_conds['initial_min_on']
        self.initial_min_off = init_conds['initial_min_off']
        
        self.model = gp.Model(f'{self.model_name}_{k+1}')
        self._add_variables()
        self._set_objective()
        self._add_constraints()
        
        return self.model
    
    
    def update(self, k:int, init_conds: dict[str, dict]) -> None:
        ''' Update the model instead of creating a new one 
        so we can perform warm start
        '''
        # TODO: Consider updating the model instead of creating a new one
        # Update cost coeffs, constraints, RHS
        self.model = self.build(k, init_conds)
        
        # Use the solution from the previous solve
        if is_warmstart():
            previous_solution_file = os.path.join(
                get_output_dir(), f'{self.model_name}_{k-1}.sol'
                )
            self.model.read(previous_solution_file)
            # Delete the since we have loaded the solution
            os.remove(previous_solution_file)
        
        return self.model
        