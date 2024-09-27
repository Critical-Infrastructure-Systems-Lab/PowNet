from datetime import datetime
import pickle
import os
import re

import pandas as pd

from pownet.data_utils import (
    create_init_condition,
    get_current_time,
)
from pownet.core import ModelBuilder, SystemInput, SystemRecord
<<<<<<< HEAD
=======
from pownet.modeling import PowerSystemModel
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0
from pownet.core.record import (
    get_hydro_from_model,
    convert_to_daily_hydro,
)
from pownet.reservoir.reservoir import ReservoirOperator
<<<<<<< HEAD

import pownet.config as config
=======
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0
from pownet.folder_utils import get_output_dir


class Simulator:
    def __init__(
        self,
<<<<<<< HEAD
        system_input: SystemInput,
        write_model: bool = False,
        use_gurobi: bool = False,
=======
        inputs: SystemInput,
        use_gurobi: bool = True,
        write_model: bool = False,
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0
        to_reoperate: bool = False,
        reop_timestep: str = "hourly",
    ) -> None:

<<<<<<< HEAD
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
        # self.system_input = SystemInput(
        #     T=T, formulation="kirchhoff", model_name=model_name
        # )

        self.model: gp.Model = None
=======
        self.use_gurobi = use_gurobi
        self.write_model = write_model
        self.to_reoperate = to_reoperate
        self.reop_timestep = reop_timestep

        self.model: PowerSystemModel = None
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0

        # Statistics
        self.wallclock_times: float = []  # Total runtime of each instance

    def create_hydropower_csv(self):
        self.reservoir_operator = ReservoirOperator(self.model_name, num_days=365)
        self.reservoir_operator.simulate()
        self.reservoir_operator.export_hydropower_csv(timestep=reop_timestep)

    def run(
        self,
        steps: int,
<<<<<<< HEAD
        init_conds,
        simulated_day,
        mip_gap: float = None,
        timelimit: float = None,
=======
        solver: str = "gurobi",
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0
    ) -> SystemRecord:
        # Initialize objects
        system_record = SystemRecord(self.system_input)
        builder = ModelBuilder(self.system_input)

        # The indexing of 'k' starts at zero because we use this to
        # index the parameters of future simulation periods (t + self.k*self.T)
        # Need to ensure that steps is a multiple of T
        STEP_BY_STEP = config.get_stepbystep()
        ONE_STEP = config.get_onestep()

        if STEP_BY_STEP or ONE_STEP:
            steps_to_run = 1
        else:
            steps_to_run = min(steps, 365 * 24 // self.T)

        for k in range(0, steps_to_run):
            # Create a gurobipy model for each simulation period
            if STEP_BY_STEP or ONE_STEP:
                simulated_step = simulated_day
            else:
                simulated_step = k
            print("\n\n\n============")
            print(f"PowNet: Simulate step {k+1}\n\n")

            k_timer = datetime.now()

            if k == 0:
                self.model = builder.build(
                    k=simulated_step,
                    init_conds=init_conds,
                )
            else:
                self.model = builder.update(
                    k=simulated_step,
                    init_conds=init_conds,
                )

            if self.write_model:
<<<<<<< HEAD
                # Save the model
                dirname = os.path.join(
                    get_output_dir(), f"{self.model_name}_{self.T}_instances"
                )
                if not os.path.exists(dirname):
                    os.makedirs(dirname)
                self.model.write(
                    os.path.join(dirname, f"{self.model_name}_{simulated_step}.mps")
                )
=======
                output_folder = get_output_dir()
                filename = f"{self.model_name}_{self.T}_{k}"
                self.model.write_mps(output_folder=output_folder, filename=filename)
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0

            # Solve the model with either Gurobi or HiGHs
            # TODO: Set mipgap, timelimit, log_to_console as arguments
            self.model.optimize(solver=solver)

            # In case when the model is infeasible, we generate ILP and MPS files
            # to describe the problem instance.
            if not self.model.check_feasible():
                output_folder_infeasible = "infeasible"
                if not os.path.exists(output_folder_infeasible):
                    os.makedirs(output_folder_infeasible)

<<<<<<< HEAD
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
=======
                self.model.write_ilp_mps(
                    output_folder=output_folder_infeasible,
                    instance_name=f"{self.model_name}_{self.T}_{k}",
                )
                # Need to learn about the initial conditions as well
                with open(
                    os.path.join(
                        get_output_dir(),
                        f"infeasible_{self.model_name}_{self.T}_{k}.pkl",
                    ),
                    "wb",
                ) as f:
                    pickle.dump(system_record, f)
                break
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0

            # Reoperate reservoirs
            if self.to_reoperate:
                self.reoperate(k, builder, init_conds, mipgap, timelimit)

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
            hydro_dispatch, start_day, end_day = get_hydro_from_model(
                self.model.model, k
            )
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
            self.reop_opt_time += self.model.get_runtime()
            reop_k += 1

        # Record the number of iterations after convergence
        self.reop_iter.append(reop_k)

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
