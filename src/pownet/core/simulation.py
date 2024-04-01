import pickle
import os

from pownet.core.builder import ModelBuilder
from pownet.core.input import SystemInput
from pownet.core.record import SystemRecord
from pownet.processing.functions import (
    create_init_condition,
    get_current_time,
)
from pownet.config import is_warmstart
from pownet.folder_sys import get_output_dir


class Simulator:
    def __init__(
        self,
        system_input: SystemInput,
        write_model: bool = False,
    ) -> None:
        self.model = None

        self.system_input = system_input
        self.T = self.system_input.T

        self.model_name = system_input.model_name
        self.write_model = write_model

    def _check_infeasibility(self, k) -> bool:
        '''
        Check if the model is infeasible. If it is, generate an output file.'''
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
        self, steps: int, mip_gap: float = None, timelimit: float = None
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
                self.model.write(os.path.join(
                    dirname, f"{self.model_name}_{k}.mps"))

            # Once the model has been optimized, first check if it is infeasible.
            # After that, we can reoperate the reservoirs
            self.model.optimize()
            # In case when the model is infeasible, we generate an output file
            # and exit the simulation. The model should always be feasible.
            if self._check_infeasibility(k):
                break

            # Save the solution file to warmstart the next instance
            if is_warmstart():
                self.model.write(
                    os.path.join(
                        get_output_dir(), f"{self.model_name}_{self.T}_{k}.sol"
                    )
                )

            '''
            TODO: Reoperate the reservoirs
            1. Get hydropower dispatch from the model
            2. Check if the hydropower was fully used per Koh et al. (2022)
            '''
            # ---- Begin reoperation of the reservoirs
            hydro_dispatch = system_record.get_hydro_from_model(
                self.model)

            # The model has been solved to optimality, so we can record the solution.
            # We need k to increment the hours field when building an instance of
            # the next timestep.
            system_record.keep(self.model, k)
            init_conds = system_record.get_init_conds()

        return system_record
