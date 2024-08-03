from __future__ import annotations
import datetime
import os
import re
from typing import TYPE_CHECKING

import gurobipy as gp
import highspy
import pandas as pd
import numpy as np

from pownet.model import PowerSystemModel
from pownet.data_utils import get_nodehour_flow
from pownet.folder_utils import get_output_dir

if TYPE_CHECKING:
    from pownet.core import SystemInput


def write_df(
    df: pd.DataFrame,
    output_name: str,
    model_name: str,
    sim_horizon: int,
) -> None:
    """Write a dataframe to the output folder."""
    df.to_csv(
        os.path.join(
            get_output_dir(),
            f'{datetime.datetime.now().strftime("%Y%m%d_%H%M")}_{model_name}_{sim_horizon}_{output_name}.csv',
        ),
        index=False,
    )


def increment_hour(df: pd.DataFrame, sim_horizon: int, step_k: int):
    """Since the model is solved in a rolling horizon manner, we need to increment the hour"""
    df = df.copy()
    df["hour"] = df["hour"] + sim_horizon * step_k
    return df


def calc_min_on(
    df: pd.DataFrame,
    sim_horizon: int,
    thermal_units: list[str],
    TU: dict[str, int],
) -> dict[str, int]:
    """Calculate the remaining minimum online duration for each thermal unit."""
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
            time_last_off = -sim_horizon

        # The calculated remaining shutdown duration can be negative,
        # which should be converted to
        init_min_on[unit_g] = max(0, TU[unit_g] - (sim_horizon - time_last_off))

    return init_min_on


def calc_min_off(
    df: pd.DataFrame,
    sim_horizon: int,
    thermal_units: list[str],
    TD: dict[str, int],
) -> dict[str, int]:
    """Calculate the remaining minimum shutdown duration for each thermal unit."""
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
            time_last_on = -sim_horizon

        # The calculated remaining shutdown duration can be negative,
        # which should be converted to
        init_min_off[unit_g] = max(0, TD[unit_g] - (sim_horizon - time_last_on))

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


