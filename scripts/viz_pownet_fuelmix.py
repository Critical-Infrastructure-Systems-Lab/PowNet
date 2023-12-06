# viz_pownet_fuelmix.py
import os

import pandas as pd
from pownet.folder_sys import get_output_dir


# Find which node has shortfall
df = pd.read_csv(
    os.path.join(get_output_dir(), '20231205_2128_thailand_node_variables.csv')
    )

df = df[df['vartype'] == 's_pos']
df = df[df['value'] > 0]


