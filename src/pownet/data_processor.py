""" data_processor.py: This file contains the DataProcessor class that processes the data provided by the user.
"""

import json
import os

import networkx as nx
import numpy as np
import pandas as pd

from .folder_utils import get_model_dir, get_database_dir
from .data_utils import get_dates


class DataProcessor:
    def __init__(self, model_name: str, year: int, frequency: int) -> None:
        """The DataProcessor class is used to process the data provided by the user. The data
        is stored in the model_library/model_name folder. The required files are:
        1. transmission.csv: A file that contains the transmission data.
        2. thermal_unit.csv: A file that contains the thermal unit data.
        3. unit_marginal_cost.csv: A file that contains the marginal cost of non-thermal units.
        4. (Optional) solar.csv, wind.csv, hydropower.csv, import.csv: Files that contain the renewable unit data.
        """
        self.model_name = model_name
        self.year = year
        self.frequency = frequency

        # Values that will be calculated
        self.cycle_map: dict = {}
        self.thermal_derate_factors: pd.DataFrame = get_dates(year)
        self.marginal_costs: pd.DataFrame = get_dates(year)

        # Maps frequency to wavelength
        wavelengths = {50: 6000, 60: 5000}
        self.wavelength = wavelengths[frequency]

        # Note that we will modify the original file
        self.model_folder = os.path.join(get_model_dir(), model_name)

    def load_data(self) -> None:
        # User inputs of transmission data
        self.user_transmission = pd.read_csv(
            os.path.join(self.model_folder, "transmission.csv"),
            header=0,
        )

        # First check that there are no repeated edges in the transmission data
        # Here, only one direction is needed. If the reverse direction is also
        # present, then it is a repeated edge.
        edges = self.user_transmission[["source", "sink"]].values
        reversed_edges = np.flip(edges, axis=1)
        edges_set = set(map(tuple, edges))
        reversed_edges_set = set(map(tuple, reversed_edges))
        repeated_edges = edges_set.intersection(reversed_edges_set)
        if len(repeated_edges) > 0:
            raise ValueError(
                f"There are repeated edges in the transmission data: {repeated_edges}"
            )

        # Generic transmission parameters for a power system
        self.transmission_params: dict = (
            pd.read_csv(
                os.path.join(get_database_dir(), "transmission_params.csv"), header=0
            )
            .set_index("kv")
            .to_dict(orient="dict")
        )
        # Calculated transmission data
        self.transmission_data: pd.DataFrame = self.user_transmission[
            ["source", "sink", "source_kv", "sink_kv"]
        ].copy()

    def calc_stability_limit(
        self,
        source_kv: int,
        sink_kv: int,
        distance: float,
        wavelength: int,
        n_circuits: int,
    ) -> float:
        """This function calculates the steady-state stability limit of a transmission line.
        From Chapter 5 of Power System Analysis and Design 5th (EQ 5.4.30)

        The stability limit per circuit is given by:
                P = V1 * V2 / X * sin(2 * pi * d / lambda)
            where:
                P is the stability limit in MW
                V1 and V2 are the voltages at the two ends of the line
                X is the reactance of the line in ohms per km
                d is the distance between the two ends of the line in km
                lambda is the wavelength of the system in km

        Args:
            source_kv (int): Voltage level of the source bus
            sink_kv (int): Voltage level of the sink bus
            distance (float): Distance between the two buses in km
            wavelength (int): Wavelength of the system in km
            n_circuits (int): Number of circuits in the transmission line

        Returns:
            float: The stability limit of the transmission line in MW
        """
        # The reactance of the line is a function of the maximum voltage level
        # of the two buses.
        max_kv = max(source_kv, sink_kv)
        reactance_per_km = self.transmission_params["reactance_ohms_per_km"][max_kv]
        # Calculate the Surge Impedance Limit (SIL)
        sil = source_kv * sink_kv / reactance_per_km / 1000  # Divide by 1000 to get MW
        stability_limit_per_circuit = sil / np.sin(2 * np.pi * distance / wavelength)
        return int(n_circuits * stability_limit_per_circuit)

    def calc_thermal_limit(
        self, source_kv: int, sink_kv: int, n_circuits: int
    ) -> float:
        """From Chapter 5 of Power System Analysis and Design 5th. See Example 5.6b.
        The full-load current at 1 per-unit factor is
              I = P/(sqrt(3) * V)
        Here, P is the surge impedance factor (SIL) and V is the voltage of the
        receiving bus. This voltage is the minimum voltage between the two ends.

        Args:
            source_kv (int): Voltage level of the source bus
            sink_kv (int): Voltage level of the sink bus
            n_circuits (int): Number of circuits in the transmission line

        Returns:
            float: The thermal limit of the transmission line in MW
        """
        max_kv = max(source_kv, sink_kv)
        n_conductors = self.transmission_params["n_conductors"][max_kv]
        # in Amps
        current_capacity = self.transmission_params["current_capacity_amps"][max_kv]
        total_current_capacity = n_conductors * current_capacity / 1000  # in kilo-A
        thermal_limit_per_circuit = total_current_capacity * np.sqrt(3) * max_kv
        return int(n_circuits * thermal_limit_per_circuit)

    def calc_line_capacity(self) -> None:
        """Calculate the capacity of line segments. The unit is in MW.
        Line capacity is the minimum of the thermal limit and the steady-state
        stability limit (a function of distance).
        """
        self.transmission_data["stability_limit"] = self.user_transmission.apply(
            lambda x: self.calc_stability_limit(
                x["source_kv"],
                x["sink_kv"],
                x["distance"],
                self.wavelength,
                x["n_circuits"],
            ),
            axis=1,
        )

        self.transmission_data["thermal_limit"] = self.user_transmission.apply(
            lambda x: self.calc_thermal_limit(
                x["source_kv"], x["sink_kv"], x["n_circuits"]
            ),
            axis=1,
        )
        # The transmission limit is the minimum of the thermal limit and
        # the steady-state steability limit (a function of distance).
        # Normally, distance is the deciding factor.
        self.transmission_data["line_capacity"] = self.transmission_data[
            ["thermal_limit", "stability_limit"]
        ].min(axis=1)

    def calc_line_susceptance(self) -> None:
        """Calculate the susceptance of line segments. The unit is in Siemens (S)."""
        # Assume reactance based on the maximum voltage level of the two buses
        self.transmission_data["max_kv"] = self.user_transmission.apply(
            lambda x: max(x["source_kv"], x["sink_kv"]), axis=1
        )

        self.transmission_data["reactance_per_km"] = self.transmission_data.apply(
            lambda x: self.transmission_params["reactance_ohms_per_km"][x["max_kv"]],
            axis=1,
        )

        self.transmission_data["reactance_pu"] = (
            self.transmission_data["reactance_per_km"]
            * self.user_transmission["distance"]
        )

        self.transmission_data["susceptance"] = self.transmission_data.apply(
            lambda x: int(x["source_kv"] * x["sink_kv"] / x["reactance_pu"]),
            axis=1,
        )

    def write_transmission_data(self) -> None:
        self.transmission_data.to_csv(
            os.path.join(self.model_folder, "pownet_transmission.csv"), index=False
        )

    def create_cycle_map(self) -> None:
        """
        Create a cycle map for the power system. This is used to create the
        cycle constraints in the optimization model. The cycle map is a dictionary
        where the key is the cycle name and the value is a list of nodes in the cycle.
        """
        graph = nx.from_pandas_edgelist(
            self.transmission_data,
            source="source",
            target="sink",
        )
        cycles = nx.cycle_basis(graph)
        # We save this map to use by the ModelBuilder
        self.cycle_map = {f"cycle_{idx+1}": cycle for idx, cycle in enumerate(cycles)}

    def write_cycle_map(self) -> None:
        """
        Save the cycle map to a json file in model_library/{model_name}.
        The key is the cycle name and the value is a list of nodes in the cycle.
        """
        with open(os.path.join(self.model_folder, "pownet_cycle_map.json"), "w") as f:
            json.dump(self.cycle_map, f)

    def create_thermal_derate_factors(self, derate_factor: float = 1.00) -> None:
        """Assumes a constant derate factor for all thermal units. The derate factor is applied
        to the nameplate capacity of thermal units.
        """
        # Get the thermal units
        model_dir = os.path.join(get_model_dir(), self.model_name)
        thermal_units = pd.read_csv(os.path.join(model_dir, "thermal_unit.csv"))[
            "name"
        ].values
        temp_df = pd.DataFrame(
            derate_factor,
            index=self.thermal_derate_factors.index,
            columns=thermal_units,
        )
        self.thermal_derate_factors = pd.concat(
            [get_dates(year=self.year), temp_df], axis=1
        )

    def write_thermal_derate_factors(self) -> None:
        self.thermal_derate_factors.to_csv(
            os.path.join(self.model_folder, "pownet_derate_factor.csv"), index=False
        )

    def create_derated_capacity(self) -> None:
        """Create a dataframe of hourly derated capacity of thermal units. The columns are names of thermal units."""
        # Get the nameplate capacity of each thermal unit
        max_cap = pd.read_csv(
            os.path.join(self.model_folder, "thermal_unit.csv"),
            header=0,
            index_col="name",
            usecols=["name", "max_capacity"],
        ).to_dict()["max_capacity"]

        self.derated_max_cap = pd.DataFrame(
            0,
            columns=max_cap.keys(),
            index=range(0, 8760),  # match index with get_dates
        )
        for thermal_unit in max_cap.keys():
            self.derated_max_cap[thermal_unit] = (
                self.thermal_derate_factors[thermal_unit] * max_cap[thermal_unit]
            )

        self.derated_max_cap = pd.concat(
            [get_dates(year=self.year), self.derated_max_cap], axis=1
        )
        self.derated_max_cap.index += 1

    def write_derated_capacity(self) -> None:
        self.derated_max_cap.to_csv(
            os.path.join(self.model_folder, "pownet_derated_capacity.csv"), index=False
        )

    def create_marginal_costs(self) -> None:
        """Create a dataframe of hourly fuel prices (or marginal costs) of non-thermal units.
        The columns are names of renewable and import units. The marginal cost is in $/MWh.
        """
        # unit_marginal_cost.csv has three columns: name, fuel_type, and marginal_cost.
        # Now, we create a fuel_type to marginal_cost mapping
        constant_prices = pd.read_csv(
            os.path.join(self.model_folder, "unit_marginal_cost.csv"),
            header=0,
            index_col="fuel_type",
        ).to_dict()["marginal_cost"]

        # If there are solar.csv, hydropower.csv, and wind.csv files, then we need to
        # include them in the fuel price file.
        hours_in_year = range(8760)
        unit_types = ["solar", "wind", "hydropower", "import"]
        for unit_type in unit_types:
            filename = os.path.join(self.model_folder, f"{unit_type}.csv")
            if os.path.exists(filename):
                units = pd.read_csv(filename, header=0).columns
                units = units.drop(
                    ["year", "month", "day", "hour"], errors="ignore"
                ).to_list()
                temp_df = pd.DataFrame(
                    constant_prices[unit_type],
                    index=hours_in_year,
                    columns=units,
                )
                self.marginal_costs = pd.concat(
                    [
                        self.marginal_costs,
                        temp_df,
                    ],
                    axis=1,
                )

    def write_marginal_costs(self) -> None:
        self.marginal_costs.to_csv(
            os.path.join(self.model_folder, "pownet_marginal_cost.csv"), index=False
        )

    def check_user_line_capacities(self) -> None:
        """The user can provide their own line capacities under user_line_cap column
        in transmission.csv. If this is the case, then it will be used instead of the
        calculated line capacities.
        """
        pass

    def run_all_processing_steps(self) -> None:
        """Run all the data processing steps"""
        self.calc_line_capacity()
        self.calc_line_susceptance()
        self.create_cycle_map()
        self.create_thermal_derate_factors()
        self.create_derated_capacity()
        self.create_marginal_costs()

    def write_data(self) -> None:
        """Write the processed data as csv files sharing a prefix "pownet_" to the model folder"""
        self.write_transmission_data()
        self.write_cycle_map()
        self.write_thermal_derate_factors()
        self.write_derated_capacity()
        self.write_marginal_costs()

    def execute_data_pipeline(self) -> None:
        self.load_data()
        self.run_all_processing_steps()
        self.write_data()
