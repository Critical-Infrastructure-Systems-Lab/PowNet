import os
import re

import pandas as pd

from pownet.core.input import SystemInput
from pownet.core.simulation import Simulator

from pownet.folder_sys import get_output_dir, get_model_dir



MODEL_NAME = 'dummy_trade'
MODEL_FOLDER = os.path.join(get_model_dir(), MODEL_NAME)

WRITE_DEC = True


# We are only optimizing one step which is 24 hours. This optimization
# is just to initiate a model so we can extract the model from Gurobi
T = 24
steps = 1



##--------------- This section writes MPS file(s)
system_input = SystemInput(T=T, model_name=MODEL_NAME)
simulator = Simulator(
    T = T, 
    system_input = system_input,
    model_name = MODEL_NAME,
    write_model = True)

# Run the model to instantiate the model
var_node_t, var_flow, var_syswide = simulator.run(steps=steps)



##--------------- This section writes DEC file(s)
if WRITE_DEC:
    # We will get the constraints and categorize them under blocks
    model = simulator.model
    
    constr_list = model.getConstrs()
    constr_df = [constr.constrName for constr in constr_list]
    constr_df = pd.DataFrame(constr_df, columns=['name'])
    
    # The name of constraint type ends with left bracket
    pat_constr_type = r'(.+)\['
    constr_types_set = set(
        constr_df['name'].str.extract(pat_constr_type, expand=True)[0].tolist()
        )
    
    constr_df['type'] = constr_df['name'].str.extract(pat_constr_type, expand=True)
    
    print('\n\n===========')
    print('\nNumber of constraint types:', len(constr_types_set))
    
    thermal_units = system_input.thermal_units
    num_blocks = len(thermal_units)
    
    rnw_units = system_input.rnw_units
    nodes_import = system_input.nodes_import
    
    # Indexing in a DEC file starts at 1
    subp_thermal_map = {
        x: (idx+1) for idx, x in enumerate(
            thermal_units)
        }
    
    subp_rnw_map = {
        x: (idx+1+len(subp_thermal_map)) for idx, x in enumerate(
            rnw_units)
        }
    
    subp_import_map = {
        x: (idx+1+len(subp_thermal_map)+len(subp_rnw_map)) for idx, x in enumerate(
            nodes_import)
        }
    
    unit_constraints = [
        'link_p',
        'link_uv',
        'link_uv_init',
        'minDown',
        'minUp',
        'minUpInit',
        'minDownInit',
        # 'peakDownBnd',
        # 'peakUpBnd',
        'rampDown',
        'rampDownInit',
        'rampUp',
        'rampUpInit',
        # 'trajecDownBnd',
        # 'trajecUpBnd',
        # 'trajecUpBnd2',
        'upper_p'
        ]
    
    ## Future imlementations might consider separating these blocks
    # rnw_cnstrs = ['renewBnd']
    # import_node_cnstrs = ['importBnd']
    # transmission_cnstrs = ['minFlow', 'maxFlow', 'angleDiff', 'refNode']
    
    
    # If a constraint is related to a thermal unit, then it is tagged to that unit
    def map_block(row):
        constr_name = row['name']
        # Extract node
        pat_node = r'\[(\w+)'
        re_match = re.findall(pat_node, constr_name)
        constr_node = re_match[0]
        # The block number of the master problem is zero
        if row['type'] in unit_constraints:
            return subp_thermal_map[constr_node]
        else:
            return 0
    constr_df['block_id'] = constr_df.apply(map_block, axis=1)
    
    # Replace unlabelled constraints with zero which represents the master problem
    nan_mask = constr_df['block_id'].isna()
    constr_df[nan_mask] = 0
    print('Number of unlabelled constraints', sum(nan_mask))
    
    master_constrs = constr_df.loc[constr_df['block_id']==0, 'name'].tolist()
    
    
    # This section writes the text file
    dec_filename = os.path.join(
        get_output_dir(), f'{MODEL_NAME}_instances',f'{MODEL_NAME}.dec')
    with open(dec_filename, 'w') as f:
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
        
        # The number of blocks is the number of thermal units
        f.write('NBLOCKS')
        f.write('\n')
        f.write(str(num_blocks))
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
