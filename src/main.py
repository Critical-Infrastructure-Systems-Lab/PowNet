import os

from core.input import SystemInput
from core.simulation import Simulator
from core.visualize import Visualizer



def main():
    #------- User defined inputs
    # The default simulation horizon T is 24 hours
    T = 24
    
    # One year has 8760 hours. If T = 24, then we have 365 steps.
    # steps = floor(8760/self.T)
    steps = 1
    
    model_folder = 'user_inputs'
    
    # We need a folder to store the figures
    if not os.path.exists('..//outputs'):
        os.makedirs('..//outputs')
    
    system_input = SystemInput(T=T, model_folder=model_folder)
    
    simulator = Simulator(T=T, system_input=system_input)
    var_node_t, var_flow, var_syswide = simulator.run(steps=steps)
    
    visualizer = Visualizer()
    visualizer.load(df=var_node_t, system_input=system_input)
    
    visualizer.plot_fuelmix(to_save=True)
    visualizer.plot_thermal_units(to_save=True)



if __name__ == '__main__':
    main()
