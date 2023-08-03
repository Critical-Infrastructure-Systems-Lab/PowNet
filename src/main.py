from simulation import Simulator




if __name__ == '__main__':
    # User defined inputs
    T = 24
    model_folder = '..//data//'
    
    # Running the simulation
    simulation = Simulator(T, model_folder)
    simulation.run()
    