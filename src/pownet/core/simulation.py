"""simulation.py: Main class to run the simulation of the power system model"""

import pandas as pd
from pownet.data_utils import (
    create_init_condition,
)
from .model_builder import ModelBuilder
from .data_processor import DataProcessor
from ..input import SystemInput
from .output import OutputProcessor
from .record import SystemRecord
from .visualizer import Visualizer


class Simulator:
    """Main class to run the simulation of the power system model"""

    def __init__(
        self,
        input_folder: str,
        model_name: str,
        model_year: int,
        frequency: int = 50,
        use_spin_var: bool = True,
        dc_opf: str = "kirchhoff",
        spin_reserve_factor: float = 0.15,
        spin_reserve_mw: float = None,
        line_loss_factor: float = 0.075,
        line_capacity_factor: float = 0.9,
        load_shortfall_penalty_factor: float = 1000,
        load_curtail_penalty_factor: float = 10,
        spin_shortfall_penalty_factor: float = 1000,
    ) -> None:
        """Initialize the simulation parameters

        Args:
            input_folder (str): The folder containing the input data.
            model_name (str): The name of the model.
            model_year (int): The year of the model.
            frequency (int): The frequency of the power system model.
            use_spin_var (bool): Whether to use spinning reserve.
            dc_opf (str): The type of DC OPF to use.
            spin_reserve_factor (float): The spinning reserve factor.
            line_loss_factor (float): The line loss factor.
            line_capacity_factor (float): The line capacity factor.
            load_shortfall_penalty_factor (float): The load shortfall penalty factor.
            load_curtail_penalty_factor (float): The load curtailment penalty factor.
            spin_shortfall_penalty_factor (float): The spinning reserve shortfall penalty factor.

        Returns:
            None
        """

        self.input_folder: str = input_folder
        self.model_name: str = model_name
        self.model_year: int = model_year

        self.frequency: int = frequency
        self.use_spin_var: bool = use_spin_var
        self.dc_opf: str = dc_opf
        self.spin_reserve_factor: float = spin_reserve_factor
        self.spin_reserve_mw: float = spin_reserve_mw
        self.line_loss_factor: float = line_loss_factor
        self.line_capacity_factor: float = line_capacity_factor
        self.load_shortfall_penalty_factor: float = load_shortfall_penalty_factor
        self.load_curtail_penalty_factor: float = load_curtail_penalty_factor
        self.spin_shortfall_penalty_factor: float = spin_shortfall_penalty_factor

        # Simulation objects
        self.inputs: SystemInput = None
        self.system_record: SystemRecord = None
        self.node_variables: pd.DataFrame = pd.DataFrame()

    def run(
        self,
        sim_horizon: int,
        steps_to_run: int,
        num_sim_days: int = 365,
        to_process_inputs: bool = True,
        solver: str = "gurobi",
        log_to_console: bool = True,
        mipgap: float = 1e-3,
        timelimit: int = 600,
        num_threads: int = 0,
        find_lmp: bool = False,
    ) -> SystemRecord:
        """Run the simulation of the power system model

        Args:
            sim_horizon (int): The simulation horizon in hours.
            steps_to_run (int): The number of steps to run the simulation.
            to_process_inputs (bool): Whether to process the input data.
            solver (str): The solver to use for optimization.
            log_to_console (bool): Whether to log the optimization output to the console.
            mipgap (float): The MIP gap for the optimization.
            timelimit (int): The time limit for the optimization in seconds.
            num_threads (int): The number of threads to use for optimization.
            find_lmp (bool): Whether to find the locational marginal prices.

        Returns:
            SystemRecord: The system record object containing the simulation results.
        """

        if steps_to_run is None:
            steps_to_run = num_sim_days - (sim_horizon // 24 - 1)

        # To create files with "pownet_" prefix
        if to_process_inputs:
            data_processor = DataProcessor(
                input_folder=self.input_folder,
                model_name=self.model_name,
                year=self.model_year,
                frequency=self.frequency,
            )
            data_processor.execute_data_pipeline()

        self.inputs = SystemInput(
            input_folder=self.input_folder,
            model_name=self.model_name,
            year=self.model_year,
            sim_horizon=sim_horizon,
            num_sim_days=num_sim_days,
            use_spin_var=self.use_spin_var,
            dc_opf=self.dc_opf,
            spin_reserve_factor=self.spin_reserve_factor,
            spin_reserve_mw=self.spin_reserve_mw,
            line_loss_factor=self.line_loss_factor,
            line_capacity_factor=self.line_capacity_factor,
            load_shortfall_penalty_factor=self.load_shortfall_penalty_factor,
            load_curtail_penalty_factor=self.load_curtail_penalty_factor,
            spin_shortfall_penalty_factor=self.spin_shortfall_penalty_factor,
        )
        # Produce an error if the data is not making sense
        self.inputs.load_and_check_data()

        ####################### Simulation
        self.system_record = SystemRecord(self.inputs)
        model_builder = ModelBuilder(self.inputs)

        # Initially, all thermal units are off. They have to be switched on from cold start
        init_conditions = create_init_condition(
            self.inputs.thermal_units, self.inputs.storage_units
        )

        for step_k in range(1, steps_to_run + 1):
            # Build or update the model
            if step_k == 1:
                power_system_model = model_builder.build(
                    step_k=step_k,
                    init_conds=init_conditions,
                )
            else:
                power_system_model = model_builder.update(
                    step_k=step_k,
                    init_conds=init_conditions,
                )
            # Optimization
            power_system_model.optimize(
                solver=solver,
                log_to_console=log_to_console,
                mipgap=mipgap,
                timelimit=timelimit,
                num_threads=num_threads,
            )
            self.system_record.keep(
                runtime=power_system_model.get_runtime(),
                objval=power_system_model.get_objval(),
                solution=power_system_model.get_solution(),
                step_k=step_k,
                lmp=power_system_model.solve_for_lmp() if find_lmp else None,
            )
            # Update the initial conditions for the next step
            init_conditions = self.system_record.get_init_conds()

    def get_node_variables(self) -> pd.DataFrame:
        """Return the node-specific variables."""
        return self.system_record.get_node_variables()

    def get_flow_variables(self) -> pd.DataFrame:
        """Return the flow variables."""
        return self.system_record.get_flow_variables()

    def get_systemwide_variables(self) -> pd.DataFrame:
        """Return the system variables"""
        return self.system_record.get_systemwide_variables()

    def write_results(self, output_folder: str) -> None:
        """Write the simulation results to files"""
        self.system_record.write_simulation_results(output_folder)

    def plot_fuelmix(self, chart_type: str, output_folder: str = None) -> None:
        """Plot the fuel mix of the power system

        Args:
            chart_type (str): The type of chart to plot. Choose between 'bar' and 'area'.
            output_folder (str): The folder to save the plot.

        Returns:
            None
        """
        if chart_type not in ["bar", "area"]:
            raise ValueError(
                "Invalid chart type. Choose between 'fuelmix' and 'fuelmix_area'."
            )

        output_processor = OutputProcessor()
        output_processor.load(self.inputs)

        node_variables = self.system_record.get_node_variables()

        visualizer = Visualizer(model_id=self.inputs.model_id)
        if chart_type == "bar":
            visualizer.plot_fuelmix_bar(
                dispatch=output_processor.get_hourly_generation(node_variables),
                demand=output_processor.get_hourly_demand(self.inputs.demand),
                output_folder=output_folder,
            )
        elif chart_type == "area":
            visualizer.plot_fuelmix_area(
                dispatch=output_processor.get_hourly_generation(node_variables),
                demand=output_processor.get_hourly_demand(self.inputs.demand),
                output_folder=output_folder,
            )

    def plot_thermal_units(self, output_folder: str = None) -> None:
        """Plot the status of the thermal units

        Args:
            output_folder (str): The folder to save the plot.

        Returns:
            None
        """
        node_variables = self.system_record.get_node_variables()

        output_processor = OutputProcessor()
        output_processor.load(self.inputs)

        visualizer = Visualizer(model_id=self.inputs.model_id)
        visualizer.plot_thermal_units(
            unit_status=output_processor.get_thermal_unit_hourly_status(node_variables),
            thermal_dispatch=output_processor.get_thermal_unit_hourly_dispatch(
                node_variables
            ),
            thermal_rated_capacity=self.inputs.thermal_rated_capacity,
            output_folder=output_folder,
        )

    def plot_lmp(self, output_folder: str = None) -> None:
        """Plot the locational marginal prices

        Args:
            output_folder (str): The folder to save the plot.

        Returns:
            None
        """
        visualizer = Visualizer(model_id=self.inputs.model_id)
        visualizer.plot_lmp(
            lmp_df=self.system_record.get_lmp(),
            output_folder=output_folder,
        )
