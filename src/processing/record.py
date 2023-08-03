import gurobipy as gp
import pandas as pd



def get_nodehour(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Extract the node and hour information
    pat_node_time = r'(\w+)\[(.+),(\d+)\]'
    out_df = df['varname'].str.extract(pat_node_time, expand=True)
    out_df.columns = ['vartype', 'node', 'hour']
    out_df['hour'] = out_df['hour'].astype('int')
    out_df = pd.concat([out_df, df['value']], axis=1)
    return out_df


def get_nodehour_flow(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Flow is in the (node_a, node_b, t) format
    pat_node_time = r'(\w+)\((.+)_(\d+)\)'
    out_df = df['varname'].str.extract(pat_node_time, expand=True)
    out_df.columns = ['vartype', 'node', 'hour']
    out_df['hour'] = out_df['hour'].astype('int')
    return out_df


def get_nodehour_syswide(df: pd.DataFrame) -> pd.DataFrame:
    # System-wide variables are indexed only by t
    df = df.copy()
    pass



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
        self.current_min_on = None
        self.current_min_off = None
    
    
    def keep(self, model:gp.Model, k) -> None:
        # Extract the variables from the model to process them
        all_vars = model.getVars()
        values = model.getAttr("X", all_vars)
        names = model.getAttr("VarName", all_vars)
        results = pd.DataFrame({'varname':names, 'value':values})
        
        # Create a col of variable types for filtering
        pat_vartype = r'(\w+)\['
        results[['vartype']] = results['varname'].str.extract(pat_vartype, expand=True)
        
        # Some variables are not in the (node, t) format
        col2exclude = ['flow', 'rsys']
        
        # Format the dataframe into vartype, node, hour, value columns
        cur_var_node_t = results[~results['vartype'].isin(col2exclude)]
        cur_var_node_t = get_nodehour(cur_var_node_t)
        
        # Record the results
        self.var_node_t = pd.concat(
            [self.var_node_t, cur_var_node_t],
            axis = 0)
        
        self.var_flow = pd.concat(
            [self.var_flow, results[results['vartype'] == 'flow']],
            axis = 0)
        
        # Currently there is only the system-wider reserve
        self.var_syswide = pd.concat(
            [self.var_syswide, results[results['vartype'] == 'rsys']],
            axis = 0)
        
        # Save some variables as initial conditions for the next simulation period
        self.current_p = cur_var_node_t[cur_var_node_t['vartype'] == 'p']\
            .drop('vartype', axis=1).set_index(['node', 'hour']).to_dict()['value']
        
        self.current_u = cur_var_node_t[cur_var_node_t['vartype'] == 'u']['value']
        self.current_v = cur_var_node_t[cur_var_node_t['vartype'] == 'v']['value']
        
        # # Need to calculate the minimum time on/off
        # self.current_min_on = self.var_node_t[self.var_node_t['vartype'] == 'p']['value']
        # self.current_min_off = self.var_node_t[self.var_node_t['vartype'] == 'p']['value']
    
    
    def get_init_conds(self, T: int) -> dict[str, dict]:
        pairs = [
            ('initial_p', 'p'), ('initial_u', 'u'), ('initial_v', 'v'), 
            ('initial_min_on', 'min_on'), ('initial_min_off', 'min_off')]
        
        init_conds = {}
        
        for kname, vname in pairs:
            # Extract the values across 24 hours
            self.var_node_t[self.var_node_t['vartype'] == vname]['value']
            
            # Our indexing starts at t=1
            init_conds[k] = {idx+1: val for idx in range(self.T)}
            init_conds[k] = self.var_node_t[self.var_node_t['vartype'] == vname]
        
        # initial_p = {unit_g: {t: 0 for t in range(1, 25)} for unit_g in thermal_units}
        # initial_u = initial_p.copy()
        # initial_v = initial_p.copy()
        # initial_min_on = initial_p.copy()
        # initial_min_off = initial_p.copy()
    
    
    def get_record(self) -> None:
        pass
    
    
    def to_csv(self) -> None:
        pass
    
    