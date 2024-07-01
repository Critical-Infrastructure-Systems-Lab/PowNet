from datetime import datetime
import os
import pandas as pd
from pownet.config import is_warmstart
from pownet.core.input import SystemInput
from pownet.core.simulation import Simulator
from pownet.core.output import OutputProcessor, Visualizer
from pownet.folder_sys import get_output_dir, delete_all_gurobi_solutions
import ast
import glob
from pownet.processing.functions import create_init_condition
import pownet.config as config

def main():
    # ------- User defined inputs from the configuration file
    STEP_BY_STEP=config.get_stepbystep()
    ONE_STEP=config.get_onestep()
    MODEL_NAME = config.get_modelname()
    use_gurobi = config.get_usegurobi()
    
    # The default simulation horizon T is 24 hours
    T = config.get_timehorizon()
    # One year has 8760 hours. If T = 24, then we have 365 steps.
    # STEPS = math.floor(8760/T)
    STEPS = config.get_steps()

    # Decide whether to save results
    SAVE_RESULT = config.get_saveresults()
    SAVE_PLOT = config.get_saveplots()

    output_dir = get_output_dir()
    
    # We need a folder to store the figures
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    if STEP_BY_STEP: # STEP_BY_STEP Version
        print('\n\n Running STEP_BY_STEP Version..........')
        for SIM_DAY in range(1,STEPS+1):
            run_pownet(MODEL_NAME,T,STEPS,SIM_DAY,use_gurobi,output_dir,SAVE_RESULT,SAVE_PLOT)
            
    elif ONE_STEP: # ONE_STEP Version
        print('\n\n Running ONE_STEP Version..........')
        SIM_DAY=config.get_simday()
        run_pownet(MODEL_NAME,T,STEPS,SIM_DAY,use_gurobi,output_dir,SAVE_RESULT,SAVE_PLOT)
        
    else:   # ALL_STEPS Version
        print('\n\n Running ALL_STEPS Version..........')
        SIM_DAY=STEPS
        run_pownet(MODEL_NAME,T,STEPS,SIM_DAY,use_gurobi,output_dir,SAVE_RESULT,SAVE_PLOT)
        
    
def run_pownet(MODEL_NAME,T,STEPS,SIM_DAY,use_gurobi,output_dir,SAVE_RESULT,SAVE_PLOT):
        
    time_start = datetime.now()
    
    #1) Read System Input for Given Model Region and Time/Day [Users should create their own model in the model_library folder]
    system_input = SystemInput(T=T, formulation="kirchhoff", model_name=MODEL_NAME,simulated_day=SIM_DAY-1)
    
    #2) Intialize a Simulator Instance 
    simulator = Simulator(system_input=system_input, use_gurobi=use_gurobi)
    
    #3) Read or Define Initial Conditions
    fileslist=[file for file in glob.glob(output_dir+'/*%s_D%d_T%d_initial_conditions.csv'%(MODEL_NAME,SIM_DAY-1,T))]
    if len(fileslist)==0:
        init_conds = create_init_condition(
            thermal_units=system_input.thermal_units, T=T)
    else:
        init_conds_file=sorted(fileslist,reverse=True)[0]
        df_init=pd.read_csv(init_conds_file)
        df_init=df_init.set_index('Variable')
        init_conds = {}
        for i in range(len(df_init)):
            x=df_init.index[i]
            y=df_init.iloc[i].values[0]
            init_conds[x] = ast.literal_eval(y)   
      
    #4) Run PowNet Simulator 
    simulator_run = simulator.run(steps=STEPS,init_conds=init_conds,simulated_day=SIM_DAY-1)
    print("\n\n====")
    print(f"PowNet: Solved {MODEL_NAME}")
    print(
        f"PowNet: Total time (s) = {round((datetime.now() - time_start).total_seconds(), 2)}"
    )
    print(f"PowNet: Opt.time (s) = {round(sum(simulator_run.runtimes), 2)}")
    
    #5) Save PowNet Results 
    if SAVE_RESULT:
        simulator_run.to_csv()

    #6) Plot PowNet Results 
    if SAVE_PLOT:
        node_variables = simulator_run.get_node_variables()
        
        output_processor = OutputProcessor()
        output_processor.load(
            df=node_variables, system_input=system_input, model_name=MODEL_NAME
        )
    
        visualizer = Visualizer(model_name=MODEL_NAME, ctime=output_processor.ctime)
        visualizer.plot_fuelmix_area(
            dispatch=output_processor.get_total_dispatch(),
            demand=output_processor.get_total_demand(),
            to_save=SAVE_PLOT,
        )
        # The dispatch plot does not work well when simulating more than 2 day or
        # there are more than 10 thermal units.
        if STEPS <= 48 and len(system_input.thermal_units) <= 10:
            visualizer.plot_thermal_units(
                thermal_dispatch=output_processor.get_dispatch(),
                unit_status=output_processor.get_unit_status(),
                thermal_units=system_input.thermal_units,
                full_max_cap=system_input.full_max_cap,
                to_save=SAVE_PLOT,
            )
    # Delete the last solution file when warmstarting
    if is_warmstart():
        delete_all_gurobi_solutions()

if __name__ == "__main__":
    main()
