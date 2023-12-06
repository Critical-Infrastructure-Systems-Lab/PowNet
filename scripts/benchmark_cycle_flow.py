# Solves the first day of PowNet
from collections import defaultdict
from datetime import datetime
import itertools
import os

import pandas as pd

from pownet.core.input import SystemInput
from pownet.core.simulation import Simulator
from pownet.core.visualize import Visualizer
from pownet.folder_sys import get_output_dir


SAVE_FUELMIX = True
SAVE_RESULT = True

MODEL_NAMES = ['dummy_trade', 'dummy_cycle', 'laos', 'cambodia', 'malaysia', 'thailand']
FORMULATIONS = ['voltage_angle', 'kirchhoff']

###############
ctime = datetime.now().strftime("%Y%m%d_%H%M")
save_folder = f'{ctime}_compare_flow'
save_folder = os.path.join(get_output_dir(), save_folder)
if not os.path.exists(save_folder) and SAVE_FUELMIX:
    os.makedirs(save_folder)

combinations = itertools.product(MODEL_NAMES, FORMULATIONS)

benchmark_record = defaultdict(dict)
for (model_name, formulation) in combinations:
    
    # The default simulation horizon T is 24 hours
    T = 24
    # One year has 8760 hours. If T = 24, then we have 365 steps.
    STEPS = 1
    
    #############################
    output_dir = get_output_dir()
    
    # We need a folder to store the figures
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # The user should create their own model in the model_library folder
    system_input = SystemInput(
        T = T,
        formulation = formulation,
        model_name = model_name
        )
    
    simulator = Simulator(system_input=system_input)
    dw_record = simulator.run(
        steps=STEPS,
        timelimit = 60
        )
    
    var_node_t = dw_record.get_node_variables()
    
    visualizer = Visualizer()
    visualizer.load(df=var_node_t, system_input=system_input, model_name=model_name)
    
    combination_name = f'{model_name}_{formulation}'
    
    visualizer.plot_fuelmix(
        to_save = SAVE_FUELMIX,
        output_folder = os.path.join(output_dir, save_folder),
        figure_name = combination_name
        )
    
    # Statistics
    model = simulator.model
    model_objval = int(model.objval)
    model_runtime = round(model.runtime, 4)
    model_itercount = int(model.itercount)
    model_num_vars = len(model.getVars())
    model_num_constrs = len(model.getConstrs())
    model_mipgap = round(model.mipgap*100, 3)
    
    benchmark_record[combination_name]['objval'] = model_objval
    benchmark_record[combination_name]['runtime'] = model_runtime
    benchmark_record[combination_name]['itercount'] = model_itercount
    benchmark_record[combination_name]['num_vars'] = model_num_vars
    benchmark_record[combination_name]['num_constrs'] = model_num_constrs
    benchmark_record[combination_name]['mipgap_pct'] = model_mipgap
    
    print(f'\n{combination_name}')
    print(f'{"Objval:":<20} {model_objval}')
    print(f'{"Solve time (s):":<20} {model_runtime}')
    print(f'{"# Simplex iter:":<20} {model_itercount}')
    print(f'{"# Variables:":<20} {model_num_vars}')
    print(f'{"# Constraints:":<20} {model_num_constrs}')
    print(f'{"MIP GAP (%):":<20} {model_mipgap}')


benchmark_record_df = pd.DataFrame(benchmark_record)

if SAVE_RESULT:
    benchmark_record_df.to_csv(
        os.path.join(
            get_output_dir(), 
            f'{ctime}_compare_flow.csv'
            )
        )


