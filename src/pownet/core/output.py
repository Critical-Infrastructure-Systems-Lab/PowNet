""" output.py: Contains the OutputProcessor class, which processes the output from PowNet and provides methods to access the data.
"""

import pandas as pd

from .input import SystemInput
from pownet.data_utils import get_dates, get_fuel_mix_order


class OutputProcessor:
    def __init__(self) -> None:
        """Initialize the OutputProcessor object."""
        self.year: int = None
        self.fuelmap: dict = {}
        self.dates: pd.DataFrame = pd.DataFrame()

    def load(self, inputs: SystemInput) -> None:
        """Load the input data."""
        self.fuelmap = inputs.fuelmap
        self.year = inputs.year

        self.dates = get_dates(year=self.year)
        self.dates.index += 1

    def _get_power_variables(self, node_variables: pd.DataFrame) -> pd.DataFrame:
        power_vars = {
            "pthermal",
            "psolar",
            "pwind",
            "phydro",
            "pimp",
            "pos_pmismatch",
            "neg_pmismatch",
            "pdischarge",
            "pcharge",
        }
        power_variables = node_variables.loc[
            node_variables["vartype"].isin(power_vars)
        ].reset_index(drop=True)
        power_variables["fuel_type"] = power_variables.apply(
            lambda x: self.fuelmap.get(x["node"], None), axis=1
        )
        # These variables are missing in SystemInputs.fuelmap
        vartype_to_fuel_type = {
            "pimp": "import",
            "pos_pmismatch": "shortfall",
            "neg_pmismatch": "curtailment",
            "pdischarge": "discharging",
            "pcharge": "charging",
        }
        for vartype, fuel_type in vartype_to_fuel_type.items():
            power_variables.loc[power_variables["vartype"] == vartype, "fuel_type"] = (
                fuel_type
            )
        # Convert charging to negative values for plotting
        power_variables.loc[power_variables["vartype"] == "pcharge", "value"] *= -1
        return power_variables

    def get_unit_hourly_generation(self, node_variables: pd.DataFrame) -> pd.DataFrame:
        power_variables = self._get_power_variables(node_variables)
        hourly_generation = (
            power_variables[["node", "value", "hour"]]
            .groupby(["node", "hour"])
            .sum()
        )
        hourly_generation = hourly_generation.reset_index()
        hourly_generation = hourly_generation.pivot(
            columns=["hour"], index=["node"]
        ).T.reset_index(drop=True)
        # PowNet indexing starts at 1
        hourly_generation.index += 1
        hourly_generation.index.name = "Hour"

        return hourly_generation

    def get_hourly_generation(self, node_variables: pd.DataFrame) -> pd.DataFrame:
        power_variables = self._get_power_variables(node_variables)
        hourly_generation = (
            power_variables[["fuel_type", "value", "hour"]]
            .groupby(["fuel_type", "hour"])
            .sum()
        )
        hourly_generation = hourly_generation.reset_index()
        hourly_generation = hourly_generation.pivot(
            columns=["hour"], index=["fuel_type"]
        ).T.reset_index(drop=True)
        # PowNet indexing starts at 1
        hourly_generation.index += 1
        hourly_generation.index.name = "Hour"

        # Define the order of fuels for plotting. Baseload at the bottom,
        # renewables in the middle, then peaker plants, and shortfall
        fuel_mix_order = get_fuel_mix_order()
        fuel_mix_order = [
            fuel for fuel in fuel_mix_order if fuel in hourly_generation.columns
        ]
        hourly_generation = hourly_generation[fuel_mix_order]
        return hourly_generation

    def get_daily_generation(self, node_variables: pd.DataFrame) -> pd.DataFrame:
        hourly_generation = self.get_hourly_generation(node_variables)
        # Sum across 24 hours to get the daily dispatch.
        daily_generation = hourly_generation.groupby(
            (hourly_generation.index - 1) // 24
        ).sum()
        daily_generation.index += 1
        daily_generation.index.name = "Day"
        return daily_generation

    def get_monthly_generation(self, node_variables: pd.DataFrame) -> pd.DataFrame:
        monthly_generation = self.get_hourly_generation(node_variables)
        monthly_generation["month"] = self.dates["date"].dt.to_period("M")
        monthly_generation = monthly_generation.groupby("month").sum()
        monthly_generation.index = monthly_generation.index.strftime("%b")
        monthly_generation.index.name = "Month"
        return monthly_generation

    def get_hourly_demand(self, input_demand: pd.DataFrame) -> pd.DataFrame:
        # Demand is an input to the simulation
        hourly_demand = input_demand.sum(axis=1).to_frame()
        hourly_demand.columns = ["demand"]
        hourly_demand.index.name = "Hour"
        return hourly_demand

    def get_daily_demand(self, input_demand: pd.DataFrame) -> pd.Series:
        hourly_demand = self.get_hourly_demand(input_demand)
        # Need -1 because the index starts with 1 and we want to group by 24 hours
        daily_demand = hourly_demand.groupby((hourly_demand.index - 1) // 24).sum()
        daily_demand.index += 1
        return daily_demand

    def get_monthly_demand(self, input_demand: pd.DataFrame) -> pd.Series:
        monthly_demand = self.get_hourly_demand(input_demand)
        monthly_demand["month"] = self.dates["date"].dt.to_period("M")
        monthly_demand = monthly_demand.groupby("month").sum()
        monthly_demand.index = monthly_demand.index.strftime("%b")
        monthly_demand.index.name = "Month"
        return monthly_demand

    def get_thermal_unit_hourly_status(
        self, node_variables: pd.DataFrame
    ) -> pd.DataFrame:
        """The hourly status of thermal units for each hour over the simulation period."""
        thermal_unit_hourly_status = node_variables[
            node_variables["vartype"] == "status"
        ].reset_index(drop=True)
        thermal_unit_hourly_status["timestep"] = thermal_unit_hourly_status["hour"] % 24
        return thermal_unit_hourly_status

    def get_thermal_unit_mean_hourly_status(
        self, node_variables: pd.DataFrame
    ) -> pd.DataFrame:
        """The hourly status of thermal units for each hour over the simulation period."""
        thermal_unit_hourly_status = node_variables[
            node_variables["vartype"] == "status"
        ].reset_index(drop=True)
        thermal_unit_hourly_status["timestep"] = thermal_unit_hourly_status["hour"] % 24
        return thermal_unit_hourly_status.pivot_table(
            columns="node", index="timestep", values="value", aggfunc="mean"
        )

    def get_thermal_unit_daily_duration(
        self, node_variables: pd.DataFrame
    ) -> pd.DataFrame:
        """Return the daily online duration of each thermal unit. Rows are days and columns are units."""
        status_variables = node_variables[node_variables["vartype"] == "status"].copy()
        status_variables["day"] = (status_variables["hour"] - 1) // 24 + 1
        return status_variables.pivot_table(
            columns="node", index="day", values="value", aggfunc="sum"
        )

    def get_thermal_unit_startup_frequency(
        self, node_variables: pd.DataFrame
    ) -> pd.DataFrame:
        """Return the frequency of startups for each thermal unit over the whole simulation period."""
        startup_vars = node_variables[node_variables["vartype"] == "startup"].copy()
        startup_vars["day"] = (startup_vars["hour"] - 1) // 24 + 1
        return startup_vars.pivot_table(
            columns="node", index="day", values="value", aggfunc="sum"
        )

    def get_thermal_unit_total_duration_and_frequency(
        self, node_variables: pd.DataFrame
    ) -> pd.DataFrame:
        """Return data for histogram of frequency of startups and duration of committed hours in a year."""
        cols = ["startup", "status"]
        data = node_variables[node_variables["vartype"].isin(cols)]
        # Sum the number of startups and committed hours for each thermal unit
        return (
            data.groupby(["node", "vartype"]).sum().reset_index().drop(columns=["hour"])
        )

    def get_thermal_unit_daily_dispatch(
        self, node_variables: pd.DataFrame
    ) -> pd.DataFrame:
        pthermal = node_variables[node_variables["vartype"] == "pthermal"].copy()
        pthermal["day"] = (pthermal["hour"] - 1) // 24 + 1
        return pthermal.pivot_table(
            columns="node", index="day", values="value", aggfunc="sum"
        )

    def get_thermal_unit_hourly_dispatch(
        self, node_variables: pd.DataFrame
    ) -> pd.DataFrame:
        return node_variables[node_variables["vartype"] == "pthermal"].copy()

    def get_nondispatch_hourly_capacity_factor(
        self,
        type: str,
        node_variables: pd.DataFrame,
        unit_capacities: dict[str, float],
        energy_storage_attach: dict[str, str],
    ) -> pd.DataFrame:
        """Return the capacity factor which is a function of generation and storage charging."""
        type_map = {
            "hydropower": "phydro",
            "solar": "psolar",
            "wind": "pwind",
            "import": "pimp",
        }
        # Power output variables
        generation = (
            node_variables[node_variables["vartype"] == type_map[type]]
            .copy()
            .drop(columns=["vartype"])
        )
        units = generation["node"].unique()
        generation = generation.set_index(["node", "hour"])

        # Process charging variables
        charging = node_variables[node_variables["vartype"] == "pcharge"].copy()
        if not charging.empty:
            charging["unit"] = charging.apply(
                lambda x: energy_storage_attach.get(x["node"], None), axis=1
            )
            charging = charging[charging["unit"].isin(units)]
            charging = charging.drop(columns=["vartype", "node"]).set_index(
                ["unit", "hour"]
            )
        # Capacity factor is the sum of generation and charging divided by the unit capacity
        output = generation + charging
        output = output.reset_index()
        output["capacity_factor"] = output.apply(
            lambda x: x["value"] / unit_capacities[x["node"]], axis=1
        )
        return output.pivot(columns="node", index="hour", values="capacity_factor")

    def get_energy_storage_hourly_charge(
        self, node_variables: pd.DataFrame
    ) -> pd.DataFrame:
        hourly_charge = (
            node_variables[node_variables["vartype"] == "pcharge"]
            .copy()
            .drop(columns=["vartype"])
        )
        return hourly_charge.pivot(columns="node", index="hour", values="value")

    def get_energy_storage_hourly_discharge(
        self, node_variables: pd.DataFrame
    ) -> pd.DataFrame:
        hourly_discharge = (
            node_variables[node_variables["vartype"] == "pdischarge"]
            .copy()
            .drop(columns=["vartype"])
        )
        return hourly_discharge.pivot(columns="node", index="hour", values="value")

    def _get_hourly_charge_state_fraction(
        self, node_variables: pd.DataFrame, max_storage: dict[str, float]
    ) -> pd.DataFrame:
        hourly_state = (
            node_variables[node_variables["vartype"] == "charge_state"]
            .copy()
            .drop(columns=["vartype"])
        )
        hourly_state["storage_fraction"] = hourly_state.apply(
            lambda x: x["value"] / max_storage[x["node"]], axis=1
        )
        return hourly_state

    def get_energy_storage_hourly_state(
        self,
        node_variables: pd.DataFrame,
        max_storage: dict[str, float],
    ) -> pd.DataFrame:
        hourly_storage_state = self._get_hourly_charge_state_fraction(
            node_variables, max_storage
        )
        return hourly_storage_state.pivot(
            columns="node", index="hour", values="storage_fraction"
        )

    def get_energy_storage_daily_state(
        self,
        node_variables: pd.DataFrame,
        max_storage: dict[str, float],
    ) -> pd.DataFrame:
        hourly_storage_state = self._get_hourly_charge_state_fraction(
            node_variables, max_storage
        )
        hourly_storage_state["day"] = (hourly_storage_state["hour"] - 1) // 24 + 1
        return hourly_storage_state.pivot_table(
            columns="node", index="day", values="storage_fraction", aggfunc="last"
        )

    def get_import_values(self, node_variables: pd.DataFrame) -> pd.DataFrame:
        """Return the import values for each timestep. Columns are generators.
        Index is the hour in the simulation year"""
        power_variables = self._get_power_variables(node_variables)
        import_values = power_variables[power_variables["vartype"] == "pimp"]
        import_values = import_values.pivot(
            columns="node", index="hour", values="value"
        )
        return import_values

    def get_co2_emission(self, co2_map: dict[str:float]) -> pd.DataFrame:
        """Return the CO2 emissions for timestep.
        From Chowdhury, Dang, Nguyen, Koh, & Galelli. (2021).

        coal: 1.04 Mton/MWh
        gas:  0.47 Mton/MWh
        oil : 0.73 Mton/MWh
        solid_waste: 0.170 Mton/MWh

        From https://www.eia.gov/environment/emissions/co2_vol_mass.php:
        solid_waste: 49.89 kg/MMBtu
              = 49.89 kg/MMBtu * 3.412 MMBtu/MWh * 1 Mton/1000 kg = 0.170
        """
        if co2_map is None:
            co2_map = {
                "coal": 1.04,
                "gas": 0.47,
                "oil": 0.73,
                "import": 0.0,
                "shortfall": 0.0,
                "curtailment": 0.0,
                "biomass": 0.0,
                "solid_waste": 0.170,
                "slack": 0.0,
            }

        df = self.get_hourly_thermal_dispatch()
        co2_emissions = pd.DataFrame()
        for fuel in df.columns:
            co2_emissions[fuel] = df[fuel] * co2_map[fuel]
        return co2_emissions

    def get_max_line_usage(
        self,
        flow_variables: pd.DataFrame,
        line_locations: pd.DataFrame,
        rated_line_capacities: dict[tuple[str, str], int],
    ) -> pd.DataFrame:

        # Prevent unintentional modification to the original dataframe
        flow_variables = flow_variables.copy()

        flow_variables = flow_variables.rename(
            columns={"node_a": "source", "node_b": "sink"}
        ).drop("hour", axis=1)
        # Flow can be negative due to flow being directional
        flow_variables["value"] = flow_variables["value"].abs()

        # Find the max_value for each line segment across the whole time horizon
        flow_variables["max_value"] = flow_variables.groupby(["source", "sink"])[
            "value"
        ].transform("max")
        # Drop duplicates because we are only interested in the maximum flow
        # over the whole simulation
        flow_variables = flow_variables.drop_duplicates(subset=["source", "sink"])

        # Max utilization rate
        flow_variables["max_line_usage"] = flow_variables.apply(
            lambda row: row["max_value"]
            / rated_line_capacities[(row["source"], row["sink"])],
            axis=1,
        ).round(4)

        flow_variables = flow_variables[["source", "sink", "max_line_usage"]].set_index(
            ["source", "sink"]
        )
        flow_variables = flow_variables.merge(
            line_locations, how="left", left_index=True, right_index=True
        )
        # Append rated capacities
        flow_variables["rated_capacity"] = [
            rated_line_capacities[idx] for idx in flow_variables.index
        ]
        return flow_variables

    def get_fuel_mix(self, hourly_generation: pd.DataFrame) -> pd.DataFrame:
        """Return the fuel mix (%) for the whole simulation period."""
        return (hourly_generation.sum() / hourly_generation.sum().sum()).round(4) * 100

    def get_gen_by_fuel(self, hourly_generation: pd.DataFrame) -> pd.DataFrame:
        """Return the total generation for the whole simulation period."""
        return hourly_generation.sum().round(0)

    def get_curtailed_power(self):
        """Return the statistics of curtailed energy by hydro, solar, wind, and import."""
        pass

    def get_contract_hourly_generation(
        self, node_variables: pd.DataFrame, unit_contract: dict[str, str]
    ) -> pd.DataFrame:
        power_variables = self._get_power_variables(node_variables)
        vartypes = ["pthermal", "phydro", "psolar", "pwind", "pimp", "pdischarge"]
        power_variables = power_variables[power_variables["vartype"].isin(vartypes)]
        power_variables["contract"] = power_variables.apply(
            lambda x: unit_contract.get(x["node"], None), axis=1
        )
        return power_variables[["contract", "hour", "value"]]

    def get_contract_generation(
        self, node_variables: pd.DataFrame, unit_contract: dict[str, str]
    ) -> pd.DataFrame:
        hourly_generation = self.get_contract_hourly_generation(
            node_variables=node_variables, unit_contract=unit_contract
        )
        return hourly_generation[["contract", "value"]].groupby("contract").sum()

    def get_contract_cost(
        self,
        node_variables: pd.DataFrame,
        unit_contract: dict[str, str],
        contract_costs: dict[str, float],
    ) -> pd.DataFrame:
        hourly_generation = self.get_contract_hourly_generation(
            node_variables=node_variables, unit_contract=unit_contract
        )
        hourly_generation["cost"] = hourly_generation.apply(
            lambda x: x["value"] * contract_costs[(x.contract, x.hour)], axis=1
        )
        return (
            hourly_generation.drop(columns=["hour", "value"]).groupby("contract").sum()
        )
