import sys

sys.path.append(
    "/Users/dardiry/Academia/Cornell/Research/Integrated_Modeling/Model_Couplers/Analysis/PowNet/Software_Package/Version_3_Hisham/PowNet_StepByStep_GitHub_V3.2/src"
)

from datetime import datetime
import os

from pownet.simulation import Simulator
from pownet.core import OutputProcessor, Visualizer
from pownet.folder_utils import get_output_dir, delete_all_gurobi_solutions


def main():
    # ------- User defined inputs
    MODEL_NAME = "dummy_trade"
    # The default simulation horizon T is 24 hours
    sim_horizon = 24
    # One year has 8760 hours. If T = 24, then we have 365 steps.
    # STEPS = math.floor(8760/T)
    STEPS = 3

    # Decide whether to save results
    SAVE_RESULT = config.get_saveresults()
    SAVE_PLOT = config.get_saveplots()
    to_reoperate = config.get_resreop()

    output_dir = get_output_dir()

    # We need a folder to store the figures
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    if STEP_BY_STEP:  # STEP_BY_STEP Version
        print("\n\n Running STEP_BY_STEP Version..........")
        for SIM_DAY in range(1, STEPS + 1):
            run_pownet(
                MODEL_NAME,
                T,
                STEPS,
                SIM_DAY,
                use_gurobi,
                to_reoperate,
                output_dir,
                SAVE_RESULT,
                SAVE_PLOT,
            )

    elif ONE_STEP:  # ONE_STEP Version
        print("\n\n Running ONE_STEP Version..........")
        SIM_DAY = config.get_simday()
        run_pownet(
            MODEL_NAME,
            T,
            STEPS,
            SIM_DAY,
            use_gurobi,
            to_reoperate,
            output_dir,
            SAVE_RESULT,
            SAVE_PLOT,
        )

    else:  # ALL_STEPS Version
        print("\n\n Running ALL_STEPS Version..........")
        SIM_DAY = STEPS
        run_pownet(
            MODEL_NAME,
            T,
            STEPS,
            SIM_DAY,
            use_gurobi,
            to_reoperate,
            output_dir,
            SAVE_RESULT,
            SAVE_PLOT,
        )


def run_pownet(
    MODEL_NAME,
    T,
    STEPS,
    SIM_DAY,
    use_gurobi,
    to_reoperate,
    output_dir,
    SAVE_RESULT,
    SAVE_PLOT,
):

    time_start = datetime.now()

    simulator = Simulator(
        model_name=MODEL_NAME,
        T=sim_horizon,
        to_reoperate=to_reoperate,
    )

    record = simulator.run(steps=STEPS)

    if SAVE_RESULT:
        record.to_csv()

    print("\n\n====")
    print(f"PowNet: Solved {MODEL_NAME}")
    print(
        f"PowNet: Total time (s) = {round((datetime.now() - time_start).total_seconds(), 2)}"
    )
    print(f"PowNet: Opt.time (s) = {round(sum(simulator_run.runtimes), 2)}")

    # 5) Save PowNet Results
    if SAVE_RESULT:
        simulator_run.to_csv()

    # Export reservoir outputs as csv
    if to_reoperate:
        simulator.export_reservoir_outputs()

    node_variables = record.get_node_variables()

    system_input = simulator.get_system_input()
    output_processor = OutputProcessor()
    output_processor.load(
        df=node_variables, system_input=system_input, model_name=MODEL_NAME
    )

    visualizer = Visualizer(model_name=MODEL_NAME, ctime=output_processor.ctime)

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
        visualizer.plot_fuelmix_area(
            dispatch=output_processor.get_total_dispatch(),
            demand=output_processor.get_total_demand(),
            to_save=SAVE_PLOT,
        )
    else:
        visualizer.plot_fuelmix_area(
            dispatch=output_processor.get_monthly_dispatch(),
            demand=output_processor.get_monthly_demand(),
            to_save=SAVE_PLOT,
        )


if __name__ == "__main__":
    main()
