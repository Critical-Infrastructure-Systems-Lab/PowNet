"""coupler.py: PowerWaterCoupler class to couple the power and water systems."""

from .core import ModelBuilder
from .reservoir.manager import ReservoirManager

import logging

logger = logging.getLogger(__name__)


class PowerWaterCoupler:
    def __init__(
        self,
        model_builder: ModelBuilder,
        reservoir_manager: ReservoirManager,
        solver: str = "gurobi",
        mip_gap: float = 0.0001,
        timelimit: float = 600,
        log_to_console: bool = False,
    ) -> None:
        """
        Coupler class to couple the power and water systems.

        Args:
            model_builder (ModelBuilder): ModelBuilder object to build the power system model.
            reservoir_manager (ReservoirManager): ReservoirManager object to manage the water system.
            solver (str): Solver to use for optimization. Default is "gurobi".
            mip_gap (float): MIP gap for optimization. Default is 0.0001.
            timelimit (float): Time limit for optimization in seconds. Default is 600.
            log_to_console (bool): Whether to log to console. Default is False.

        Returns:
            None
        """
        self.model_builder = model_builder
        self.reservoir_manager = reservoir_manager

        self.solver = solver
        self.mipgap = mip_gap
        self.timelimit = timelimit
        self.log_to_console = log_to_console

        self.num_days_in_step = self.model_builder.inputs.sim_horizon // 24

        self.reop_iter = []
        self.reop_opt_time = 0.0

    def get_reop_opt_time(self):
        return self.reop_opt_time

    def get_reop_iter(self):
        return self.reop_iter

    def reoperate(
        self,
        step_k: int,
        max_reop_iter: int = 100,
    ) -> None:
        """Reoperate the reservoirs based on the daily dispatch of the power system model.
        Note that we don't reoperate on the first day of the simulation period.

        Args:
            step_k (int): Current step in the simulation.

        Returns:
            None
        """

        # Assume optimization is rolling horizon of 24 hours
        days_in_step = range(step_k, step_k + self.num_days_in_step)

        reop_converge = False
        reop_k = 0

        while not reop_converge:
            # --- PowNet returns the hydropower dispatch in hourly resolution across the simulation horizon
            hydropower_dispatch = {
                (unit, day): 0
                for unit in self.reservoir_manager.simulation_order
                for day in days_in_step
            }
            for varname, var in self.model_builder.get_phydro().items():
                unit = varname[0]

                if varname[1] % 24 == 0:
                    current_day = varname[1] // 24 + step_k - 1
                else:
                    current_day = varname[1] // 24 + step_k

                hydropower_dispatch[unit, current_day] += var.X

            # --- Reoperate the reservoirs
            proposed_capacity = self.reservoir_manager.reoperate(
                daily_dispatch=hydropower_dispatch,
                days_in_step=days_in_step,
            )

            # --- Iterate the reoperation process
            # Compare the new hydropower capacity with the current dispatch
            max_deviation = {
                (unit, day): abs(
                    proposed_capacity[unit, day] - hydropower_dispatch[unit, day]
                )
                for unit in self.reservoir_manager.simulation_order
                for day in days_in_step
            }

            # Set the tolerance for convergence to 5%
            reop_tol = {
                (unit, day): 0.05 * hydropower_dispatch[unit, day]
                for unit, day in max_deviation.keys()
            }

            if all(
                max_deviation[unit, day] <= reop_tol[unit, day]
                for unit in self.reservoir_manager.simulation_order
                for day in days_in_step
            ):
                reop_converge = True
                logger.info(
                    f"PowNet: Day {step_k + 1} - Reservoirs converged at iteration {reop_k}"
                )

            logger.info("Max deviations:", max_deviation)

            if reop_k > max_reop_iter:
                raise ValueError(
                    f"Reservoirs reoperation did not converge after {max_reop_iter} iterations"
                )

            # To reoptimize PowNet with the new hydropower capacity,
            # update the builder class
            power_system_model = self.model_builder.update_daily_hydropower_capacity(
                step_k=step_k, new_capacity=proposed_capacity
            )
            power_system_model.optimize(
                solver=self.solver,
                mipgap=self.mipgap,
                timelimit=self.timelimit,
                log_to_console=self.log_to_console,
            )

            # Keep track of optimization time oand reoperation iterations
            self.reop_opt_time += power_system_model.get_runtime()
            reop_k += 1

        # Record the number of iterations after convergence
        self.reop_iter.append(reop_k)
