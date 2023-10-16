import math
import os

from core.input import SystemInput
from core.simulation import Simulator
from core.visualize import Visualizer



MODEL_NAME = 'laos'



def main():
    #------- User defined inputs
    # The default simulation horizon T is 24 hours
    T = 24
    
    # One year has 8760 hours. If T = 24, then we have 365 steps.
    steps = math.floor(8760/T)
    # steps = 2
    
    wdir = os.path.dirname((os.path.dirname(os.getcwd())))
    
    # We need a folder to store the figures
    if not os.path.exists(os.path.join(wdir, 'outputs')):
        os.makedirs(os.path.join(wdir, 'outputs'))
    
    
    system_input = SystemInput(
        T=T, model_folder=os.path.join(wdir, 'model_library', MODEL_NAME)
        )
    
    simulator = Simulator(T=T, system_input=system_input)
    var_node_t, _, _ = simulator.run(steps=steps)
    # var_node_t.to_csv(os.path.join(wdir, 'outputs', f'{MODEL_NAME}_results.csv'))
    
    visualizer = Visualizer()
    visualizer.load(df=var_node_t, system_input=system_input)
    
    visualizer.plot_fuelmix(to_save=True)
    # visualizer.plot_thermal_units(to_save=False)



if __name__ == '__main__':
    main()
