import os

from pownet.config import is_warmstart
from pownet.core.input import SystemInput
from pownet.core.simulation import Simulator
from pownet.core.visualize import Visualizer
from pownet.folder_sys import get_output_dir, delete_all_gurobi_solutions



def main():
    #------- User defined inputs
    MODEL_NAME = 'dummy_trade'
    # The default simulation horizon T is 24 hours
    T = 24
    # One year has 8760 hours. If T = 24, then we have 365 steps.
    # STEPS = math.floor(8760/T)
    STEPS = 2
    
    #############################
    output_dir = get_output_dir()
    
    # We need a folder to store the figures
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # The user should create their own model in the model_library folder
    system_input = SystemInput(
        T = T,
        formulation = 'voltage_angle',
        model_name = MODEL_NAME
        )
    
    simulator = Simulator(system_input=system_input)
    
    record = simulator.run(steps=STEPS)
    record.to_csv()
    
    node_variables = record.get_node_variables()
    
    visualizer = Visualizer()
    visualizer.load(df=node_variables, system_input=system_input, model_name=MODEL_NAME)
    
    visualizer.plot_fuelmix(to_save=False)
    # The dispatch plot does not work well when simulating more than 2 day or
    # there are more than 10 thermal units.
    if STEPS <= 48 and len(system_input.thermal_units) <= 10:
        visualizer.plot_thermal_units(to_save=False)
        
    # Delete the last solution file when warmstarting
    if is_warmstart():
        delete_all_gurobi_solutions()



if __name__ == '__main__':
    main()
