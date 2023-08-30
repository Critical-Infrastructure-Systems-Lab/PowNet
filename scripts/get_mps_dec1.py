import os
import re

import pandas as pd

from pownet.core.input import SystemInput
from pownet.core.simulation import Simulator
# from core.visualize import Visualizer



##--------------- Create the model
# The default simulation horizon T is 24 hours
T = 24

# One year has 8760 hours. If T = 24, then we have 365 steps.
# steps = floor(8760/self.T)
steps = 1

model_folder = 'user_inputs'

# We need a folder to store the figures
if not os.path.exists('..//outputs'):
    os.makedirs('..//outputs')

system_input = SystemInput(T=T, model_folder=model_folder)

simulator = Simulator(T=T, system_input=system_input)

var_node_t, var_flow, var_syswide = simulator.run(steps=steps)


##--------------- Extract the info
model = simulator.model

constr_list = model.getConstrs()

constr_df = [constr.constrName for constr in constr_list]
constr_df = pd.DataFrame(constr_df, columns=['name'])

##--------------- Extract the constraint types
pat_constr_type = r'(.+)\['
constr_types_set = set(
    constr_df['name'].str.extract(pat_constr_type, expand=True)[0].tolist()
    )

constr_df['type'] = constr_df['name'].str.extract(pat_constr_type, expand=True)

print('\n\n===========')
print('\nNumber of constraint types:', len(constr_types_set))


##--------------- Writes a dec file
thermal_units = pd.read_csv(
    os.path.join('..\\user_inputs', 'unit_param.csv'), 
    header = 0, index_col='name', usecols = ['name']).index.tolist()

# Numbering in .dec file starts at 1
subp_map = {x: (idx+1) for idx, x in enumerate(thermal_units)}

num_blocks = len(thermal_units)

unit_constraints = [
    'link_p',
    'link_uv',
    'link_uv_init',
    'minDown',
    'minUp',
    'minUpInit',
    'minDownInit',
    'peakDownBnd',
    'peakUpBnd',
    'rampDown',
    'rampDownInit',
    'rampUp',
    'rampUpInit',
    'trajecDownBnd',
    'trajecUpBnd',
    'trajecUpBnd2',
    'upper_p'
    ]

# Specify the corresponding block of each constraint
def map_block(row):
    constr_name = row['name']
    # Extract node
    pat_node = r'\[(\w+)'
    re_match = re.findall(pat_node, constr_name)
    constr_node = re_match[0]
    # The block number of the master problem is zero
    if row['type'] in unit_constraints:
        return subp_map[constr_node]
    else:
        return 0

constr_df['block_id'] = constr_df.apply(map_block, axis=1)

# Replace unlabelled constraints with zero which represents the master problem
nan_mask = constr_df['block_id'].isna()
constr_df[nan_mask] = 0
print('Number of unlabelled constraints', sum(nan_mask))

master_constrs = constr_df.loc[constr_df['block_id']==0, 'name'].tolist()


# This section writes the text file
filename = 'power_system'
with open(f'.\\analysis\\decom_files\\{filename}.dec', 'w') as f:
    # Unspecified constraints are put into the master problem
    f.write('CONSDEFAULTMASTER')
    f.write('\n')
    f.write('1')
    f.write('\n')
    
    # The decomposition was not from a presolved problem
    f.write('PRESOLVED')
    f.write('\n')
    f.write('0')
    f.write('\n')
    
    # The number of blocks is the number of thermal units plus an empty subproblem
    f.write('NBLOCKS')
    f.write('\n')
    f.write(str(num_blocks+1))
    f.write('\n')
    
    # The indexing of .dec starts at one
    for subp_id in range(1, num_blocks+1):
        # Write the block header
        f.write(f'BLOCK {subp_id}')
        f.write('\n')
        # Dump the constraints in each block
        block_constrs = constr_df.loc[constr_df['block_id']==subp_id, 'name'].tolist()
        for block_constr in block_constrs:
            f.write(block_constr)
            f.write('\n')
    
    f.write('MASTERCONSS')
    f.write('\n')
    
    for master_constr in master_constrs:
        f.write(master_constr)
        f.write('\n')
    

# Write the lp file
simulator.model.write(f'.\\analysis\\decom_files\\{filename}.mps')
