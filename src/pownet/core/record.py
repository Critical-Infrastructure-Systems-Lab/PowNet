"""record.py: The SystemRecord class processes stores the modeling outputs from each iteration.
TODO: self.current_hydro, self.current_import for model coupling
"""

import json
import pandas as pd

from ..input import SystemInput
from pownet.data_utils import (
    parse_node_variables,
    parse_flow_variables,
    parse_syswide_variables,
    parse_lmp,
    calc_remaining_on_duration,
    calc_remaining_off_duration,
    write_df,
)


class SystemRecord:
    """This class stores modeling outputs from each iteration. The results are stored
    in three dataframes: node_vars, flow_vars, and syswide_vars. The initial conditions
    are also stored in the class.
    """

    def __init__(
        self,
        system_input: SystemInput,
        batch_mode: bool = True,
        keep_record_each_step: bool = False,
    ) -> None:
        """Initialize the SystemRecord object.
        Args:
            system_input (SystemInput): The input object containing the simulation parameters.
        """

        self.inputs: SystemInput = system_input
        self.batch_mode: bool = batch_mode
        self.keep_record_each_step: bool = keep_record_each_step

        if not batch_mode and not keep_record_each_step:
            print(
                '\nWarning: No data will be stored because both "batch_mode" and "keep_record_each_step" are False.'
            )

        # Format of variable name: var(node, t)
        self.node_vars: pd.DataFrame = pd.DataFrame()
        # Format of variable name: flow(node_a, node_b, t)
        self.flow_vars: pd.DataFrame = pd.DataFrame()
        # Format of variable name: var(t)
        self.syswide_vars: pd.DataFrame = pd.DataFrame()

        # Locational marginal prices (LMP)
        self.lmp_df: pd.DataFrame = pd.DataFrame()

        self.objvals: list = []
        self.runtimes: list = []

        # These are vpower, unit status, unit switching, etc.
        self.current_p: dict[str] = {}
        self.current_u: dict[str] = {}
        self.current_v: dict[str] = {}
        self.current_w: dict[str] = {}
        self.current_min_on: dict[str] = {}
        self.current_min_off: dict[str] = {}
        self.current_charge_state: dict[str] = {}

    def keep(
        self,
        runtime: float,
        objval: float,
        solution: pd.DataFrame,
        step_k: int,
        lmp: dict[str, float] = None,
    ) -> None:
        """Keep the simulation results at the current simulation period step_k.

        Args:
            runtime (float): The runtime of the model.
            objval (float): The objective value of the model.
            solution (pd.DataFrame): The solution dataframe from the model.
            step_k (int): The current simulation period.
            lmp (dict[str, float], optional): The locational marginal prices. Defaults to None.

        Returns:
            None
        """

        def _extract_vartype_data(df: pd.DataFrame, vartype: str) -> dict[str, float]:
            """Extracts data for a specific 'vartype' from the DataFrame and converts it to a dictionary."""
            return (
                df[
                    (df["vartype"] == vartype) & (df["timestep"] == 24)
                ]  # Only considers values of the last hour
                .drop("vartype", axis=1)
                .set_index(["node"])  # Assume generator names do not repeat
                .to_dict()["value"]
            )

        self.runtimes.append(runtime)
        self.objvals.append(objval)

        # Create a col of variable types for filtering
        pat_vartype = r"(\w+)\["
        solution[["vartype"]] = solution["varname"].str.extract(
            pat_vartype, expand=True
        )

        node_vars = parse_node_variables(solution, self.inputs.sim_horizon, step_k)
        # Only keep 24-hours as we are doing rolling horizon
        node_vars = node_vars[node_vars["timestep"] <= 24]
        ##################
        # Initial conditions: vpower (p), commitment (u),
        # startup (v), shutdown (w), and storage's charge_state
        ##################
        self.current_p = _extract_vartype_data(node_vars, "vpower")
        self.current_u = _extract_vartype_data(node_vars, "status")
        self.current_v = _extract_vartype_data(node_vars, "startup")
        self.current_w = _extract_vartype_data(node_vars, "shutdown")
        self.current_charge_state = _extract_vartype_data(node_vars, "charge_state")

        # Need to calculate the minimum time on/off
        self.current_min_on = calc_remaining_on_duration(
            node_vars,
            sim_horizon=24,
            thermal_units=self.inputs.thermal_units,
            TU=self.inputs.TU,
        )
        self.current_min_off = calc_remaining_off_duration(
            node_vars,
            sim_horizon=24,
            thermal_units=self.inputs.thermal_units,
            TD=self.inputs.TD,
        )

        ##################
        # Locational Marginal Prices (LMP)
        ##################
        if lmp is not None:
            self.lmp_df = pd.concat(
                [
                    self.lmp_df,
                    parse_lmp(lmp, self.inputs.sim_horizon, step_k).drop(
                        "timestep", axis=1
                    ),
                ],
                axis=0,
            )

        ##################
        # Append results to the existing dataframes in batch mode
        # otherwise, write to disk at each step_k if specified
        ##################
        # Keep outputs from the first 24-hr under rolling horizon for day-ahead planning
        node_vars = node_vars[node_vars["timestep"] <= 24]
        node_vars = node_vars.drop(["varname", "timestep"], axis=1)

        flow_vars = parse_flow_variables(
            solution=solution, sim_horizon=self.inputs.sim_horizon, step_k=step_k
        )
        flow_vars = flow_vars[flow_vars["timestep"] <= 24]
        flow_vars = flow_vars.drop("timestep", axis=1)

        syswide_vars = parse_syswide_variables(
            solution=solution, sim_horizon=self.inputs.sim_horizon, step_k=step_k
        )
        syswide_vars = syswide_vars[syswide_vars["timestep"] <= 24]
        syswide_vars = syswide_vars.drop("timestep", axis=1)

        if self.batch_mode:
            self.node_vars = pd.concat([self.node_vars, node_vars], axis=0)
            self.flow_vars = pd.concat([self.flow_vars, flow_vars], axis=0)
            self.syswide_vars = pd.concat([self.syswide_vars, syswide_vars], axis=0)

        if self.keep_record_each_step:
            output_folder = f"{self.inputs.model_id}_outputs"
            data_to_write = [
                (node_vars, f"node_variables_{step_k}"),
                (flow_vars, f"flow_variables_{step_k}"),
                (syswide_vars, f"system_variables_{step_k}"),
                (
                    pd.DataFrame({"objval": [objval], "runtime": [runtime]}),
                    f"model_stats_{step_k}",
                ),
            ]
            for df, output_name in data_to_write:
                write_df(
                    df,
                    output_folder=output_folder,
                    output_name=output_name,
                    model_id=self.inputs.model_id,  # Use model_name as the identifier
                )

    def get_init_conds(self) -> dict[str, dict]:
        """Return the initial conditions for the simulation."""
        return {
            "initial_p": self.current_p,
            "initial_u": self.current_u,
            "initial_v": self.current_v,
            "initial_w": self.current_w,
            "initial_min_on": self.current_min_on,
            "initial_min_off": self.current_min_off,
            "initial_charge_state": self.current_charge_state,
        }

    def write_init_conds(self, output_folder: str) -> None:
        init_conds = self.get_init_conds()
        with open(f"{output_folder}/ilp_init_conds.json", "w") as f:
            json.dump(init_conds, f, indent=4)

    def get_node_variables(self) -> pd.DataFrame:
        """Return node-specific variables. These variables include
        dispatch, unit status, unit switching, etc.
        """
        return self.node_vars

    def get_flow_variables(self) -> pd.DataFrame:
        """Return the flow variables."""
        return self.flow_vars

    def get_systemwide_variables(self) -> pd.DataFrame:
        """Return the system variables. We currently only have the
        system-wide spinning reserve shortfall.
        """
        return self.syswide_vars

    def get_runtimes(self) -> list[float]:
        """Return the model runtime from each iteration."""
        return self.runtimes

    def get_objvals(self) -> list[float]:
        """Return the objective values from each iteration."""
        return self.objvals

    def get_lmp(self) -> pd.DataFrame:
        """Return the locational marginal prices (LMP) data."""
        return self.lmp_df.pivot_table(
            index="hour", columns="node", values="value", aggfunc="first"
        )

    def get_model_stats(self) -> pd.DataFrame:
        return pd.DataFrame({"objval": self.objvals, "runtime": self.runtimes})

    def write_simulation_results(self, output_folder: str) -> None:
        """
        Write CSV files containing modeling results to the output directory.

        Args:
            output_folder (str): The directory where the output files will be saved.

        Returns:
            None
        """
        if not self.batch_mode:
            print("No data to write because batch_mode is False.")
            return

        data_to_write = [
            (self.node_vars, "node_variables"),
            (self.flow_vars, "flow_variables"),
            (self.syswide_vars, "system_variables"),
            (
                pd.DataFrame({"objval": self.objvals, "runtime": self.runtimes}),
                "model_stats",
            ),
        ]
        for df, output_name in data_to_write:
            write_df(
                df,
                output_folder=output_folder,
                output_name=output_name,
                model_id=self.inputs.model_id,  # Use model_name as the identifier
            )

        # Objective values and runtimes
        write_df(
            self.get_model_stats(),
            output_folder=output_folder,
            output_name="model_stats",
            model_id=self.inputs.model_id,
        )

        # LMP data if it exists
        if not self.lmp_df.empty:
            write_df(
                self.lmp_df,
                output_folder=output_folder,
                output_name="lmp",
                model_id=self.inputs.model_id,
            )
