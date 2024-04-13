import datetime
import os
import re

import gurobipy as gp
import highspy
import pandas as pd
import numpy as np

from pownet.core.input import SystemInput
from pownet.processing.functions import (
    get_nodehour,
    get_nodehour_flow,
    get_nodehour_sys,
)
from pownet.folder_sys import get_output_dir


def write_df(
    df: pd.DataFrame,
    output_name: str,
    model_name: str,
    T: int,
) -> None:
    """Write a dataframe to the output folder."""
    df.to_csv(
        os.path.join(
            get_output_dir(),
            f'{datetime.datetime.now().strftime("%Y%m%d_%H%M")}_{model_name}_{T}_{output_name}.csv',
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


def get_hydro_from_model(model: gp.Model, k: int):
    hydropower_dispatch = []
    pattern = 'phydro\[(\w+),(\d+)\]'
    for v in model.getVars():
        if re.match(pattern, v.varName):
            reservoir = re.search(pattern, v.varName).group(1)
            hour = int(re.search(pattern, v.varName).group(2))
            hydropower_dispatch.append(
                (reservoir, hour, v.x)
            )
    df = pd.DataFrame(hydropower_dispatch, columns=[
                      'reservoir', 'hour', 'dispatch'])
    # Pivot to have the hour as the index and reservoir as the columns
    df = df.pivot(index='hour', columns='reservoir', values='dispatch')
    df.index = df.index + k*24
    start_day = df.index[0] // 24
    end_day = df.index[-1] // 24
    return df, start_day, end_day


def get_hydro_from_df(df: pd.DataFrame):
    df = df[df['vartype'] == 'phydro']
    df = df.set_index(['hour', 'node'])
    df = df['value'].unstack().reset_index()
    df = df.pivot(index='hour', columns='node', values='value')
    start_day = df.index[0] // 24
    end_day = df.index[-1] // 24
    return df, start_day, end_day


def convert_to_daily_hydro(df: pd.DataFrame, start_day: int, end_day: int) -> pd.DataFrame:
    daily_hydro = df.groupby((df.index-1) // 24).sum()
    daily_hydro.index = range(start_day, end_day)
    return daily_hydro


class SystemRecord:
    def __init__(self, system_input: SystemInput) -> None:
        self.T: int = system_input.T
        self.model_name: str = system_input.model_name
        self.runtimes = None

        self.thermal_units: list = system_input.thermal_units
        self.TD: dict[str, int] = system_input.TD
        self.TU: dict[str, int] = system_input.TU

        # The model results are separated into three types based on
        # the formating of their index: var(node, t), var(node, node, t), var(t)
        self.var_node_t: pd.DataFrame = None
        self.var_flow: pd.DataFrame = None
        self.var_syswide: pd.DataFrame = None

        # These attributes are a list of values
        self.current_p = None
        self.current_u = None
        self.current_v = None
        self.current_w = None
        self.current_min_on = None
        self.current_min_off = None

    def _get_sol_from_gurobi(self, gp_model) -> pd.DataFrame:
        # Extract the variables from the model to process them
        return pd.DataFrame(
            {"varname": gp_model.getAttr(
                "varname"), "value": gp_model.getAttr("X")}
        )

    def _get_sol_from_highs(self, highs_model: highspy.highs.Highs) -> pd.DataFrame:
        # Extract the variables from the model to process them
        # Check the solution
        return pd.DataFrame(
            {
                "varname": [
                    highs_model.getColName(i)[1]
                    for i in range(
                        highs_model.getNumCol()
                    )  # getColName returns a tuple
                ],
                "value": highs_model.getSolution().col_value,
            }
        )

    def keep(
        self,
        model: gp.Model | highspy.highs.Highs,
        k: int,
    ) -> None:

        if isinstance(model, gp.Model):
            results = self._get_sol_from_gurobi(model)
        elif isinstance(model, highspy.highs.Highs):
            results = self._get_sol_from_highs(model)

        # Create a col of variable types for filtering
        pat_vartype = r"(\w+)\["
        results[["vartype"]] = results["varname"].str.extract(
            pat_vartype, expand=True)

        # Some variables are not in the (node, t) format.
        # These are system-level variables
        col2exclude = ["flow", "sys_spin"]

        # Format the dataframe into vartype, node, hour, value columns
        cur_var_node_t = results[~results["vartype"].isin(col2exclude)]
        cur_var_node_t = get_nodehour(cur_var_node_t)
        # Prevent numerical instability by ensuring the binary values are zero or one
        cur_var_node_t.loc[
            np.isclose(cur_var_node_t["value"], 0, atol=1e-4), "value"
        ] = 0
        cur_var_node_t.loc[
            np.isclose(cur_var_node_t["value"], 1, atol=1e-4), "value"
        ] = 1

        cur_var_flow = results[results["vartype"] == "flow"]
        cur_var_flow = get_nodehour_flow(cur_var_flow)

        cur_var_syswide = results[results["vartype"] == "sys_spin"]
        cur_var_syswide = get_nodehour_sys(cur_var_syswide)

        # Save some variables as initial conditions for the next simulation period
        self.current_p = (
            cur_var_node_t[cur_var_node_t["vartype"] == "p"]
            .drop("vartype", axis=1)
            .set_index(["node", "hour"])
            .to_dict()["value"]
        )

        self.current_u = (
            cur_var_node_t[cur_var_node_t["vartype"] == "status"]
            .drop("vartype", axis=1)
            .set_index(["node", "hour"])
            .to_dict()["value"]
        )

        self.current_v = (
            cur_var_node_t[cur_var_node_t["vartype"] == "start"]
            .drop("vartype", axis=1)
            .set_index(["node", "hour"])
            .to_dict()["value"]
        )

        self.current_w = (
            cur_var_node_t[cur_var_node_t["vartype"] == "shut"]
            .drop("vartype", axis=1)
            .set_index(["node", "hour"])
            .to_dict()["value"]
        )

        self.current_u = {k: v for k, v in self.current_u.items()}
        self.current_v = {k: v for k, v in self.current_v.items()}
        self.current_w = {k: v for k, v in self.current_w.items()}

        # Record the results after incrementing the hour by the simulation period
        cur_var_node_t = increment_hour(cur_var_node_t, T=self.T, k=k)
        # The solver produces very small numbers
        cur_var_node_t.loc[np.isclose(cur_var_node_t["value"], 0), "value"] = 0

        self.var_node_t = pd.concat([self.var_node_t, cur_var_node_t], axis=0)

        cur_var_flow = increment_hour(cur_var_flow, T=self.T, k=k)
        self.var_flow = pd.concat([self.var_flow, cur_var_flow], axis=0)

        # Currently there is only the system-wider reserve
        cur_var_syswide = increment_hour(cur_var_syswide, T=self.T, k=k)
        self.var_syswide = pd.concat(
            [self.var_syswide, cur_var_syswide], axis=0)

        # Need to calculate the minimum time on/off
        self.current_min_on = get_init_min_on(
            cur_var_node_t, T=self.T, thermal_units=self.thermal_units, TU=self.TU
        )
        self.current_min_off = get_init_min_off(
            cur_var_node_t, T=self.T, thermal_units=self.thermal_units, TD=self.TD
        )

        # Save the model runtime
        if isinstance(model, gp.Model):
            if k == 0:
                self.runtimes = [model.runtime]
            else:
                self.runtimes.append(model.runtime)
        elif isinstance(model, highspy.highs.Highs):
            if k == 0:
                self.runtimes = [model.getRunTime()]
            else:
                self.runtimes.append(model.getRunTime())

    def get_init_conds(self) -> dict[str, dict]:
        return {
            "initial_p": self.current_p,
            "initial_u": self.current_u,
            "initial_v": self.current_v,
            "initial_w": self.current_w,
            "initial_min_on": self.current_min_on,
            "initial_min_off": self.current_min_off,
        }

    def get_record(self) -> None:
        """Return all the variables as a set of three dataframes"""
        return [self.var_node_t, self.var_flow, self.var_syswide]

    def get_node_variables(self) -> pd.DataFrame:
        """Return node-specific variables. These variables include
        dispatch, unit status, unit switching, etc.
        """
        return self.var_node_t

    def get_flow_variables(self) -> pd.DataFrame:
        """Return the flow variables."""
        return self.var_flow

    def get_system_variables(self) -> pd.DataFrame:
        """Return the system variables. We currently only have the
        system-wide spinning reserve shortfall.
        """
        return self.var_syswide

    def runtimes(self) -> list[datetime.datetime]:
        return self.runtimes

    def to_csv(self) -> None:
        write_df(
            self.var_node_t, output_name="node_variables", model_name=self.model_name, T=self.T
        )
        write_df(
            self.var_flow, output_name="flow_variables", model_name=self.model_name, T=self.T
        )
        write_df(
            self.var_syswide, output_name="system_variables", model_name=self.model_name, T=self.T
        )

    def get_hydro_dispatch(self) -> pd.DataFrame:
        df = self.var_node_t[self.var_node_t['vartype'] == 'phydro']
        df = df[['node', 'hour', 'value']]
        df = df.rename(columns={'node': 'reservoir', 'value': 'dispatch'})
        # Columns: reservoir, hour, v.x
        df = df.pivot(index='hour', columns='reservoir', values='dispatch')
        start_day = df.index[0] // 24
        end_day = df.index[-1] // 24
        df = convert_to_daily_hydro(df, start_day, end_day)
        return df

    @staticmethod
    def get_hydro_from_model(model: gp.Model) -> dict:
        ''' The output of the hydro dispatch is a dictionary of the form
        {
            "reservoir1": {t1: value1, t2: value2, ...},
            "reservoir2": {t1: value1, t2: value2, ...},
        }
        '''
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
