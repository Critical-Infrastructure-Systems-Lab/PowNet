<<<<<<< HEAD
from __future__ import annotations
import datetime
import os
import re
from typing import TYPE_CHECKING
=======
""" record.py: This module contains the SystemRecord class, which processes stores the modeling outputs from each iteration.
TODO: self.current_hydro, self.current_import for model coupling
"""

from .input import SystemInput
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0

import pandas as pd

from pownet.data_utils import (
<<<<<<< HEAD
    get_nodehour,
    get_nodehour_flow,
    get_nodehour_sys,
)
import pownet.config as config
from pownet.folder_utils import get_output_dir

if TYPE_CHECKING:
    from pownet.core import SystemInput


def write_df(
    df: pd.DataFrame,
    output_name: str,
    model_name: str,
    simulated_day: int,
    T: int,
) -> None:
    """Write a dataframe to the output folder."""
    STEP_BY_STEP = config.get_stepbystep()
    ONE_STEP = config.get_onestep()

    if STEP_BY_STEP:
        df.to_csv(
            os.path.join(
                get_output_dir(),
                f'{datetime.datetime.now().strftime("%Y%m%d_%H%M")}_{model_name}_D{simulated_day}_T{T}_{output_name}.csv',
            ),
            index=False,
        )
    elif ONE_STEP:
        df.to_csv(
            os.path.join(
                get_output_dir(),
                f'{datetime.datetime.now().strftime("%Y%m%d_%H%M")}_{model_name}_D{simulated_day}_T{T}_{output_name}.csv',
            ),
            index=False,
        )
    else:
        df.to_csv(
            os.path.join(
                get_output_dir(),
                f'{datetime.datetime.now().strftime("%Y%m%d_%H%M")}_{model_name}_D1-{simulated_day}_T{T}_{output_name}.csv',
            ),
            index=False,
        )


def increment_hour(df: pd.DataFrame, T: int, k: int):
    df = df.copy()
    # Increment the hour column according to the simulation period
    df["hour"] = df["hour"] + T * k
    return df


def get_init_min_on(
    df: pd.DataFrame,
    T: int,
    thermal_units: list[str, ...],
    TU: dict[str, int],
) -> dict[str, int]:
    init_min_on = {}

    for unit_g in thermal_units:
        df_unit = (
            df[(df["node"] == unit_g) & (df["vartype"] == "start")]
            .set_index("hour")
            .drop(["vartype", "node"], axis=1)
        )

        # Check if there are non-zero elements.
        if len(np.where(df_unit["value"])[0]) > 0:
            # np.argmax returns the index starting at zero, so we need to add 1
            time_last_off = np.max(np.where(df_unit["value"])) + 1
        else:
            # Taking the negative of T will ensure the calculation is negative
            # such that max(0, calculation) = 0
            time_last_off = -T

        # The calculated remaining shutdown duration can be negative,
        # which should be converted to
        init_min_on[unit_g] = max(0, TU[unit_g] - (T - time_last_off))

    return init_min_on


def get_init_min_off(
    df: pd.DataFrame,
    T: int,
    thermal_units: list[str, ...],
    TD: dict[str, int],
) -> dict[str, int]:
    init_min_off = {}

    for unit_g in thermal_units:
        df_unit = (
            df[(df["node"] == unit_g) & (df["vartype"] == "shut")]
            .set_index("hour")
            .drop(["vartype", "node"], axis=1)
        )

        # Check if there are non-zero elements.
        if len(np.where(df_unit["value"])[0]) > 0:
            # np.argmax returns the index starting at zero, so we need to add 1
            time_last_on = np.max(np.where(df_unit["value"])) + 1
        else:
            # Taking the negative of T will ensure the calculation is negative
            # such that max(0, calculation) = 0
            time_last_on = -T

        # The calculated remaining shutdown duration can be negative,
        # which should be converted to
        init_min_off[unit_g] = max(0, TD[unit_g] - (T - time_last_on))

    return init_min_off


