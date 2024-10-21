import os
from pownet.core import Simulator


def main():

    # --------- User inputs

    input_folder = "model_library"
    model_name = "dummy"
    model_year = 2016

    # System parameters
    dc_opf = "kirchhoff"
    spin_reserve_factor = 0.15
    line_loss_factor = 0.075
    line_capacity_factor = 0.9
    load_shortfall_penalty_factor = 1000
    load_curtail_penalty_factor = 10
    spin_shortfall_penalty_factor = 1000

    # Simulation parameters
    sim_horizon = 24
    steps_to_run = 2  # 365 - (sim_horizon // 24 - 1)
    to_process_inputs = True
    solver = "gurobi"
    log_to_console = True
    find_lmp = False

    # Outputs
    output_folder = "temptemp"

    # --------- End of user inputs

    # Run the simulation
    simulator = Simulator(
        input_folder=input_folder,
        model_name=model_name,
        model_year=model_year,
        dc_opf=dc_opf,
        spin_reserve_factor=spin_reserve_factor,
        line_loss_factor=line_loss_factor,
        line_capacity_factor=line_capacity_factor,
        load_shortfall_penalty_factor=load_shortfall_penalty_factor,
        load_curtail_penalty_factor=load_curtail_penalty_factor,
        spin_shortfall_penalty_factor=spin_shortfall_penalty_factor,
    )

    simulator.run(
        sim_horizon=sim_horizon,
        steps_to_run=steps_to_run,
        to_process_inputs=to_process_inputs,
        solver=solver,
        log_to_console=log_to_console,
        find_lmp=find_lmp,
    )

    # Write the simulation results
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    simulator.write_results(output_folder)

    # Plot the results
    simulator.plot_fuelmix("bar", output_folder)
    # simulator.plot_unit_status(output_folder)

    if find_lmp:
        simulator.plot_lmp(output_folder)


if __name__ == "__main__":
    main()
