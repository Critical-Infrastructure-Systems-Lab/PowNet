from datetime import datetime
import pickle
import os
import re

import pandas as pd
import gurobipy as gp
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
import pownet.config as config

class Simulator:
    def __init__(
        self,
        system_input: SystemInput,
        model_name: str,
        T: int,
        write_model: bool = False,
        use_gurobi: bool = True,
        to_reoperate: bool = False,
        reop_timestep: str = "hourly",
    ) -> None:

        self.system_input = system_input
        self.model_name = system_input.model_name
        self.T = system_input.T
        self.write_model = write_model
        self.use_gurobi = use_gurobi
        
        self.to_reoperate = to_reoperate
        self.reop_timestep = reop_timestep

        # Simulate reservoir operation based on provided rule curve to get pownet_hydropower.csv
        if self.to_reoperate:
            self.reservoir_operator = ReservoirOperator(model_name, num_days=365)
            self.reservoir_operator.simulate()
            self.reservoir_operator.export_hydropower_csv(timestep=reop_timestep)

        # Extract model parameters from the model library directory
        self.system_input = SystemInput(
            T=T, formulation="kirchhoff", model_name=model_name
        )

        self.model: gp.Model = None

        # Statistics
        self.runtimes: float = []  # Total runtime of each instance
        self.reop_iter: int = []  # Number of reoperation iterations
        self.reop_opt_time: float = 0  # Total runtime of reoperation

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
        init_conds, 
        simulated_day,
        mip_gap: float = None,
        timelimit: float = None,
    ) -> SystemRecord:
        # Initialize objects
        system_record = SystemRecord(self.system_input)
        builder = ModelBuilder(self.system_input)

        

        # The indexing of 'k' starts at zero because we use this to
        # index the parameters of future simulation periods (t + self.k*self.T)
        # Need to ensure that steps is a multiple of T
        STEP_BY_STEP=config.get_stepbystep()
        ONE_STEP=config.get_onestep()

        if STEP_BY_STEP or ONE_STEP:
            steps_to_run=1
        else:
            steps_to_run = min(steps, 365 * 24 // self.T)
            
        for k in range(0, steps_to_run):
            # Create a gurobipy model for each simulation period
            if STEP_BY_STEP or ONE_STEP:
                simulated_step=simulated_day
            else:
                simulated_step=k
            print("\n\n\n============")
            print(f"PowNet: Simulate step {k+1}\n\n")
            
            k_timer = datetime.now()

            if k == 0:
                self.model = builder.build(
                    k=simulated_step,
                    init_conds=init_conds,
                    mip_gap=mip_gap,
                    timelimit=timelimit,
                )
            else:
                self.model = builder.update(
                    k=simulated_step,
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
                self.model.write(os.path.join(dirname, f"{self.model_name}_{simulated_step}.mps"))

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
                    print(f"PowNet: Iteration: {simulated_step} is infeasible.")
                    self.model.computeIIS()
                    c_time = get_current_time()
                    ilp_file = os.path.join(
                        get_output_dir(),
                        f"infeasible_{self.model_name}_{self.T}_{simulated_step}_{c_time}.ilp",
                    )
                    self.model.write(ilp_file)

                    mps_file = os.path.join(
                        get_output_dir(),
                        f"infeasible_{self.model_name}_{self.T}_{simulated_step}_{c_time}.mps",
                    )
                    self.model.write(mps_file)

                    # Need to learn about the initial conditions as well
                    with open(
                        os.path.join(
                            get_output_dir(),
                            f"infeasible_{self.model_name}_{self.T}_{simulated_step}_{c_time}.pkl",
                        ),
                        "wb",
                    ) as f:
                        pickle.dump(system_record, f)
                    break

            # Reoperate reservoirs
            if self.to_reoperate:
                self.reoperate(k, builder, init_conds, mip_gap, timelimit)

            # Need k to increment the hours field
            system_record.keep(self.model, simulated_step)
            init_conds = system_record.get_init_conds()

            # Record the runtime
            self.runtimes.append((datetime.now() - k_timer).total_seconds())

        return system_record

    def reoperate(
        self,
        k: int,
        builder: ModelBuilder,
        init_conds: dict,
        mip_gap: float = None,
        timelimit: float = None,
    ):
        reop_converge = False
        reop_k = 0
        while not reop_converge:
            print(f"\nReservoirs reoperation iteration {reop_k}")
            print("New Capacity vs. Current Dispatch")

            # PowNet returns the hydropower dispatch in hourly resolution across the simulation horizon
            hydro_dispatch, start_day, end_day = get_hydro_from_model(self.model, k)
            # Convert to daily dispatch
            hydro_dispatch = convert_to_daily_hydro(hydro_dispatch, start_day, end_day)
            new_hydro_capacity = self.reservoir_operator.reoperate_basins(
                pownet_dispatch=hydro_dispatch
            )

            for res in new_hydro_capacity.columns:
                print(
                    f"{res}: {round(new_hydro_capacity[res].sum(),2)} vs {round(hydro_dispatch[res].sum(),2)}",
                )

            max_deviation = (new_hydro_capacity - hydro_dispatch).abs().max()
            # The tolerance for convergence should be 5% of the largest hydro capacity
            reop_tol = 0.05 * new_hydro_capacity.max()
            if (max_deviation <= reop_tol[max_deviation.index]).all():
                reop_converge = True
                print(f"PowNet: Day {k+1} - Reservoirs converged at iteration {reop_k}")

            if reop_k > 50:
                raise ValueError(
                    "Reservoirs reoperation did not converge after 100 iterations"
                )

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

            # Keep track of optimization time oand reoperation iterations
            self.reop_opt_time += self.model.runtime
            reop_k += 1

        # Record the number of iterations after convergence
        self.reop_iter.append(reop_k)

    def get_system_input(self):
        return self.system_input

    def export_reservoir_outputs(self):
        return self.reservoir_operator.export_reservoir_outputs()

    def export_reop_iter(self):
        ctime = datetime.now().strftime("%Y%m%d_%H%M")
        df = pd.Series(self.reop_iter)
        df.to_csv(
            os.path.join(
                get_output_dir(),
                f"{ctime}_{self.model_name}_{self.T}_reop_iters.csv",
            )
        )

    def export_runtimes(self):
        ctime = datetime.now().strftime("%Y%m%d_%H%M")
        df = pd.Series(self.runtimes)
        df.to_csv(
            os.path.join(
                get_output_dir(),
                f"{ctime}_{self.model_name}_{self.T}_runtimes.csv",
            )
        )
