""" This file contains supporting functions to perform analysis.
"""

import os
import re

import gurobipy as gp
import pandas as pd

from pownet.folder_utils import get_model_dir, get_output_dir, get_temp_dir
from pownet.data_utils import get_dates


def calc_percent_change(
    series_new: pd.Series, series_base: pd.Series, small_value: float = 0.0001
) -> pd.Series:
    """Return a series of percentage change."""
    percent_change = (
        abs(series_new - series_base) / (small_value + series_base) * 100
    ).round(4)
    return percent_change


def get_total_daily_load(model_name: str) -> pd.Series:
    """Return the total load of the system each day."""
    load = pd.read_csv(
        os.path.join(get_model_dir(), model_name, "demand_export.csv")
    ).sum(axis=1)
    return load.groupby(load.index // 24).sum()


def get_total_daily_renewable(model_name: str) -> pd.Series:
    """Return the total renewable capacity of the system each day."""
    renewables = pd.read_csv(
        os.path.join(get_model_dir(), model_name, "renewable.csv")
    ).sum(axis=1)
    return renewables.groupby(renewables.index // 24).sum()


def get_total_daily_from_output(
    variables: list[str], model_name: str, year: int = 2016
) -> pd.Series:
    """Return the"""
    status = pd.read_csv(
        os.path.join(get_output_dir(), f"{model_name}_node_variables.csv"), header=0
    )
    status = status[status["vartype"].isin(variables)]
    status = status.pivot_table(
        values="value", index=["hour"], columns=["node"], aggfunc="sum"
    )
    status = status.reset_index(drop=True)
    status["total"] = status.sum(axis=1)
    return status["total"].groupby(status.index // 24).sum()


def read_dw_stats():
    """Return a dataframe of the DW stats from csv files of a model.
    Basecase is the termination criterion - optgap (%) - of the Dantzig-Wolfe algorithm.
    """
    # Assume that all the PowNet Dantzig-Wolfe stats are in dw_stats folder.
    folder_name = os.path.join(get_temp_dir(), "dw_stats")
    filesets = [file for file in os.listdir(folder_name) if ("csv" in file)]

    capture_pat = r".*_(\w+)_([.\d]+)_(\w+)_dwstats"
    dw_stats = pd.DataFrame()
    for file in filesets:
        match = re.search(capture_pat, file)
        model_name = match.group(1)
        dw_stop = match.group(2)
        relaxed_subp = match.group(3)

        subset = pd.read_csv(os.path.join(folder_name, file))
        subset["model_name"] = file.split("_")[0]

        # Add labels from the filename
        subset["model_name"] = model_name
        subset["dw_stop"] = float(dw_stop)
        subset["relaxed_subp"] = relaxed_subp == "True"

        # Calculate attributes for analysis
        # Ratio of opt time: DW-MIP to Gurobi-MIP
        subset["dwmip_mip_opt_time"] = subset["dw_mip_time"] / subset["mip_gurobi_time"]
        # Optgap: DW-MIP to Gurobi-MIP
        subset["dwmip_mip_gap"] = calc_percent_change(
            subset["dw_mip_objval"], subset["mip_objval"]
        )
        # Optgap: DW-LP to Gurobi-MIP
        subset["dw_mip_gap"] = calc_percent_change(
            subset["dw_objval"], subset["mip_objval"]
        )
        # Optgap: Gurobi-LP to Gurobi-MIP
        subset["lp_mip_gap"] = calc_percent_change(
            subset["lp_objval"], subset["mip_objval"]
        )
        # The overhead is the difference between wallclock and DW (LP)
        subset["dw_overhead_time"] = subset["wall_clock_dw"] - subset["dw_time"]

        # Add contextual information from the input file
        subset["total_load"] = get_total_daily_load(model_name=model_name)
        subset["total_renewable"] = get_total_daily_renewable(model_name=model_name)
        subset["excess_renewable"] = subset["total_renewable"] - subset["total_load"]

        dw_stats = pd.concat([dw_stats, subset], axis=0)
    return dw_stats.reset_index(drop=True)


def create_infeasibility_file(mps_file: str):
    """Generate an infeasibility file from the given mps file."""
    model = gp.Model(mps_file)
    model.optimize()
    # Check model status
    if model.status == gp.GRB.INFEASIBLE:
        model.computeIIS()
        model.write(f"{mps_file}.ilp")
    else:
        raise ValueError("Optimal solution found")
