from datetime import datetime
import os

from pownet.core.input import SystemInput
from pownet.core.simulation import Simulator
from pownet.core.visualize import Visualizer
from pownet.folder_sys import get_output_dir



def main():
    #------- User defined inputs
    MODEL_NAME = 'laos'
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
        model_name = MODEL_NAME
        )
    
    simulator = Simulator(T=T, system_input=system_input)
    var_node_t, _, _ = simulator.run(steps=STEPS)
    
    var_node_t.to_csv(
    os.path.join(
        get_output_dir(),
        f'{datetime.now().strftime("%Y%m%d_%H%M")}_{MODEL_NAME}_outputs.csv'
        )
    )
    
    visualizer = Visualizer()
    visualizer.load(df=var_node_t, system_input=system_input, model_name=MODEL_NAME)
    
    visualizer.plot_fuelmix(to_save=False)
    # The dispatch plot does not work well when simulating more than 2 days.
    if STEPS <= 48 and False: # Will implement better logic control later
        visualizer.plot_thermal_units(to_save=False)



if __name__ == '__main__':
    main()