class SystemRecord:
    """This class is used to store the results of the model. The results are stored
    in three dataframes: node_vars, flow_vars, and syswide_vars. The node_vars dataframe
    stores the node-specific variables such as dispatch, unit status, unit switching, etc.
    The flow_vars dataframe stores the flow variables. The syswide_vars dataframe stores
    the system variables. The class also stores the current state of the system such as
    the current dispatch, unit status, unit switching, etc. The class also stores
    the minimum time on/off for each thermal unit.
    """

    def __init__(self, system_input: SystemInput) -> None:
        self.sim_horizon: int = system_input.T
        self.model_name: str = system_input.model_name
        self.thermal_units: list = system_input.thermal_units
        self.TD: dict[str, int] = system_input.TD
        self.TU: dict[str, int] = system_input.TU

        # The model results are separated into three types based on
        # the formating of their index: var(node, t), var(node, node, t), var(t)
        self.node_vars: pd.DataFrame = None
        self.flow_vars: pd.DataFrame = None
        self.syswide_vars: pd.DataFrame = None

        self.objvals = []
        self.runtimes = []

        # These are dispatch, unit status, unit switching, etc.
        self.current_p = None
        self.current_u = None
        self.current_v = None
        self.current_w = None
        self.current_min_on = None
        self.current_min_off = None

    def keep(
        self,
        power_system_model: PowerSystemModel,
        step_k: int,
    ) -> None:
        """Keep the simulation results at the current simulation period step_k"""

        self.runtimes.append(power_system_model.get_runtime())
        self.objvals.append(power_system_model.get_objval())

        solution = pd.DataFrame(power_system_model.get_solution())
        # Create a col of variable types for filtering
        pat_vartype = r"(\w+)\["
        solution[["vartype"]] = solution["varname"].str.extract(
            pat_vartype, expand=True
        )

        ##################
        # Node variables are in the (node, t) format.
        ##################
        pat_node_var = r"(\w+)\[(\w+),(\d+)\]"
        # Filter to only variables that are node-specific
        current_node_vars = solution[solution["varname"].str.match(pat_node_var)].copy()
        current_node_vars[["node", "hour"]] = current_node_vars["varname"].str.extract(
            pat_node_var, expand=True
        )[[1, 2]]
        # Convert the hour to an integer
        current_node_vars["hour"] = current_node_vars["hour"].astype(int)
        # The extracted hour is across the entire simulation period, so we need to increment it
        # by the simulation horizon to get the actual hour of the year.
        current_node_vars = increment_hour(
            current_node_vars, sim_horizon=self.sim_horizon, step_k=step_k
        )
        # The solver may return binary values that are are not exactly zero or one, so we need to round them
        current_node_vars.loc[
            np.isclose(current_node_vars["value"], 0, atol=1e-4), "value"
        ] = 0
        current_node_vars.loc[
            np.isclose(current_node_vars["value"], 1, atol=1e-4), "value"
        ] = 1

        self.node_vars = pd.concat([self.node_vars, current_node_vars], axis=0)

        ##################
        # The flow variables are in the (node, node, t) format.
        ##################
        pat_flow_var = r"flow\[(\w+),(\w+),(\d+)\]"
        cur_flow_vars = solution[solution["varname"].str.match(pat_flow_var)].copy()
        cur_flow_vars[["node_a", "node_b", "hour"]] = cur_flow_vars[
            "varname"
        ].str.extract(pat_flow_var, expand=True)
        cur_flow_vars["hour"] = cur_flow_vars["hour"].astype(int)
        cur_flow_vars = increment_hour(
            cur_flow_vars, sim_horizon=self.sim_horizon, step_k=step_k
        )
        self.flow_vars = pd.concat([self.flow_vars, cur_flow_vars], axis=0)

        ##################
        # The system-wide variables are in the (t) format
        ##################
        pat_syswide = r"(\w+)\[(\d+)\]"
        cur_syswide_vars = solution[solution["varname"].str.match(pat_syswide)].copy()
        cur_syswide_vars["hour"] = cur_syswide_vars["varname"].str.extract(
            pat_syswide, expand=True
        )[1]
        cur_syswide_vars["hour"] = cur_syswide_vars["hour"].astype(int)
        cur_syswide_vars = increment_hour(
            cur_syswide_vars, sim_horizon=self.sim_horizon, step_k=step_k
        )
        self.syswide_vars = pd.concat([self.syswide_vars, cur_syswide_vars], axis=0)

        ##################
        # Initial conditions are dispatch (p), commitment (u), startup (v), and shutdown (w).
        ##################
        self.current_p = (
            current_node_vars[current_node_vars["vartype"] == "p"]
            .drop("vartype", axis=1)
            .set_index(["node", "hour"])
            .to_dict()["value"]
        )
        self.current_u = (
            current_node_vars[current_node_vars["vartype"] == "status"]
            .drop("vartype", axis=1)
            .set_index(["node", "hour"])
            .to_dict()["value"]
        )

        self.current_v = (
            current_node_vars[current_node_vars["vartype"] == "start"]
            .drop("vartype", axis=1)
            .set_index(["node", "hour"])
            .to_dict()["value"]
        )

        self.current_w = (
            current_node_vars[current_node_vars["vartype"] == "shut"]
            .drop("vartype", axis=1)
            .set_index(["node", "hour"])
            .to_dict()["value"]
        )

        # Need to calculate the minimum time on/off
        self.current_min_on = calc_min_on(
            current_node_vars,
            sim_horizon=self.sim_horizon,
            thermal_units=self.thermal_units,
            TU=self.TU,
        )
        self.current_min_off = calc_min_off(
            current_node_vars,
            sim_horizon=self.sim_horizon,
            thermal_units=self.thermal_units,
            TD=self.TD,
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

    def write_simulation_results(self) -> None:
        write_df(
            self.node_vars,
            output_name="node_variables",
            model_name=self.model_name,
            sim_horizon=self.sim_horizon,
        )
        write_df(
            self.flow_vars,
            output_name="flow_variables",
            model_name=self.model_name,
            sim_horizon=self.sim_horizon,
        )
        write_df(
            self.syswide_vars,
            output_name="system_variables",
            model_name=self.model_name,
            sim_horizon=self.sim_horizon,
        )
        objvals = pd.DataFrame({"objval": self.objvals})
        write_df(
            objvals,
            output_name="objvals",
            model_name=self.model_name,
            sim_horizon=self.sim_horizon,
        )
        runtimes = pd.DataFrame({"runtime": self.runtimes})

    def get_hydro_dispatch(self) -> pd.DataFrame:
        # TODO: This function should not convert to daily hydro dispatch
        # because a function should only do one thing.
        df = self.node_vars[self.node_vars["vartype"] == "phydro"]
        df = df[["node", "hour", "value"]]
        df = df.rename(columns={"node": "reservoir", "value": "dispatch"})
        # Columns: reservoir, hour, v.x
        df = df.pivot(index="hour", columns="reservoir", values="dispatch")
        start_day = df.index[0] // 24
        end_day = df.index[-1] // 24
        df = convert_to_daily_hydro(df, start_day, end_day)
        return df

    @staticmethod
    def get_hydro_from_model(model: gp.Model) -> dict:
        """The output of the hydro dispatch is a dictionary of the form
        {
            "reservoir1": {t1: value1, t2: value2, ...},
            "reservoir2": {t1: value1, t2: value2, ...},
        }
        """
        hydro_dispatch = {}
        # Variables are named as "phydro[reservoir,t]"
        pattern = r"phydro\[(\w+),(\d+)\]"
        for v in model.getVars():
            varname = v.varName
            match = re.match(pattern, varname)
            if match:
                reservoir, t = match.groups()
                t = int(t)
                if reservoir not in hydro_dispatch:
                    hydro_dispatch[reservoir] = {}
                hydro_dispatch[reservoir][t] = v.X
        return hydro_dispatch
