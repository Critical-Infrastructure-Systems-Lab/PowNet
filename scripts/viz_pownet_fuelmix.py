# viz_pownet_fuelmix.py
import os

import pandas as pd
from pownet.folder_sys import get_output_dir
from pownet.core.input import SystemInput
from pownet.core.output import Visualizer



MODEL_NAME = 'laos'
T = 24

node_variables = pd.read_csv(
    os.path.join(get_output_dir(), '20231212_1327_laos_node_variables.csv')
    )


system_input = SystemInput(
    T = T,
    formulation = 'kirchhoff',
    model_name = MODEL_NAME
    )

visualizer = Visualizer()
visualizer.load(
    df = node_variables, 
    system_input = system_input, 
    model_name = MODEL_NAME
    )

visualizer.plot_area_fuelmix()
