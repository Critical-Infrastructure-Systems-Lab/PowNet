from math import floor
import pandas as pd

from core.builder import ModelBuilder
from processing.functions import create_init_condition
from processing.input import SystemInput
from processing.record import SystemRecord


# TODO: Implement warm start


class Simulator:
    def __init__(self, T: int, model_folder: str) -> None:
        self.T = T
        self.model_folder = model_folder
        
        
    def run(self) -> None:
        # Instantiate objects
        system_record = SystemRecord(self.T)
        
        system_input = SystemInput(model_folder=self.model_folder, T=self.T)
        builder = ModelBuilder(system_input)
        
        # One year has 8760 hours. If T = 24, then we have 365 steps.
        steps = floor(8760/self.T)
        
        # Initially, we can define the initial conditions
        init_conds = create_init_condition(system_input.thermal_units)
        
        # The indexing of 'i' starts at zero because we use this to
        # index the parameters of future simulation periods (t + self.i*self.T)
        for k in range(0, 1):#steps):
            # Create a gurobipy model for each simulation period
            model = builder.build(
                k = k,
                init_conds = init_conds)
            
            model.optimize()
            
            # Need k to increment the hours field
            system_record.keep(model, k)
            init_conds = system_record.get_init_conds(k)
        
        # # Export the final results somewhere
        # system_record.to_csv()
        # return system_record.get_record()
        return model
    
    
    
    
if __name__ == '__main__':
    simulator = Simulator(T=24, model_folder='user_inputs')
    model = simulator.run()
