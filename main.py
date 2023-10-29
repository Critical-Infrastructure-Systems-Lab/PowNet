import math
import os

from pownet.core.input import SystemInput
from pownet.core.simulation import Simulator
from pownet.core.visualize import Visualizer
from pownet.folder_sys import get_output_dir



def main():
    #------- User defined inputs
    # The default simulation horizon T is 24 hours
    T = 24
    
    # One year has 8760 hours. If T = 24, then we have 365 steps.
    # steps = math.floor(8760/T)
    steps = 1
    
    output_dir = get_output_dir()
    
    # We need a folder to store the figures
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # The user should create their own model in the model_library folder
    system_input = SystemInput(
        T = T,
        model_name = MODEL_NAME
        )
    
    simulator = Simulator(T=T, system_input=system_input)
    var_node_t, _, _ = simulator.run(steps=steps)
    
    # var_node_t.to_csv(
    # os.path.join(get_output_dir(), f'{MODEL_NAME}_results.csv'))
    
    visualizer = Visualizer()
    visualizer.load(df=var_node_t, system_input=system_input)
    
    visualizer.plot_fuelmix(to_save=False)
    visualizer.plot_thermal_units(to_save=False)



if __name__ == '__main__':
    MODEL_NAME = 'dummy_trade'
    main()
