from datetime import datetime
import os

from pownet.core.simulation import Simulator
from pownet.folder_sys import get_output_dir


def main():
    # ------- User defined inputs
    MODEL_NAME = "dummy_hydro"
    # The default simulation horizon T is 24 hours
    T = 24
    # One year has 8760 hours. If T = 24, then we have 365 steps.
    # STEPS = math.floor(8760/T)
    STEPS = 365

    # Decide whether to save results
    SAVE_RESULT = True
    SAVE_PLOT = False

    to_reoperate = False

    #############################
    output_dir = get_output_dir()

    # We need a folder to store the figures
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # A user should create their own model in the model_library folder
    time_start = datetime.now()

    simulator = Simulator(
        model_name=MODEL_NAME,
        T=T,
        to_reoperate=to_reoperate,
        reop_timestep="hourly",
    )

    record = simulator.run(steps=STEPS)

    # if SAVE_RESULT:
    #     record.to_csv()

    print("\n\n====")
    print(f"PowNet: Solved {MODEL_NAME}")
    print(
        f"PowNet: Total time (s) = {round((datetime.now() - time_start).total_seconds(), 2)}"
    )

    if to_reoperate:
        print(f"PowNet: Reopt time (s) = {round(simulator.reop_opt_time, 2)}")

    print(f"PowNet: Opt.time (s) = {round(sum(record.runtimes), 2)}")

    # Export reservoir outputs as csv
    # if to_reoperate:
    #     simulator.export_reservoir_outputs()

    if to_reoperate:
        simulator.export_reop_iter()
    simulator.export_runtimes()


if __name__ == "__main__":
    main()
