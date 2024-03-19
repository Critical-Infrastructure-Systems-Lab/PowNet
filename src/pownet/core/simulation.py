import pickle
import os

import highspy

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
        use_gurobi: bool = True,
    ) -> None:

        self.model = None
        self.use_gurobi = use_gurobi

        self.system_input = system_input
        self.T = self.system_input.T

        self.model_name = system_input.model_name
        self.write_model = write_model

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

            # Need k to increment the hours field
            system_record.keep(self.model, k)
            init_conds = system_record.get_init_conds()

        return system_record
