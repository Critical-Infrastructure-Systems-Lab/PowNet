import gurobipy as gp
import pandas as pd
import numpy as np

from pownet.core.input import SystemInput
from pownet.processing.functions import get_nodehour, get_nodehour_flow, get_nodehour_sys


def increment_hour(df: pd.DataFrame, T: int, k: int):
    df = df.copy()
    # Increment the hour column according to the simulation period
    df['hour'] = df['hour'] + T*k
    return df
    

def get_init_min_on(
        df: pd.DataFrame, 
        T: int, 
        system_input: SystemInput
        ) -> dict[str, int]:
    
    init_min_on = {}
    
    for unit_g in system_input.thermal_units:
        df_unit = df[(df['node'] == unit_g) & (df['vartype'] == 'start')]\
            .set_index('hour').drop(['vartype', 'node'], axis=1)
            
        # Check if there are non-zero elements.
        if len(np.where(df_unit['value'])[0]) > 0:
            # np.argmax returns the index starting at zero, so we need to add 1
            time_last_off = np.max(np.where(df_unit['value'])) + 1
        else:
            # Taking the negative of T will ensure the calculation is negative
            # such that max(0, calculation) = 0
            time_last_off = -T
            
        # The calculated remaining shutdown duration can be negative, 
        # which should be converted to
        init_min_on[unit_g] = max(0, system_input.TU[unit_g] - (T - time_last_off))

    return init_min_on


def get_init_min_off(
        df: pd.DataFrame, T: int, system_input: SystemInput
        ) -> dict[str, int]:
    
    init_min_off = {}
    
    for unit_g in system_input.thermal_units:
        df_unit = df[(df['node'] == unit_g) & (df['vartype'] == 'shut')]\
            .set_index('hour').drop(['vartype', 'node'], axis=1)
            
        # Check if there are non-zero elements.
        if len(np.where(df_unit['value'])[0]) > 0:
            # np.argmax returns the index starting at zero, so we need to add 1
            time_last_on = np.max(np.where(df_unit['value'])) + 1
        else:
            # Taking the negative of T will ensure the calculation is negative
            # such that max(0, calculation) = 0
            time_last_on = -T
            
        # The calculated remaining shutdown duration can be negative, 
        # which should be converted to
        init_min_off[unit_g] = max(0, system_input.TD[unit_g] - (T - time_last_on))

    return init_min_off



class SystemRecord():
    def __init__(self, T: int) -> None:
        self.T: int = T
        # The model results are separated into three types based on
        # the formating of their index: var(node, t), var(node, node, t), var(t)
        self.var_node_t: pd.DataFrame = None
        self.var_flow: pd.DataFrame = None
        self.var_syswide: pd.DataFrame = None
        
        # These attributes are a list of values
        self.current_p = None
        self.current_u = None
        self.current_v = None
        self.current_w = None
        self.current_min_on = None
        self.current_min_off = None
    
    
    def keep(self, model: gp.Model, k: int, system_input: SystemInput) -> None:
        # Extract the variables from the model to process them
        all_vars = model.getVars()
        values = model.getAttr("X", all_vars)
        names = model.getAttr("VarName", all_vars)
        results = pd.DataFrame({'varname':names, 'value':values})
        
        # Create a col of variable types for filtering
        pat_vartype = r'(\w+)\['
        results[['vartype']] = results['varname'].str.extract(pat_vartype, expand=True)
        
        # Some variables are not in the (node, t) format. 
        # These are system-level variables
        col2exclude = ['flow', 'rsys']
        
        # Format the dataframe into vartype, node, hour, value columns
        cur_var_node_t = results[~results['vartype'].isin(col2exclude)]
        cur_var_node_t = get_nodehour(cur_var_node_t)
        
        cur_var_flow = results[results['vartype'] == 'flow']
        cur_var_flow = get_nodehour_flow(cur_var_flow)
        
        cur_var_syswide = results[results['vartype'] == 'rsys']
        cur_var_syswide = get_nodehour_sys(cur_var_syswide)
        
        # Save some variables as initial conditions for the next simulation period
        self.current_p = cur_var_node_t[cur_var_node_t['vartype'] == 'p']\
            .drop('vartype', axis=1).set_index(['node', 'hour']).to_dict()['value']
        
        self.current_u = cur_var_node_t[cur_var_node_t['vartype'] == 'status']\
            .drop('vartype', axis=1).set_index(['node', 'hour']).to_dict()['value']
            
        self.current_v = cur_var_node_t[cur_var_node_t['vartype'] == 'start']\
            .drop('vartype', axis=1).set_index(['node', 'hour']).to_dict()['value']
        
        self.current_w = cur_var_node_t[cur_var_node_t['vartype'] == 'shut']\
            .drop('vartype', axis=1).set_index(['node', 'hour']).to_dict()['value']
            
        # Prevent numerical instability by converting to binary values
        self.current_u = {k: int(v) for k, v in self.current_u.items()}
        self.current_v = {k: int(v) for k, v in self.current_v.items()}
        self.current_w = {k: int(v) for k, v in self.current_w.items()}
        
        # Record the results after incrementing the hour by the simulation period
        cur_var_node_t = increment_hour(cur_var_node_t, T=self.T, k=k)
        self.var_node_t = pd.concat(
            [self.var_node_t, cur_var_node_t],
            axis = 0)
        
        cur_var_flow = increment_hour(cur_var_flow, T=self.T, k=k)
        self.var_flow = pd.concat(
            [self.var_flow, cur_var_flow],
            axis = 0)
        
        # Currently there is only the system-wider reserve
        cur_var_syswide = increment_hour(cur_var_syswide, T=self.T, k=k)
        self.var_syswide = pd.concat(
            [self.var_syswide, cur_var_syswide],
            axis = 0)
        
        
        # Need to calculate the minimum time on/off
        self.current_min_on = get_init_min_on(cur_var_node_t, self.T, system_input)
        self.current_min_off = get_init_min_off(cur_var_node_t, self.T, system_input)
    
    
    def get_init_conds(self) -> dict[str, dict]:
        return {
            'initial_p': self.current_p, 
            'initial_u': self.current_u, 
            'initial_v': self.current_v,
            'initial_w': self.current_w,
            'initial_min_on': self.current_min_on, 
            'initial_min_off': self.current_min_off
            }
    
    
    def get_record(self) -> None:
        return [self.var_node_t, self.var_flow, self.var_syswide]
    
    
    def to_csv(self) -> None:
        raise NotImplementedError('Record.to_csv() has not been implemented.')
    
    