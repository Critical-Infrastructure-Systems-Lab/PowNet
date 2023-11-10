import os

from pownet.core.input import SystemInput
from pownet.core.simulation import Simulator
from pownet.folder_sys import get_model_dir


MODEL_NAME = 'thailand'
MODEL_FOLDER = os.path.join(get_model_dir(), MODEL_NAME)

WRITE_DEC = False


# We are only optimizing one step which is 24 hours. This optimization
# is just to initiate a model so we can extract the model from Gurobi
T = 24
steps = 2



##--------------- This section writes MPS file(s)
system_input = SystemInput(T=T, model_name=MODEL_NAME)
simulator = Simulator(
    T = T, 
    system_input = system_input,
    model_name = MODEL_NAME,
    write_model = True)

# Run the model to instantiate the model
var_node_t, var_flow, var_syswide = simulator.run(steps=steps)

