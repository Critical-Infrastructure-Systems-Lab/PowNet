import os

from pownet.core.builder import ModelBuilder
from pownet.core.input import SystemInput
from pownet.core.record import SystemRecord
from pownet.processing.functions import create_init_condition
from pownet.folder_sys import get_output_dir, get_temp_dir



class Simulator:
    def __init__(
            self, 
            T: int, 
            system_input: SystemInput,
            model_name: str = None,
            write_model: bool = False,
            ) -> None:
        self.model = None
        self.T = T
        self.system_input = system_input
        self.model_name = model_name
        self.write_model = write_model
        
        
    def run(self, steps: int) -> SystemRecord:
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
            
            if k == 0:
                self.model = builder.build(
                    k = k,
                    init_conds = init_conds)
            else:
                # TODO: Implement warm start
                self.model = builder.update(
                    k = k,
                    init_conds = init_conds)
            self.model.optimize()
            
            # Check model status
            if self.model.status == 3:
                print(f'Iteration: {k} is infeasible.')
                self.model.computeIIS()
                ilp_file = os.path.join(
                    get_temp_dir(),
                    f'infeasible_{self.model_name}_{k}.ilp'
                    )
                self.model.write(ilp_file)
                
                mps_file = os.path.join(
                    get_temp_dir(),
                    f'infeasible_{self.model_name}_{k}.mps'
                    )
                self.model.write(mps_file)
                break
            
            # Need k to increment the hours field
            system_record.keep(self.model, k, self.system_input)
            init_conds = system_record.get_init_conds()
            
            # Save the model
            output_dir = get_output_dir()
            dirname = f'{self.model_name}_instances'
            dirname = os.path.join(output_dir, dirname)
            
            if self.write_model:
                if not os.path.exists(dirname):
                    os.makedirs(dirname)
                self.model.write(
                    os.path.join(
                        dirname, f'{self.model_name}_{k}.mps'
                        )
                    )
        
        # # Export the final results somewhere
        # system_record.to_csv()
        return system_record.get_record()
    
    
    
if __name__ == '__main__':
    print('Jigglypuffs')
    
