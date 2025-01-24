""" This script provides an example of how to run PowNet 2.0.
"""

import os
from pownet.core import Simulator


def main():

    # --------- User inputs

    input_folder = "..//model_library"
    output_folder = "..//temptemp"

    model_name = "solar_ess"
    model_year = 2016

    # Simulation parameters
    sim_horizon = 24
    steps_to_run = 2
    solver = "gurobi"  # or highs

    # --------- End of user inputs

    # Run the simulation
    simulator = Simulator(
        input_folder=input_folder,
        model_name=model_name,
        model_year=model_year,
    )

    simulator.run(
        sim_horizon=sim_horizon,
        steps_to_run=steps_to_run,
        solver=solver,
    )

    # Write the simulation results
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    simulator.write_results(output_folder)

    # Plot the results
    simulator.plot_fuelmix("bar", output_folder)
    simulator.plot_thermal_units(output_folder)


if __name__ == "__main__":
    main()
