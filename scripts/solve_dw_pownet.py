# Solves PowNet
from datetime import datetime
import os

import pandas as pd

from pypolp.dw.dw import DantzigWolfe, Record
from pypolp.tools.parser import parse_mps_dec


MODEL_NAME = 'laos'

# Get out of decomposition and src
CTIME = c_time = datetime.now().strftime("%Y%m%d_%H%M")
PDIR = os.path.dirname(os.getcwd())
INSTANCE_FOLDER = os.path.join(PDIR, 'temp', f'{MODEL_NAME}_instances')
path_dec = os.path.join(INSTANCE_FOLDER, f'{MODEL_NAME}.dec')


master_times = []
master_itercounts = []

subp_times = []
subp_itercounts = []

# The number of MPS files is the total number of instances.
# Note that we have one DEC file, so we need to subtract 1
num_instances = len(os.listdir(INSTANCE_FOLDER)) - 1
for k in range(num_instances):
    print(f'\n\n=== Solving Day {k} ===')
    path_mps = os.path.join(INSTANCE_FOLDER, f'{MODEL_NAME}_{k}.mps')

    dw_problem = parse_mps_dec(path_mps, path_dec)
    record = Record()
    record.fit(dw_problem)
        
    dw_instance = DantzigWolfe()
    dw_instance.fit(dw_problem, record)
    dw_instance.solve(record)
    
    master_time, subp_time = dw_instance.get_stats('runtime')
    master_itercount, subp_itercount = dw_instance.get_stats('itercount')
    
    master_times.append(master_time)
    subp_times.append(subp_time)
    
    master_itercounts.append(master_itercount)
    subp_itercounts.append(subp_itercount)

# Create a dataframe and 
dw_stats = pd.DataFrame({
    'master_time': master_times,
    'master_iter': master_itercounts,
    'subp_time': subp_times,
    'subp_iter': subp_itercounts
    })

dw_stats.to_csv(
    os.path.join(PDIR, 'temp', f'{CTIME}_{MODEL_NAME}_dw_stats.csv'),
    index = False
    )
