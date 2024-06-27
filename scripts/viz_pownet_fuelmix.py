# viz_pownet_fuelmix.py
import os

import pandas as pd
from pownet.folder_sys import get_output_dir
from pownet.core.input import SystemInput
from pownet.core.output import Visualizer, OutputProcessor


MODEL_NAME = "dummy_hydro"
T = 24

node_variables = pd.read_csv(
    os.path.join(get_output_dir(), "20240603_0952_dummy_hydro_24_node_variables.csv")
)


system_input = SystemInput(T=T, formulation="kirchhoff", model_name=MODEL_NAME)

output_processor = OutputProcessor()
output_processor.load(
    df=node_variables, system_input=system_input, model_name=MODEL_NAME
)
output_processor = OutputProcessor()
output_processor.load(
    df=node_variables, system_input=system_input, model_name=MODEL_NAME
)

visualizer = Visualizer(model_name=MODEL_NAME, ctime=output_processor.ctime)
visualizer.plot_fuelmix_bar(
    dispatch=output_processor.get_total_dispatch(),
    demand=output_processor.get_total_demand(),
    to_save=False,
)
