from __future__ import annotations
import os

import pandas as pd

from pownet.folder_utils import get_database_dir
from pownet.data_utils import get_dates


def get_fuel_mix_order() -> list[str]:
    """Return the order of fuel mix for plotting.
    We use this list to order the node variables dataframe.

    Returns
        list[str]: The order of fuel mix.
    -------
    """
    return pd.read_csv(
        os.path.join(get_database_dir(), "fuels.csv"),
        header=0,
    )["name"].tolist()


class OutputProcessor:
    def __init__(self, system_input: "SystemInput"):
        self.inputs = system_input
        self.dates: pd.DataFrame = None

        self.node_variables: pd.DataFrame = None

        self.total_dispatch: pd.DataFrame = None
        self.monthly_dispatch: pd.DataFrame = None
        self.daily_dispatch: pd.DataFrame = None

        self.total_demand: pd.Series = None
        self.monthly_demand: pd.Series = None
        self.daily_demand: pd.Series = None

        # Define the order of fuel mix. Baseload at the bottom,
        # renewables in the middle, then peaker plants, and shortfall
        self.fuel_mix_order: list[str] = None

        self.unit_status: pd.DataFrame = None

    def load(
        self,
        node_var_df: pd.DataFrame,
    ) -> None:
        """Process node-specific variables from PowNet."""
        # Extract the dispatch of generators (thermal units and renewables)
        dispatch_vars = [
            "pthermal",
            "psolar",
            "pwind",
            "phydro",
            "pimp",
            "pos_pmismatch",
            "neg_pmismatch",
        ]
        self.node_variables = node_var_df.loc[
            node_var_df["vartype"].isin(dispatch_vars)
        ].reset_index(drop=True)
        self.node_variables["fuel_type"] = self.node_variables.apply(
            lambda x: self.inputs.fuelmap.get(x["node"], None), axis=1
        )
        # Assign import and slack fuel types as they are not in the fuelmap dictionary
        self.node_variables.loc[
            self.node_variables["vartype"] == "pimp", "fuel_type"
        ] = "import"
        self.node_variables.loc[
            self.node_variables["vartype"] == "pos_pmismatch", "fuel_type"
        ] = "shortfall"
        self.node_variables.loc[
            self.node_variables["vartype"] == "neg_pmismatch", "fuel_type"
        ] = "curtailment"

        # self.total_dispatch = self.node_variables.reset_index(drop=True)
        self.total_dispatch = (
            self.node_variables[["fuel_type", "value", "hour"]]
            .groupby(["fuel_type", "hour"])
            .sum()
        )
        self.total_dispatch = self.total_dispatch.reset_index()
        self.total_dispatch = self.total_dispatch.pivot(
            columns=["hour"], index=["fuel_type"]
        ).T.reset_index(drop=True)
        # PowNet indexing starts at 1
        self.total_dispatch.index += 1

        # Reorder the columns of total dispatch in case we want to plot
        self.fuel_mix_order = get_fuel_mix_order()
        self.fuel_mix_order = [
            fuel for fuel in self.fuel_mix_order if fuel in self.total_dispatch.columns
        ]
        self.total_dispatch = self.total_dispatch[self.fuel_mix_order]

        # Sum across each month to get the monthly dispatch
        # For processing dataframes
        self.dates = get_dates(year=self.inputs.year)
        self.dates.index += 1

        self.monthly_dispatch = self.total_dispatch.copy()
        self.monthly_dispatch["month"] = self.dates["date"].dt.to_period("M")
        self.monthly_dispatch = self.monthly_dispatch.groupby("month").sum()
        self.monthly_dispatch.index = self.monthly_dispatch.index.strftime("%b")

        # Sum across 24 hours to get the daily dispatch.
        self.daily_dispatch = self.total_dispatch.copy()
        self.daily_dispatch = self.daily_dispatch.groupby(
            (self.daily_dispatch.index - 1) // 24
        ).sum()
        self.daily_dispatch.index += 1
        self.daily_dispatch.index.name = "day"

        # Demand is an input to the simulation
        self.total_demand = self.inputs.demand.sum(axis=1).to_frame()
        self.total_demand.columns = ["demand"]
        self.total_demand.index.name = "hour"

        # Sum across each month to get the monthly demand
        self.monthly_demand = self.total_demand.copy()
        self.monthly_demand["month"] = self.dates["date"].dt.to_period("M")
        self.monthly_demand = self.monthly_demand.groupby("month").sum()
        self.monthly_demand.index = self.monthly_demand.index.strftime("%b")

        # Need -1 because the index starts with 1 and we want to group by 24 hours
        self.daily_demand = self.total_demand.groupby(
            (self.total_demand.index - 1) // 24
        ).sum()
        self.daily_demand.index += 1

        # Need unit statuses for plotting their activities
        self.unit_status = node_var_df[node_var_df["vartype"] == "status"].reset_index(
            drop=True
        )

    def get_hourly_dispatch(self) -> pd.DataFrame:
        return self.total_dispatch

    def get_daily_dispatch(self) -> pd.DataFrame:
        return self.daily_dispatch

    def get_monthly_dispatch(self) -> pd.DataFrame:
        return self.monthly_dispatch

    def get_hourly_demand(self) -> pd.Series:
        return self.total_demand

    def get_daily_demand(self) -> pd.Series:
        return self.daily_demand

    def get_monthly_demand(self) -> pd.Series:
        return self.monthly_demand

    def get_unit_status(self) -> pd.DataFrame:
        return self.unit_status

    def load_from_csv(
        self,
        filename: pd.DataFrame,
    ) -> None:
        """Load the PowNet output from a CSV file."""
        node_var_df = pd.read_csv(filename, header=0)
        self.load(node_var_df=node_var_df)

    def get_daily_dispatch_by_fuel_type(self, fuel_type) -> pd.DataFrame:
        """Return the daily hydro generation."""
        daily_dispatch = self.daily_dispatch[fuel_type].to_frame()
        daily_dispatch.columns = [fuel_type]
        return daily_dispatch

    def get_monthly_dispatch_by_fuel_type(self, fuel_type) -> pd.DataFrame:
        """Return the monthly hydro generation."""
        monthly_dispatch = self.monthly_dispatch[fuel_type].to_frame()
        monthly_dispatch.columns = [fuel_type]
        return monthly_dispatch

    def get_co2_emission(self, time_interval: str) -> pd.DataFrame:
        """Return the CO2 emissions for timestep.
        From Chowdhury, Dang, Nguyen, Koh, & Galelli. (2021).

        coal: 1.04 Mton/MWh
        gas:  0.47 Mton/MWh
        oil : 0.73 Mton/MWh

        From https://www.eia.gov/environment/emissions/co2_vol_mass.php:
        wsth: 49.89 kg/MMBtu
              = 49.89 kg/MMBtu * 3.412 MMBtu/MWh * 1 Mton/1000 kg = 0.170


        """
        co2_map = {
            "coal": 1.04,
            "gas": 0.47,
            "oil": 0.73,
            "import": 0.0,
            "shortfall": 0.0,
            "curtailment": 0.0,
            "biomass": 0.0,
            "wsth": 0.170,
            "slack": 0.0,
        }

        if time_interval == "monthly":
            df = self.get_monthly_thermal_dispatch()
        elif time_interval == "daily":
            df = self.get_daily_thermal_dispatch()
        else:
            raise ValueError("Time interval must be either 'monthly' or 'daily'.")

        co2_emissions = pd.DataFrame()
        for fuel in df.columns:
            co2_emissions[fuel] = df[fuel] * co2_map[fuel]

        return co2_emissions

    def get_fuel_cost(self, time_interval: str) -> pd.DataFrame:
        """Return the system cost for each timestep."""
        cost_map = {
            "coal": 5,
            "gas": 5.85,
            "oil": 8,
            "import": 10,
            "shortfall": 1000,
            "curtailment": 1000,
            "biomass": 3.02,
            "wsth": 3.02,
            "slack": 1000,
        }

        if time_interval == "monthly":
            df = self.get_monthly_thermal_dispatch()
        elif time_interval == "daily":
            df = self.get_daily_thermal_dispatch()
        else:
            raise ValueError("Time interval must be either 'monthly' or 'daily'.")

        system_cost = pd.DataFrame()
        for fuel in df.columns:
            system_cost[fuel] = df[fuel] * cost_map[fuel]

        return system_cost
