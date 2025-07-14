"""data_processor.py: This file contains the DataProcessor class that processes the data provided by the user."""

import json
import os

import networkx as nx
import numpy as np
import pandas as pd

from pownet.folder_utils import get_database_dir
from pownet.data_utils import get_dates


class DataProcessor:
    def __init__(
        self, input_folder: str, model_name: str, year: int, frequency: int
    ) -> None:
        """The DataProcessor class is used to process the data provided by the user. The data
        is stored in the model_library/model_name folder. The required files are:

        1. transmission.csv: A file that contains the transmission data.
        2. thermal_unit.csv: A file that contains the thermal unit data.
        3. solar.csv, wind.csv, hydropower.csv, import.csv: Files that contain the renewable unit data.
        4. energy_storage.csv: A file that contains the energy storage system data.

        """
        self.input_folder = input_folder
        self.model_name = model_name
        self.year = year
        self.frequency = frequency

        # Values that will be calculated
        self.cycle_map: dict = json.loads("{}")
        self.thermal_derate_factors: pd.DataFrame = pd.DataFrame()
        self.thermal_derated_capacity: pd.DataFrame = pd.DataFrame()

        self.transmission_data: pd.DataFrame = pd.DataFrame()
        self.transmission_params: dict = {}  # Default PowNet parameters
        self.user_transmission: pd.DataFrame = pd.DataFrame()

        self.ess_derate_factors: pd.DataFrame = pd.DataFrame()
        self.ess_derated_capacity: pd.DataFrame = pd.DataFrame()

        # Maps frequency to wavelength
        wavelengths = {50: 6000, 60: 5000}
        self.wavelength = wavelengths[frequency]

        # Note that we will modify the original file
        self.model_folder = os.path.join(self.input_folder, model_name)

    def load_transmission_data(self) -> None:
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
        n_circuits: int,
    ) -> float:
        """Calculates the theoretical steady-state stability limit of a transmission line.
        
        This function uses the fundamental power transfer formula based on total line 
        reactance, as shown in "Power System Analysis and Design" (Eq. 5.4.27):

            P_max = (V_S * V_R) / X'

        where:
            P_max is the stability limit in MW.
            V_S and V_R are the sending and receiving end voltages in kV.
            X' is the total line reactance in ohms.

        Args:
            source_kv (int): Voltage level of the source bus in kV.
            sink_kv (int): Voltage level of the sink bus in kV.
            distance (float): Distance between the two buses in km.
            n_circuits (int): Number of circuits in the transmission line.

        Returns:
            float: The stability limit of the transmission line in MW.
        """
        # Get the reactance per kilometer for the line's voltage level.
        max_kv = max(source_kv, sink_kv)
        reactance_per_km = self.transmission_params["reactance_ohms_per_km"][max_kv]

        # 1. Calculate the TOTAL line reactance.
        total_reactance = reactance_per_km * distance

        # Avoid division by zero for co-located buses (distance = 0).
        if total_reactance == 0:
            return float('inf')

        # 2. Calculate the stability limit per circuit.
        # The result is in MW because (kV * kV) / ohms = MVA. We assume a 
        # power factor of 1 (MW = MVA).
        stability_limit_per_circuit = (source_kv * sink_kv) / total_reactance

        # 3. Return the total limit for all circuits.
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

        Note the calculated values are overwritten by user provided values
        in the transmission.csv file.
        """
        self.transmission_data["stability_limit"] = self.user_transmission.apply(
            lambda x: self.calc_stability_limit(
                x["source_kv"],
                x["sink_kv"],
                x["distance"],
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

        # Overwrite calculated values with user provided values
        excluded_list = [-1, None]
        user_specified_capacity = self.user_transmission.loc[
            ~self.user_transmission["user_line_cap"].isin(excluded_list)
        ]
        user_specified_capacity = user_specified_capacity.set_index(
            ["source", "sink"]
        ).rename(columns={"user_line_cap": "line_capacity"})

        self.transmission_data = self.transmission_data.set_index(["source", "sink"])
        self.transmission_data.update(user_specified_capacity)
        self.transmission_data = self.transmission_data.reset_index()

    def calc_line_susceptance(self) -> None:
        """Calculate the susceptance of line segments. The unit is in Siemens (S)."""

        # TODO: This is a misnomer as we are calculating the maximum power that
        # can be transferred over the line, not the susceptance.

        # Assume reactance based on the maximum voltage level of the two buses
        self.transmission_data["max_kv"] = self.user_transmission.apply(
            lambda x: max(x["source_kv"], x["sink_kv"]), axis=1
        )

        self.transmission_data["reactance_per_km"] = self.transmission_data.apply(
            lambda x: self.transmission_params["reactance_ohms_per_km"][x["max_kv"]],
            axis=1,
        )

        self.transmission_data["reactance"] = (
            self.transmission_data["reactance_per_km"]
            * self.user_transmission["distance"]
        )

        self.transmission_data["susceptance"] = self.transmission_data.apply(
            lambda x: int(x["source_kv"] * x["sink_kv"] / x["reactance"]),
            axis=1,
        )

        # Raise an error if there are other values other than -1 or None
        if not self.user_transmission["user_susceptance"].isin([-1, None]).all():
            raise ValueError(
                "Currently does not support user specified susceptance values."
            )

        # TODO: Revise the following code
        # # Replace with user-specified values
        # excluded_values = [-1, None]
        # user_specified_susceptance = self.user_transmission.loc[
        #     ~self.user_transmission["user_susceptance"].isin(excluded_values),
        #     ["source", "sink", "user_susceptance"],
        # ]
        # user_specified_susceptance = user_specified_susceptance.set_index(
        #     ["source", "sink"]
        # )
        # # Change from float to int
        # user_specified_susceptance = user_specified_susceptance.astype(
        #     {"user_susceptance": int}
        # )

        self.transmission_data = self.transmission_data.set_index(["source", "sink"])
        # self.transmission_data.update(user_specified_susceptance)
        self.transmission_data = self.transmission_data.reset_index()

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
        # Save this map to be uses by ModelBuilder
        self.cycle_map = {f"cycle_{idx + 1}": cycle for idx, cycle in enumerate(cycles)}

    def write_cycle_map(self) -> None:
        """
        Save the cycle map to a json file in model_library/{model_name}.
        The key is the cycle name and the value is a list of nodes in the cycle.
        """
        with open(os.path.join(self.model_folder, "pownet_cycle_map.json"), "w") as f:
            json.dump(self.cycle_map, f)

    def _create_derate_factors(
        self, unit_type: str, derate_factor: float = 1.00
    ) -> None:
        """Creates derate factors for a given unit type (thermal or ess).

        Args:
            unit_type (str): The type of unit ('thermal' or 'ess').
            derate_factor (float): The derate factor to apply. Defaults to 1.00.
        """

        model_dir = os.path.join(self.input_folder, self.model_name)

        if unit_type == "thermal":
            filename = "thermal_unit.csv"
            attribute_name = "thermal_derate_factors"
        elif unit_type == "ess":
            filename = "energy_storage.csv"
            attribute_name = "ess_derate_factors"
        else:
            raise ValueError(
                f"Invalid unit type: {unit_type}. Must be 'thermal' or 'ess'."
            )

        if os.path.exists(os.path.join(model_dir, filename)):
            units = pd.read_csv(os.path.join(model_dir, filename))["name"].values
        else:
            return

        num_hrs_in_year = 8760
        temp_df = pd.DataFrame(
            derate_factor,
            index=range(0, num_hrs_in_year),
            columns=units,
        )
        setattr(
            self,
            attribute_name,
            pd.concat([get_dates(year=self.year), temp_df], axis=1),
        )

    def create_thermal_derate_factors(self, derate_factor: float = 1.00) -> None:
        """Creates derate factors for thermal units."""
        self._create_derate_factors("thermal", derate_factor)

    def create_ess_derate_factors(self, derate_factor: float = 1.00) -> None:
        """Creates derate factors for ESS units."""
        self._create_derate_factors("ess", derate_factor)

    def write_thermal_derate_factors(self) -> None:
        self.thermal_derate_factors.to_csv(
            os.path.join(self.model_folder, "pownet_derate_factor.csv"), index=False
        )

    def _create_derated_capacity(self, unit_type: str) -> None:
        """Creates a dataframe of hourly derated capacity for a given unit type.

        Args:
            unit_type (str): The type of unit ('thermal' or 'ess').
        """

        if unit_type == "thermal":
            filename = "thermal_unit.csv"
            derate_factor_attr = "thermal_derate_factors"
            derated_capacity_attr = "thermal_derated_capacity"
        elif unit_type == "ess":
            filename = "energy_storage.csv"
            derate_factor_attr = "ess_derate_factors"
            derated_capacity_attr = "ess_derated_capacity"
        else:
            raise ValueError(
                f"Invalid unit type: {unit_type}. Must be 'thermal' or 'ess'."
            )

        # Get the nameplate capacity of each unit
        filepath = os.path.join(self.model_folder, filename)
        if os.path.exists(filepath):
            max_cap = pd.read_csv(
                filepath,
                index_col="name",
                usecols=["name", "max_capacity"],
            )[
                "max_capacity"
            ]  # Directly get the Series
        else:
            return

        # Get the derate factors for the units
        derate_factors = getattr(self, derate_factor_attr)

        # Efficiently calculate derated capacity using vectorized operations
        derated_capacity = derate_factors.drop(columns=["date", "hour"]).mul(
            max_cap, axis=1
        )

        # Concatenate with dates and set the index
        derated_capacity = pd.concat(
            [get_dates(year=self.year), derated_capacity], axis=1
        )
        derated_capacity.index += 1

        setattr(self, derated_capacity_attr, derated_capacity)

    def create_thermal_derated_capacity(self) -> None:
        """Creates a dataframe of hourly derated capacity of thermal units."""
        self._create_derated_capacity("thermal")

    def create_ess_derated_capacity(self) -> None:
        """Creates a dataframe of hourly derated capacity of ess units."""
        self._create_derated_capacity("ess")

    def write_thermal_derated_capacity(self) -> None:
        if not self.thermal_derate_factors.empty:
            self.thermal_derated_capacity.to_csv(
                os.path.join(self.model_folder, "pownet_thermal_derated_capacity.csv"),
                index=False,
            )

    def write_ess_derated_capacity(self) -> None:
        if not self.ess_derated_capacity.empty:
            self.ess_derated_capacity.to_csv(
                os.path.join(self.model_folder, "pownet_ess_derated_capacity.csv"),
                index=False,
            )

    def check_user_line_capacities(self) -> None:
        """The user can provide their own line capacities under user_line_cap column
        in transmission.csv. If this is the case, then it will be used instead of the
        calculated line capacities.
        """
        pass

    def run_all_processing_steps(self) -> None:
        """Run all the data processing steps"""
        if not self.user_transmission.empty:
            self.calc_line_capacity()
            self.calc_line_susceptance()
            self.create_cycle_map()

        self.create_thermal_derate_factors()
        self.create_thermal_derated_capacity()

        self.create_ess_derate_factors()
        self.create_ess_derated_capacity()

    def write_data(self) -> None:
        """Write the processed data as csv files sharing a prefix `pownet_` to the model folder"""

        if not self.transmission_data.empty:
            self.write_transmission_data()
            self.write_cycle_map()

        self.write_thermal_derated_capacity()
        self.write_ess_derated_capacity()

    def execute_data_pipeline(self) -> None:
        if os.path.exists(os.path.join(self.model_folder, "transmission.csv")):
            self.load_transmission_data()

        self.run_all_processing_steps()
        self.write_data()
