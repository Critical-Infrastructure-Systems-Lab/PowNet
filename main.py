from datetime import datetime
import os

from pownet.config import is_warmstart
from pownet.core.input import SystemInput
from pownet.core.simulation import Simulator
from pownet.core.output import OutputProcessor, Visualizer
from pownet.folder_sys import get_output_dir, delete_all_gurobi_solutions


def main():
    # ------- User defined inputs
    MODEL_NAME = 'dummy_trade'
    # The default simulation horizon T is 24 hours
    T = 24
    # One year has 8760 hours. If T = 24, then we have 365 steps.
    # STEPS = math.floor(8760/T)
    STEPS = 2

    # Decide whether to save results
    SAVE_RESULT = False
    SAVE_PLOT = False

    #############################
    output_dir = get_output_dir()

    # We need a folder to store the figures
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # The user should create their own model in the model_library folder
    time_start = datetime.now()

    system_input = SystemInput(
        T=T,
        formulation='kirchhoff',
        model_name=MODEL_NAME
    )

    simulator = Simulator(
        system_input=system_input,
        use_gurobi=False
        )

    record = simulator.run(steps=STEPS)

    if SAVE_RESULT:
        record.to_csv()

    print("\n\n====")
    print(f"PowNet: Solved {MODEL_NAME}")
    print(
        f"PowNet: Total time (s) = {round((datetime.now() - time_start).total_seconds(), 2)}"
    )
    print(f"PowNet: Opt.time (s) = {round(sum(record.runtimes), 2)}")

    node_variables = record.get_node_variables()

    output_processor = OutputProcessor()
    output_processor.load(
        df=node_variables, system_input=system_input, model_name=MODEL_NAME
    )

    visualizer = Visualizer(model_name=MODEL_NAME,
                            ctime=output_processor.ctime)
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


if __name__ == '__main__':
    main()