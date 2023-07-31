import pandas as pd


def get_nodehour(df, varname):
    pat_node_time = r'(\w+)\[(.+),(\d+)\]'
    
    out_df = df['varname'].str.extract(pat_node_time, expand=True)
    out_df.columns = ['vartype', 'node', 'hour']
    out_df['hour'] = out_df['hour'].astype('int')
    
    return out_df
