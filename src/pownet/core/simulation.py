import pickle
import os
import re

import pandas as pd
import highspy

from pownet.core.builder import ModelBuilder
from pownet.core.input import SystemInput
from pownet.core.record import (
    SystemRecord,
    get_hydro_from_model,
    convert_to_daily_hydro,
)
from pownet.reservoir.reservoir import ReservoirOperator
from pownet.processing.functions import (
    create_init_condition,
    get_current_time,
)
from pownet.folder_sys import get_output_dir


class Simulator:
    def __init__(
        self,
        model_name: str,
        T: int,
        hydro_timestep: str = "hourly",
        write_model: bool = False,
        use_gurobi: bool = True,
        to_reoperate: bool = False,
    ) -> None:

        self.model_name = model_name
        self.T = T
        self.hydro_timestep = hydro_timestep
        self.write_model = write_model
        self.use_gurobi = use_gurobi
        self.to_reoperate = to_reoperate

        # Simulate reservoir operation based on provided rule curve to get pownet_hydropower.csv
        if self.to_reoperate:
            self.reservoir_operator = ReservoirOperator(model_name, num_days=365)
            self.reservoir_operator.simulate()
            self.reservoir_operator.get_hydropower()
            self.reservoir_operator.export_hydropower_csv(timestep=hydro_timestep)

        # Extract model parameters from the model library directory
        self.system_input = SystemInput(
            T=T, formulation="kirchhoff", model_name=model_name
        )

        self.model = None

    def _check_infeasibility(self, k) -> bool:
        """
        Check if the model is infeasible. If it is, generate an output file."""
        is_infeasible = self.model.status == 3
        if is_infeasible == 3:
            print(f"PowNet: Iteration: {k} is infeasible.")
            self.model.computeIIS()
            c_time = get_current_time()
            ilp_file = os.path.join(
                get_output_dir(),
                f"infeasible_{self.model_name}_{self.T}_{k}_{c_time}.ilp",
            )
            self.model.write(ilp_file)

            mps_file = os.path.join(
                get_output_dir(),
                f"infeasible_{self.model_name}_{self.T}_{k}_{c_time}.mps",
            )
            self.model.write(mps_file)

            # Need to learn about the initial conditions as well
            with open(
                os.path.join(
                    get_output_dir(),
                    f"infeasible_{self.model_name}_{self.T}_{k}_{c_time}.pkl",
                ),
                "wb",
            ) as f:
                pickle.dump(system_record, f)
        return is_infeasible

    def run(
        self,
        steps: int,
        mip_gap: float = None,
        timelimit: float = None,
    ) -> SystemRecord:
        # Initialize objects
        system_record = SystemRecord(self.system_input)
        builder = ModelBuilder(self.system_input)

        # Initially, we can define the initial conditions
        init_conds = create_init_condition(
            thermal_units=self.system_input.thermal_units, T=self.T
        )

        # The indexing of 'k' starts at zero because we use this to
        # index the parameters of future simulation periods (t + self.k*self.T)
        # Need to ensure that steps is a multiple of T
        steps_to_run = min(steps, 365 * 24 // self.T)

        for k in range(0, steps_to_run):
            # Create a gurobipy model for each simulation period
            print("\n\n\n============")
            print(f"PowNet: Simulate step {k+1}\n\n")

            if k == 0:
                self.model = builder.build(
                    k=k,
                    init_conds=init_conds,
                    mip_gap=mip_gap,
                    timelimit=timelimit,
                )
            else:
                self.model = builder.update(
                    k=k,
                    init_conds=init_conds,
                    mip_gap=mip_gap,
                    timelimit=timelimit,
                )

            # We can write the model as .MPS and use non-Gurobi solvers
            if self.write_model:
                # Save the model
                dirname = os.path.join(
                    get_output_dir(), f"{self.model_name}_{self.T}_instances"
                )
                if not os.path.exists(dirname):
                    os.makedirs(dirname)
                self.model.write(os.path.join(dirname, f"{self.model_name}_{k}.mps"))

            # Solve the model with either Gurobi or HiGHs
            if self.use_gurobi:
                self.model.optimize()

            else:
                # Export the instance to MPS and solve with HiGHs
                mps_file = "temp_instance_for_HiGHs.mps"
                self.model.write(mps_file)

                self.model = highspy.Highs()
                self.model.readModel(mps_file)
                self.model.run()

                # Delete the MPS file
                os.remove(mps_file)

            # In case when the model is infeasible, we generate an output file
            # to troubleshoot the problem. The model should always be feasible.
            if self.use_gurobi:
                if self.model.status == 3:
                    print(f"PowNet: Iteration: {k} is infeasible.")
                    self.model.computeIIS()
                    c_time = get_current_time()
                    ilp_file = os.path.join(
                        get_output_dir(),
                        f"infeasible_{self.model_name}_{self.T}_{k}_{c_time}.ilp",
                    )
                    self.model.write(ilp_file)

                    mps_file = os.path.join(
                        get_output_dir(),
                        f"infeasible_{self.model_name}_{self.T}_{k}_{c_time}.mps",
                    )
                    self.model.write(mps_file)

                    # Need to learn about the initial conditions as well
                    with open(
                        os.path.join(
                            get_output_dir(),
                            f"infeasible_{self.model_name}_{self.T}_{k}_{c_time}.pkl",
                        ),
                        "wb",
                    ) as f:
                        pickle.dump(system_record, f)
                    break

            # Reoperate reservoirs
            if self.to_reoperate:
                reop_converge = False
                reop_k = 0
                # If we are at the first timestep, then we do not reoperate
                while not reop_converge:
                    print(f"\nReservoirs reoperation iteration {reop_k}")
                    # PowNet returns the hydropower dispatch in hourly resolution
                    hydro_dispatch, start_day, end_day = get_hydro_from_model(
                        self.model, k
                    )
                    # Convert to daily dispatch
                    hydro_dispatch = convert_to_daily_hydro(
                        hydro_dispatch, start_day, end_day
                    )
                    # Use PowNet to reoperate the reservoirs
                    new_hydro_capacity = self.reservoir_operator.reoperate_basins(
                        pownet_dispatch=hydro_dispatch
                    )
                    for res in new_hydro_capacity.columns:
                        print(
                            f"{res}: {round(new_hydro_capacity[res].sum(),2)} vs {round(hydro_dispatch[res].sum(),2)}",
                        )

                    # Terminate the loop if the reservoirs have converged when difference is less than 1MW-day
                    max_deviation = (new_hydro_capacity - hydro_dispatch).abs().max()
                    # The tolerance for convergence should be 5% of the largest hydro capacity
                    reop_tol = 0.05 * new_hydro_capacity.max()
                    if (max_deviation <= reop_tol[max_deviation.index]).all():
                        reop_converge = True
                        print(
                            f"PowNet: Day {k+1} - Reservoirs converged at iteration {reop_k}"
                        )
                        break

                    # To reoptimize PowNet with the new hydropower capacity,
                    # update the builder class
                    builder.update_hydro_capacity(new_hydro_capacity)
                    self.model = builder.update(
                        k=k,
                        init_conds=init_conds,
                        mip_gap=mip_gap,
                        timelimit=timelimit,
                    )
                    self.model.optimize()
                    reop_k += 1

            # Need k to increment the hours field
            system_record.keep(self.model, k)
            init_conds = system_record.get_init_conds()

        return system_record

    def get_system_input(self):
        return self.system_input
