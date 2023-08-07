from math import floor

from core.builder import ModelBuilder
from core.input import SystemInput
from core.record import SystemRecord
from processing.functions import create_init_condition


# TODO: Implement warm start


class Simulator:
    def __init__(self, T: int, system_input: SystemInput) -> None:
        self.T = T
        self.system_input = system_input
        
        
    def run(self, steps) -> None:
        # Instantiate objects
        system_record = SystemRecord(self.T)
        
        builder = ModelBuilder(self.system_input)
        
        # Initially, we can define the initial conditions
        init_conds = create_init_condition(self.system_input.thermal_units, self.T)
        
        # The indexing of 'i' starts at zero because we use this to
        # index the parameters of future simulation periods (t + self.i*self.T)
        for k in range(0, steps):
            # Create a gurobipy model for each simulation period
            print('\n\n\n============')
            print(f'Simulate step {k+1}\n\n')
            model = builder.build(
                k = k,
                init_conds = init_conds)
            
            model.optimize()
            
            # Check model status
            if model.status == 3:
                print(f'Iteration: {k} is infeasible.')
                model.computeIIS()
                model.write('infeasible.ilp')
                break
            
            # Need k to increment the hours field
            system_record.keep(model, k, self.system_input)
            init_conds = system_record.get_init_conds(k)
        
        # # Export the final results somewhere
        # system_record.to_csv()
        return system_record.get_record()
    
    
    
    
    
if __name__ == '__main__':
    print('Jigglypuffs')
    