def get_hydro_from_model(model: gp.Model, k: int) -> tuple[pd.DataFrame, int, int]:
    """Extract the hydro dispatch from the model. The model is assumed to have
    variables named as "phydro[reservoir,t]". The function returns a dataframe
    with the columns: reservoir, hour, dispatch. The hour is incremented by the
    simulation period, and the dataframe is pivoted such that the reservoirs are
    the columns and the hours are the index. The function also returns the start
    and end day of the hydro dispatch.
    """
    hydropower_dispatch = []
    pattern = "phydro\[(\w+),(\d+)\]"
    for v in model.getVars():
        if re.match(pattern, v.varName):
            reservoir = re.search(pattern, v.varName).group(1)
            hour = int(re.search(pattern, v.varName).group(2))
            hydropower_dispatch.append((reservoir, hour, v.x))
    df = pd.DataFrame(hydropower_dispatch, columns=["reservoir", "hour", "dispatch"])
    # Pivot to have the hour as the index and reservoir as the columns
    df = df.pivot(index="hour", columns="reservoir", values="dispatch")
    # Update the index to reflect the hour index in a year
    df.index = df.index + k * 24
    start_day = df.index[0] // 24 + 1
    end_day = df.index[-1] // 24 + 1
    return df, start_day, end_day


def get_hydro_from_df(df: pd.DataFrame):
    df = df[df["vartype"] == "phydro"]
    df = df.set_index(["hour", "node"])
    df = df["value"].unstack().reset_index()
    df = df.pivot(index="hour", columns="node", values="value")
    start_day = df.index[0] // 24
    end_day = df.index[-1] // 24
    return df, start_day, end_day


def convert_to_daily_hydro(
    df: pd.DataFrame, start_day: int, end_day: int
) -> pd.DataFrame:
    daily_hydro = df.groupby((df.index - 1) // 24).sum()
    daily_hydro.index = range(start_day, end_day)
    return daily_hydro
=======
    parse_node_variables,
    parse_flow_variables,
    parse_syswide_variables,
    parse_lmp,
    calc_remaining_on_duration,
    calc_remaining_off_duration,
    write_df_to_output_dir,
)
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0


class SystemRecord:
    """This class stores modeling outputs from each iteration. The results are stored
    in three dataframes: node_vars, flow_vars, and syswide_vars. The initial conditions
    are also stored in the class.
    """

    def __init__(self, system_input: SystemInput) -> None:
<<<<<<< HEAD
        self.T: int = system_input.T
        self.model_name: str = system_input.model_name
        self.runtimes = None
        self.simulated_day: int = system_input.simulated_day
        self.thermal_units: list = system_input.thermal_units
        self.TD: dict[str, int] = system_input.TD
        self.TU: dict[str, int] = system_input.TU
=======

        self.inputs = system_input
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0

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
<<<<<<< HEAD
        ONE_STEP = config.get_onestep()
        if isinstance(model, gp.Model):
            results = self._get_sol_from_gurobi(model)
            self.objvals.append(model.objVal)
        elif isinstance(model, highspy.highs.Highs):
            results = self._get_sol_from_highs(model)
            self.objvals.append(self._get_objval_from_highs(model))
=======
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
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0

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

<<<<<<< HEAD
        # Save the model runtime
        if isinstance(model, gp.Model):
            if k == 0 or ONE_STEP:
                self.runtimes = [model.runtime]
            else:
                self.runtimes.append(model.runtime)
        elif isinstance(model, highspy.highs.Highs):
            if k == 0 or ONE_STEP:
                self.runtimes = [model.getRunTime()]
            else:
                self.runtimes.append(model.getRunTime())
=======
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
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0

        self.init_conds = self.get_init_conds()
        self.init_conds_df: pd.DataFrame = None
        self.init_conds_df = pd.DataFrame(
            self.init_conds.items(), columns=["Variable", "Value"]
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

<<<<<<< HEAD
    def to_csv(self) -> None:
        write_df(
            self.var_node_t,
            output_name="node_variables",
            model_name=self.model_name,
            simulated_day=self.simulated_day + 1,
            T=self.T,
        )
        write_df(
            self.var_flow,
            output_name="flow_variables",
            model_name=self.model_name,
            simulated_day=self.simulated_day + 1,
            T=self.T,
        )
        write_df(
            self.var_syswide,
            output_name="system_variables",
            model_name=self.model_name,
            simulated_day=self.simulated_day + 1,
            T=self.T,
        )
        write_df(
            self.init_conds_df,
            output_name="initial_conditions",
            model_name=self.model_name,
            simulated_day=self.simulated_day + 1,
            T=self.T,
        )

        objvals = pd.DataFrame({"objval": self.objvals})
        write_df(
            objvals,
            output_name="objvals",
            model_name=self.model_name,
            simulated_day=self.simulated_day + 1,
            T=self.T,
=======
    def get_objvals(self) -> list[float]:
        return self.objvals

    def get_lmp(self) -> pd.DataFrame:
        return self.lmp_df.pivot_table(
            index="hour", columns="node", values="value", aggfunc="first"
>>>>>>> 2713ab8ef7d05cb2166b986110140e0693cd09f0
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
