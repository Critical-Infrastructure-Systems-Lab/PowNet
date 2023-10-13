import os

from pownet.core.input import SystemInput
from pownet.core.simulation import Simulator



CDIR = os.path.dirname(os.getcwd())

MODEL_NAME = 'laos'
MODEL_FOLDER = os.path.join(CDIR, 'model_library', MODEL_NAME)

WRITE_DEC = False


# We are only optimizing one step which is 24 hours. This optimization
# is just to initiate a model so we can extract the model from Gurobi
T = 24
steps = 5



##--------------- This section writes MPS file(s)
system_input = SystemInput(T=T, model_folder=MODEL_FOLDER)
simulator = Simulator(
    T = T, 
    system_input = system_input,
    model_name = MODEL_NAME,
    write_model = True)

# Run the model to instantiate the model
var_node_t, var_flow, var_syswide = simulator.run(steps=steps)

