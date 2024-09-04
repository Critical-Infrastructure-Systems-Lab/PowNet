""" record.py: This module contains the SystemRecord class, which processes stores the modeling outputs from each iteration.
TODO: self.current_hydro, self.current_import for model coupling
"""

from __future__ import annotations

import pandas as pd

from pownet.data_utils import (
    parse_node_variables,
    parse_flow_variables,
    parse_syswide_variables,
    parse_lmp,
    calc_remaining_on_duration,
    calc_remaining_off_duration,
    write_df_to_output_dir,
)


class SystemRecord:
    """This class stores modeling outputs from each iteration. The results are stored
    in three dataframes: node_vars, flow_vars, and syswide_vars. The initial conditions
    are also stored in the class.
    """

    def __init__(self, system_input: "SystemInput") -> None:

        self.inputs = system_input

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
        self.current_p: dict[str, float] = {}
        self.current_u: dict[str, int] = {}
        self.current_v: dict[str, int] = {}
        self.current_w: dict[str, int] = {}
        self.current_min_on: dict[str, int] = {}
        self.current_min_off: dict[str, int] = {}

    def keep(
        self,
        runtime: float,
        objval: float,
        solution: pd.DataFrame,
        step_k: int,
        lmp: dict[str, float] = None,
    ) -> None:
        """Keep the simulation results at the current simulation period step_k"""

        def _extract_vartype_data(df: pd.DataFrame, vartype: str) -> dict[str, float]:
            """Extracts data for a specific 'vartype' from the DataFrame and converts it to a dictionary."""
            return (
                df[
                    (df["vartype"] == vartype)
                    & (df["timestep"] == self.inputs.sim_horizon)
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

        current_node_vars = parse_node_variables(
            solution, self.inputs.sim_horizon, step_k
        )

        ##################
        # Initial conditions: vpower (p), commitment (u),
        # startup (v), and shutdown (w).
        ##################
        self.current_p = _extract_vartype_data(current_node_vars, "vpower")
        self.current_u = _extract_vartype_data(current_node_vars, "status")
        self.current_v = _extract_vartype_data(current_node_vars, "startup")
        self.current_w = _extract_vartype_data(current_node_vars, "shutdown")

        # Need to calculate the minimum time on/off
        self.current_min_on = calc_remaining_on_duration(
            current_node_vars,
            sim_horizon=self.inputs.sim_horizon,
            thermal_units=self.inputs.thermal_units,
            TU=self.inputs.TU,
        )
        self.current_min_off = calc_remaining_off_duration(
            current_node_vars,
            sim_horizon=self.inputs.sim_horizon,
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
        # Append results to the existing dataframes
        ##################
        # Only keep the first 24-hours of the simulation
        current_node_vars = current_node_vars[current_node_vars["timestep"] <= 24]
        # Remove varname column from the three dataframes
        # move the value column to the end
        current_node_vars = current_node_vars.drop(["varname", "timestep"], axis=1)
        self.node_vars = pd.concat([self.node_vars, current_node_vars], axis=0)

        flow_vars = parse_flow_variables(
            solution=solution, sim_horizon=self.inputs.sim_horizon, step_k=step_k
        )
        # Only keep the first 24-hours of the simulation
        flow_vars = flow_vars[flow_vars["timestep"] <= 24]
        flow_vars = flow_vars.drop("timestep", axis=1)
        self.flow_vars = pd.concat(
            [
                self.flow_vars,
                flow_vars,
            ],
            axis=0,
        )

        syswide_vars = parse_syswide_variables(
            solution=solution, sim_horizon=self.inputs.sim_horizon, step_k=step_k
        )
        # Only keep the first 24-hours of the simulation
        syswide_vars = syswide_vars[syswide_vars["timestep"] <= 24]
        syswide_vars = syswide_vars.drop("timestep", axis=1)
        self.syswide_vars = pd.concat(
            [
                self.syswide_vars,
                syswide_vars,
            ],
            axis=0,
        )

    def get_init_conds(self) -> dict[str, dict]:
        return {
            "initial_p": self.current_p,
            "initial_u": self.current_u,
            "initial_v": self.current_v,
            "initial_w": self.current_w,
            "initial_min_on": self.current_min_on,
            "initial_min_off": self.current_min_off,
        }

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
        return self.runtimes

    def get_objvals(self) -> list[float]:
        return self.objvals

    def get_lmp(self) -> pd.DataFrame:
        return self.lmp_df.pivot_table(
            index="hour", columns="node", values="value", aggfunc="first"
        )

    def write_simulation_results(self) -> None:
        """
        Write 4 CSV files containing modeling results to the output directory.
        """
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
            write_df_to_output_dir(
                df,
                output_name=output_name,
                model_id=self.inputs.model_id,  # Use model_name as the identifier
            )

        if not self.lmp_df.empty:
            write_df_to_output_dir(
                self.lmp_df,
                output_name="lmp",
                model_id=self.inputs.model_id,
            )
