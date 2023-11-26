# Solves the first day of PowNet
from collections import defaultdict
import itertools
import os

import pandas as pd

from pownet.core.input import SystemInput
from pownet.core.simulation import Simulator
from pownet.core.visualize import Visualizer
from pownet.folder_sys import get_output_dir


MODEL_NAMES = ['dummy_trade', 'dummy_cycle', 'laos', 'cambodia', 'malaysia', 'thailand']
FORMULATIONS = ['voltage_angle', 'kirchhoff']
combinations = itertools.product(MODEL_NAMES, FORMULATIONS)

record = defaultdict(dict)
for (model_name, formulation) in combinations:
    model_name = 'laos'
    formulation = 'voltage_angle'
    
    # The default simulation horizon T is 24 hours
    T = 24
    # One year has 8760 hours. If T = 24, then we have 365 steps.
    # STEPS = math.floor(8760/T)
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
    var_node_t, _, _ = simulator.run(steps=STEPS)
    
    visualizer = Visualizer()
    visualizer.load(df=var_node_t, system_input=system_input, model_name=model_name)
    
    visualizer.plot_fuelmix(to_save=False)
    
    # Statistics
    model = simulator.model
    combination_name = f'{model_name}_{formulation}'
    model_objval = int(model.objval)
    model_runtime = round(model.runtime, 4)
    model_itercount = int(model.itercount)
    model_num_vars = len(model.getVars())
    model_num_constrs = len(model.getConstrs())
    model_mipgap = round(model.mipgap, 3)
    
    record[combination_name]['objval'] = model_objval
    record[combination_name]['runtime'] = model_runtime
    record[combination_name]['itercount'] = model_itercount
    record[combination_name]['num_vars'] = model_num_vars
    record[combination_name]['num_constrs'] = model_num_constrs
    record[combination_name]['mipgap'] = model_mipgap
    
    
    print(f'\n{combination_name}')
    print(f'{"Objval:":<20} {model_objval}')
    print(f'{"Solve time (s):":<20} {model_runtime}')
    print(f'{"# Simplex iter:":<20} {model_itercount}')
    print(f'{"# Variables:":<20} {model_num_vars}')
    print(f'{"# Constraints:":<20} {model_num_constrs}')
    print(f'{"MIP GAP:":<20} {model_mipgap}')


record_df = pd.DataFrame(record)


