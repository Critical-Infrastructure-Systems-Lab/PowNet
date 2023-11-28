import os

from pownet.core.builder import ModelBuilder
from pownet.core.input import SystemInput
from pownet.core.record import SystemRecord
from pownet.processing.functions import create_init_condition, get_current_time
from pownet.config import is_warmstart
from pownet.folder_sys import get_output_dir



class Simulator:
    def __init__(
            self, 
            system_input: SystemInput,
            write_model: bool = False,
            ) -> None:
        self.model = None
        
        self.system_input = system_input
        self.T = self.system_input.T
        
        self.model_name = system_input.model_name
        self.write_model = write_model
        
        
    def run(self, steps: int) -> SystemRecord:
        # Instantiate objects
        system_record = SystemRecord(self.system_input)
        
        builder = ModelBuilder(self.system_input)
        
        # Initially, we can define the initial conditions
        init_conds = create_init_condition(
            thermal_units = self.system_input.thermal_units,
            T = self.T
            )
        
        # The indexing of 'k' starts at zero because we use this to
        # index the parameters of future simulation periods (t + self.k*self.T)
        for k in range(0, steps):
            # Create a gurobipy model for each simulation period
            print('\n\n\n============')
            print(f'Simulate step {k+1}\n\n')
            
            if k == 0:
                self.model = builder.build(
                    k = k,
                    init_conds = init_conds)
            else:
                self.model = builder.update(
                    k = k,
                    init_conds = init_conds)
            self.model.optimize()
            
            # In case when the model is infeasible, we generate an output file
            # to troubleshoot the problem. The model should always be feasible.
            if self.model.status == 3:
                print(f'Iteration: {k} is infeasible.')
                self.model.computeIIS()
                c_time = get_current_time()
                ilp_file = os.path.join(
                    get_output_dir(),
                    f'infeasible_{self.model_name}_{k}_{c_time}.ilp'
                    )
                self.model.write(ilp_file)
                
                mps_file = os.path.join(
                    get_output_dir(),
                    f'infeasible_{self.model_name}_{k}_{c_time}.mps'
                    )
                self.model.write(mps_file)
                break
            
            # Save the solution file to warmstart the next instance
            if is_warmstart():
                self.model.write(
                    os.path.join(
                        get_output_dir(), f'{self.model_name}_{k}.sol'
                        )
                    )
            
            # Need k to increment the hours field
            system_record.keep(self.model, k)
            init_conds = system_record.get_init_conds()
            
            if self.write_model:
                # Save the model
                dirname = os.path.join(
                    get_output_dir(), f'{self.model_name}_instances'
                    )
                if not os.path.exists(dirname):
                    os.makedirs(dirname)
                self.model.write(
                    os.path.join(
                        dirname, f'{self.model_name}_{k}.mps'
                        )
                    )
        
        return system_record.get_record()
    
    
    
if __name__ == '__main__':
    print('Jigglypuffs')
    
