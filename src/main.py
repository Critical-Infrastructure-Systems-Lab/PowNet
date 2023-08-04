from processing.input import SystemInput
from core.simulation import Simulator
from core.visualize import Visualizer



if __name__ == '__main__':
    #------- User defined inputs
    # The default simulation horizon T is 24 hours
    T = 24
    model_folder = 'user_inputs'
    
    system_input = SystemInput(T=T, model_folder=model_folder)
    
    simulator = Simulator(T=T, system_input=system_input)
    var_node_t, var_flow, var_syswide = simulator.run()
    
    visualizer = Visualizer()
    visualizer.load(df=var_node_t, system_input=system_input)
    
    visualizer.plot_fuelmix(to_save=True)
    visualizer.plot_thermal_units(to_save=True)