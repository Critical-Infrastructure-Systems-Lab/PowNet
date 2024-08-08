from datetime import datetime
import os

from pownet.simulation import Simulator
from pownet.core import Visualizer, OutputProcessor
from pownet.folder_utils import get_output_dir


def main():
    # ------- User defined inputs
    MODEL_NAME = "dummy_trade"
    # The default simulation horizon T is 24 hours
    T = 24
    # One year has 8760 hours. If T = 24, then we have 365 steps.
    # STEPS = math.floor(8760/T)
    STEPS = 1

    to_reoperate = False
    reop_timestep = "daily"

    save_result = False

    #############################
    output_dir = get_output_dir()

    # We need a folder to store the figures
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # A user should create their own model in the model_library folder
    time_start = datetime.now()

    simulator = Simulator(
        model_name=MODEL_NAME,
        use_gurobi=True,
        T=T,
        to_reoperate=to_reoperate,
        reop_timestep=reop_timestep,
    )

    record = simulator.run(steps=STEPS, solver="highs")
    results = record.get_node_variables()

    if save_result:
        record.to_csv()

    print("\n\n====")
    print(f"PowNet: Solved {MODEL_NAME}")
    print(
        f"PowNet: Total time (s) = {round((datetime.now() - time_start).total_seconds(), 2)}"
    )

    if to_reoperate:
        print(f"PowNet: Reopt time (s) = {round(simulator.reop_opt_time, 2)}")

    print(f"PowNet: Opt.time (s) = {round(sum(record.runtimes), 2)}")

    # Export reservoir outputs as csv
    if to_reoperate:
        simulator.export_reservoir_outputs()

    if to_reoperate:
        simulator.export_reop_iter()
    simulator.export_runtimes()

    # Plot the results
    output_processor = OutputProcessor()
    output_processor.load(results, simulator.system_input)

    visualizer = Visualizer(model_name=MODEL_NAME, ctime=output_processor.ctime)
    visualizer.plot_fuelmix_area(
        dispatch=output_processor.get_total_dispatch()[: 24 * 3],
        demand=output_processor.get_total_demand()[: 24 * 3],
        to_save=False,
    )

    nodal_prices = simulator.model.get_lmp()
    model = simulator.model.model


if __name__ == "__main__":
    main()
