"""input.py: SystemInput class loads and checks the input data. It is used by other PowNet objects to access the input data."""

from datetime import datetime
import logging
import json
import os
import textwrap

import gurobipy as gp
from gurobipy import GRB
import pandas as pd

logger = logging.getLogger(__name__)


class SystemInput:
    def __init__(
        self,
        input_folder: str,
        model_name: str,
        year: int,
        sim_horizon: int,
        num_sim_days: int = 365,
        use_spin_var: bool = True,
        dc_opf: str = "kirchhoff",
        use_nondispatch_status_var: bool = False,
        spin_reserve_factor: float = 0.15,
        spin_reserve_mw: float = None,
        gen_loss_factor: float = 0.01,
        line_loss_factor: float = 0.0001,
        line_capacity_factor: float = 0.9,
        load_shortfall_penalty_factor: float = 1000,
        load_curtail_penalty_factor: float = 1000,
        spin_shortfall_penalty_factor: float = 900,
        ess_discharge_shortfall_penalty_factor: float = 900,
    ) -> None:
        """This class reads the input data for the power system model.

        Args:
            input_folder (str): Path to the folder containing the input data.
            model_name (str): Name of the model.
            year (int): Year of the simulation.
            sim_horizon (int): Simulation horizon in hours.
            num_sim_days (int): Number of days in the simulation. Default is 365.
            use_spin_var (bool): Whether to use spin reserve variable. Default is True.
            use_nondispatch_status_var (bool): Whether to use nondispatch status variable. Default is False.
            dc_opf (str): DC OPF formulation. Can be "kirchhoff" or "voltage_angle". Default is "kirchhoff".
            spin_reserve_factor (float): Spin reserve factor. Default is 0.15.
            spin_reserve_mw (float): Spin reserve in MW. Default is None.
            gen_loss_factor (float): Generator loss factor. Default is 0.01.
            line_loss_factor (float): Line loss factor. Default is 0.0001.
            line_capacity_factor (float): Line capacity factor. Default is 0.9.
            load_shortfall_penalty_factor (float): Load shortfall penalty factor. Default is 1000.
            load_curtail_penalty_factor (float): Load curtail penalty factor. Default is 1000.
            spin_shortfall_penalty_factor (float): Spin shortfall penalty factor. Default is 900.
            ess_discharge_shortfall_penalty_factor (float): ESS discharge shortfall penalty factor. Default is 900.
        """

        self.model_name: str = model_name
        self.model_dir: str = os.path.join(input_folder, model_name)
        self.year: int = year
        self.sim_horizon: int = sim_horizon

        self.num_sim_days: int = num_sim_days
        self.num_sim_hours: int = num_sim_days * 24

        # Choose to use these variables or not
        self.use_spin_var: bool = use_spin_var
        self.use_nondispatch_status_var: bool = use_nondispatch_status_var

        # The timestamp is used to create a unique folder for the model
        self.timestamp: str = datetime.now().strftime("%Y%m%d_%H%M")

        self.model_id: str = f"{self.timestamp}_{self.model_name}_{self.sim_horizon}"

        # DC representation of the power flow model
        if dc_opf not in ["kirchhoff", "voltage_angle"]:
            raise ValueError(
                "PowNet: Line flow must be either 'kirchhoff' or 'voltage_angle'."
            )
        self.dc_opf: str = dc_opf

        # The spin reserve factor is a fraction of total demand, so should be between 0 and 1
        if not 0 <= spin_reserve_factor <= 1:
            raise ValueError("PowNet: Spin reserve factor must be between 0 and 1.")
        self.spin_reserve_factor: float = spin_reserve_factor
        self.spin_reserve_mw: float = spin_reserve_mw

        self.gen_loss_factor: float = gen_loss_factor
        self.line_loss_factor: float = line_loss_factor

        # The line capacity factor is the fraction of the line capacity
        # that can be used. It is used to account for the uncertainty in
        # the line capacity.
        self.line_capacity_factor: float = line_capacity_factor

        # The shortfall penalty is the cost of not meeting the demand. (USD/MWh)
        self.load_shortfall_penalty_factor: float = load_shortfall_penalty_factor
        self.load_curtail_penalty_factor: float = load_curtail_penalty_factor

        # The reserve penalty is the cost of not meeting the reserve requirement. (USD/MWh)
        self.spin_shortfall_penalty_factor: float = spin_shortfall_penalty_factor

        # The energy storage system discharge shortfall penalty. (USD/MWh)
        self.ess_discharge_shortfall_penalty_factor: float = (
            ess_discharge_shortfall_penalty_factor
        )

        #################
        # Complex attributes that will be defined in load_data
        #################

        # Thermal units
        self.thermal_unit_node: dict[str, str] = {}

        self.thermal_fixed_cost: dict[str, float] = {}
        self.thermal_opex: dict[str, float] = {}
        self.thermal_startup_cost: dict[str, float] = {}
        self.thermal_heat_rate: dict[str, float] = {}

        self.thermal_rated_capacity: dict[str, float] = {}
        self.thermal_derated_capacity: pd.DataFrame = pd.DataFrame()
        self.thermal_min_capacity: dict[str, float] = {}

        self.TD: dict[str, int] = {}
        self.TU: dict[str, int] = {}
        self.SD: dict[str, float] = {}
        self.SU: dict[str, float] = {}
        self.RD: dict[str, float] = {}
        self.RU: dict[str, float] = {}

        # Energy storage
        self.ess_unit_attach: dict[str, str] = {}
        self.ess_attach_unit: dict[str, list[str]] = {}

        self.ess_hydro_units: dict[str, list[str]] = {}
        self.ess_daily_hydro_units: dict[str, list[str]] = {}
        self.ess_weekly_hydro_units: dict[str, list[str]] = {}
        self.ess_solar_units: dict[str, list[str]] = {}
        self.ess_wind_units: dict[str, list[str]] = {}
        self.ess_thermal_units: dict[str, list[str]] = {}
        self.ess_substation_units: dict[str, list[str]] = {}

        self.ess_max_charge: dict[str, float] = {}
        self.ess_max_discharge: dict[str, float] = {}
        self.ess_max_capacity: dict[str, float] = {}
        self.ess_min_capacity: dict[str, float] = {}
        self.ess_charge_efficiency: dict[str, float] = {}
        self.ess_discharge_efficiency: dict[str, float] = {}
        self.ess_self_discharge_rate: dict[str, float] = {}
        self.ess_derated_capacity: pd.DataFrame = pd.DataFrame()

        self.ess_unit_node: dict[str, str] = {}

        # Demand
        self.demand: pd.DataFrame = pd.DataFrame()
        self.total_demand: pd.Series = pd.Series()
        self.demand_nodes: list[str] = []
        self.max_demand_node: str = ""

        # Hydropower (hourly and daily timeseries)
        self.hydro_contracted_capacity: dict[str, float] = {}
        self.hydro_capacity: pd.DataFrame = pd.DataFrame()
        self.hydro_min_capacity: pd.DataFrame = pd.DataFrame()
        self.hydro_max_capacity: dict[str, float] = {}
        self.hydro_unit_node: dict[str, str] = {}
        self.daily_hydro_capacity: pd.DataFrame = pd.DataFrame()
        self.daily_hydro_unit_node: dict[str, str] = {}
        self.weekly_hydro_capacity: pd.DataFrame = pd.DataFrame()
        self.weekly_hydro_unit_node: dict[str, str] = {}

        self.solar_contracted_capacity: dict[str, float] = {}
        self.solar_capacity: pd.DataFrame = pd.DataFrame()
        self.solar_max_capacity: dict[str, float] = {}
        self.solar_unit_node: dict[str, str] = {}

        self.wind_contracted_capacity: dict[str, float] = {}
        self.wind_capacity: pd.DataFrame = pd.DataFrame()
        self.wind_max_capacity: dict[str, float] = {}
        self.wind_unit_node: dict[str, str] = {}

        self.import_contracted_capacity: dict[str, float] = {}
        self.import_capacity: pd.DataFrame = pd.DataFrame()
        self.import_max_capacity: dict[str, float] = {}
        self.import_unit_node: dict[str, str] = {}

        self.edges: gp.tuplelist = gp.tuplelist()
        self.line_capacity: pd.DataFrame = pd.DataFrame()
        self.rated_line_capacities: dict[tuple[str, str], int] = {}
        self.line_locations: pd.DataFrame = pd.DataFrame()
        self.susceptance: pd.DataFrame = pd.DataFrame()
        self.cycle_map: dict = {}

        self.max_line_capacity: int = 0
        self.spin_requirement: pd.Series = pd.Series()

        self.fuelmap: dict[str, str] = {}  # Maps each unit to its fuel type

        # Maps a unit to its contracted price
        self.fuel_contracts: dict[str, str] = {}
        self.nondispatch_contracts: dict[str, str] = {}
        self.ess_contracts: dict[str, str] = {}
        # Contract costs are dicts of (contract, timestep) -> cost_per_mw
        self.contract_costs: dict[tuple[str, int], float] = {}

        # List of units
        self.thermal_units: list[str] = []
        self.thermal_must_take_units: list[str] = []

        self.hydro_units: list[str] = []
        self.solar_units: list[str] = []
        self.wind_units: list[str] = []
        self.import_units: list[str] = []
        self.all_generators: set[str] = []

        self.storage_units: list = []

        self.hydro_must_take_units: list[str] = []
        self.daily_hydro_must_take_units: list[str] = []
        self.weekly_hydro_must_take_units: list[str] = []
        self.solar_must_take_units: list[str] = []
        self.wind_must_take_units: list[str] = []
        self.import_must_take_units: list[str] = []

        # Generators by node
        self.node_generator: dict[str, list[str]] = {}

        # Edges by node
        self.nodes: set[str] = set(["b1"])  # Will get overwritten by the actual nodes
        self.node_edge: dict[str, list[str]] = {}

    def _load_timeseries_from_csv(
        self, filename: str, header_levels: int
    ) -> pd.DataFrame:
        """Helper function to load CSV with default options.
        - Date columns are dropped from the DataFrame
        - PowNet indexing starts at 1
        """
        date_cols = ["year", "month", "day", "hour", "date", "datetime"]
        # If there are header levels, we drop the date columns at the lowest level
        col_level = None
        if header_levels > 0:
            col_level = 0
        timeseries = pd.read_csv(
            os.path.join(self.model_dir, filename),
            header=list(range(header_levels + 1)),
        ).drop(date_cols, level=col_level, axis=1, errors="ignore")
        timeseries.index += 1
        return timeseries

    def _check_and_load_timeseries(
        self, filename: str, header_levels: int
    ) -> pd.DataFrame:
        """Check if the timeseries file exists and load it.
        Timeseries of unit capacities are column indexed with unit name and the connected node.
        """
        if os.path.exists(os.path.join(self.model_dir, filename)):
            return self._load_timeseries_from_csv(filename, header_levels=header_levels)
        return pd.DataFrame()

    def _check_and_load_csv(self, filename: str) -> pd.DataFrame:
        """Check if the CSV file exists and load it."""
        if os.path.exists(os.path.join(self.model_dir, filename)):
            return pd.read_csv(os.path.join(self.model_dir, filename), header=0)
        return pd.DataFrame()

    def _get_column_pairs_as_dict(self, df: pd.DataFrame) -> list:
        """
        Extracts dictionary pairs from the DataFrame's multi-index columns.

        Args:
            df: The DataFrame with multi-index columns.

        Returns:
            A dictionary where (1) Keys The first-level column index values and (2) Values are the second-level column index values.
        """
        column_pairs = df.columns.to_flat_index().tolist()
        return dict(column_pairs)

    def load_thermal_unit_params(self):
        """Load the techno-economic parameters of thermal units from thermal_unit.csv."""
        thermal_unit_df = self._check_and_load_csv("thermal_unit.csv")

        if thermal_unit_df.empty:
            return

        thermal_unit_df = thermal_unit_df.set_index("name")

        self.thermal_unit_node = thermal_unit_df["node"].to_dict()
        self.thermal_fixed_cost = thermal_unit_df["fixed_cost"].to_dict()
        self.thermal_opex = thermal_unit_df["operation_cost"].to_dict()
        self.thermal_startup_cost = thermal_unit_df["startup_cost"].to_dict()
        self.thermal_heat_rate = thermal_unit_df["heat_rate"].to_dict()

        # The minimum downtime and uptime are in hours
        self.TD = thermal_unit_df["min_downtime"].to_dict()
        self.TU = thermal_unit_df["min_uptime"].to_dict()

        # The startup and shutdown ramp rates are in MW/h
        # IMPORTANT: Currently we do not model these values in PowNet
        # Therefore, we assume the shutdown and startup ramp rates are equal
        # and they are equal to the minimum capacity of the unit.
        self.SD = thermal_unit_df["min_capacity"].to_dict()
        self.SU = self.SD.copy()

        # The ramp rates are in MW/h.
        # IMPORTANT: We assume the ramp rates are equal for both directions.
        self.RD = thermal_unit_df["ramp_rate"].to_dict()
        self.RU = self.RD.copy()

        # Maximum/Minimum capacity of the thermal units
        self.thermal_rated_capacity = thermal_unit_df["max_capacity"].to_dict()
        self.thermal_min_capacity = thermal_unit_df["min_capacity"].to_dict()

        # The maximum capacity is reduced by the derating factor (timeseries)
        self.thermal_derated_capacity = self._load_timeseries_from_csv(
            "pownet_thermal_derated_capacity.csv", header_levels=0
        )

        # The fuel type of each thermal unit
        self.fuelmap.update(thermal_unit_df["fuel_type"].to_dict())

        # Must take thermal units (units that have dispatch priority)
        self.thermal_must_take_units = (
            thermal_unit_df.loc[thermal_unit_df["must_take"] == 1]
        ).index.tolist()

    def load_ess_params(self):
        """Load the techno-economic parameters of energy storage systems from energy_storage.csv."""
        ess_df = self._check_and_load_csv("energy_storage.csv")

        if ess_df.empty:
            return

        # Ensure values are between zero and one
        for col in ["charge_efficiency", "discharge_efficiency", "self_discharge_rate"]:
            if not 0 <= ess_df[col].min() <= ess_df[col].max() <= 1:
                raise ValueError(f"PowNet: {col} must be between 0 and 1.")

        # Min capacity must be less than max capacity
        if not (ess_df["min_capacity"] <= ess_df["max_capacity"]).all():
            raise ValueError(
                "PowNet: Min capacity must be less than or equal to max capacity."
            )

        ess_df = ess_df.set_index("name")

        self.ess_max_charge = ess_df["max_charge"].to_dict()
        self.ess_max_discharge = ess_df["max_discharge"].to_dict()
        self.ess_max_capacity = ess_df["max_capacity"].to_dict()
        self.ess_min_capacity = ess_df["min_capacity"].to_dict()
        self.ess_charge_efficiency = ess_df["charge_efficiency"].to_dict()
        self.ess_discharge_efficiency = ess_df["discharge_efficiency"].to_dict()
        self.ess_self_discharge_rate = ess_df["self_discharge_rate"].to_dict()

        # ESS -> unit/node attached
        self.ess_unit_attach = ess_df["attach_to"].to_dict()
        # unit/node -> list of ESS attached
        for unit, attached in self.ess_unit_attach.items():
            if attached not in self.ess_attach_unit.keys():
                self.ess_attach_unit[attached] = [unit]
            else:
                self.ess_attach_unit[attached].append(unit)

            # Separate ESS by unit type
            if attached in self.hydro_unit_node.keys():
                self.ess_hydro_units[attached] = self.ess_attach_unit[attached]

            elif attached in self.daily_hydro_unit_node.keys():
                self.ess_daily_hydro_units[attached] = self.ess_attach_unit[attached]

            elif attached in self.weekly_hydro_unit_node.keys():
                self.ess_weekly_hydro_units[attached] = self.ess_attach_unit[attached]

            elif attached in self.solar_unit_node.keys():
                self.ess_solar_units[attached] = self.ess_attach_unit[attached]

            elif attached in self.wind_unit_node.keys():
                self.ess_wind_units[attached] = self.ess_attach_unit[attached]

            elif attached in self.thermal_unit_node.keys():
                self.ess_thermal_units[attached] = self.ess_attach_unit[attached]

            # Lowest priority so a storage unit is chosen as attached to a generator first
            elif attached in self.nodes:
                self.ess_substation_units[attached] = self.ess_attach_unit[attached]

        self.storage_units = list(self.ess_unit_attach.keys())

        # The maximum capacity is reduced by the derating factor (timeseries)
        self.ess_derated_capacity = self._load_timeseries_from_csv(
            "pownet_ess_derated_capacity.csv", header_levels=0
        )

    def _add_units_to_node(self, node, unit_node_dict):
        """
        Helper method to add units to the node_generator dictionary.
        """
        for unit, unit_node in unit_node_dict.items():
            if unit_node == node:
                self.node_generator[node].append(unit)

    def _store_generators_by_node(self):
        """
        Store the generators by node in a dictionary : {
        node1:['generator1', 'gen2'],
        node2:['gen3', 'gen4']
        }
        Generators include thermal, hydro, solar, wind, and import units.
        """
        self.node_generator = {}
        for node in self.nodes:
            self.node_generator[node] = []
            self._add_units_to_node(node, self.thermal_unit_node)
            self._add_units_to_node(node, self.hydro_unit_node)
            self._add_units_to_node(node, self.daily_hydro_unit_node)
            self._add_units_to_node(node, self.weekly_hydro_unit_node)
            self._add_units_to_node(node, self.solar_unit_node)
            self._add_units_to_node(node, self.wind_unit_node)
            self._add_units_to_node(node, self.import_unit_node)

    def _store_edges_by_node(self):
        """
        Store the edges by node in a dictionary : {
        node1:['edge1', 'edge2'],
        node2:['edge3', 'edge4']
        }
        """
        self.node_edge = {}
        for node in self.nodes:
            self.node_edge[node] = []
            for edge in self.edges:
                if node in edge:
                    self.node_edge[node].append(edge)

    def _load_capacity_and_update_fuelmap_and_get_unit_node(
        self, csv_filename: str, fuel_type: str
    ) -> tuple[pd.DataFrame, dict[str, str]]:
        """
        Loads capacity data from a CSV file, extracts unit-node mapping, and updates the fuelmap.

        Args:
            csv_filename: The name of the CSV file to load.
            fuel_type: The fuel type to associate with the loaded units.

        Returns:
            The loaded capacity DataFrame with a single-level column index.
        """
        capacity_data = self._check_and_load_timeseries(csv_filename, header_levels=1)
        unit_node_map = self._get_column_pairs_as_dict(capacity_data)
        capacity_data.columns = (
            capacity_data.columns.droplevel(1)
            if len(capacity_data.columns) >= 1
            else capacity_data.columns
        )
        self.fuelmap.update({k: fuel_type for k in unit_node_map.keys()})
        return capacity_data, unit_node_map

    def _load_contract_costs(self):
        self.fuel_contracts = self._check_and_load_csv("thermal_unit.csv")
        if not self.fuel_contracts.empty:
            self.fuel_contracts = self.fuel_contracts.set_index("name")[
                "fuel_contract"
            ].to_dict()

        self.nondispatch_contracts = self._check_and_load_csv("nondispatch_unit.csv")
        if not self.nondispatch_contracts.empty:
            self.nondispatch_contracts = self.nondispatch_contracts.set_index("name")[
                "contract"
            ].to_dict()

        # Add ESS contracts to nondispatch_contracts
        self.ess_contracts = self._check_and_load_csv("energy_storage.csv")
        if not self.ess_contracts.empty:
            self.ess_contracts = self.ess_contracts.set_index("name")[
                "cost_contract"
            ].to_dict()

        # Load contract costs as a dictionary containing (contract, timestep) -> cost_per_mw
        contract_costs_df = self._check_and_load_timeseries(
            "contract_cost.csv", header_levels=0
        )

        # Check that the contract costs timeseries is of length num_sim_hours
        if len(contract_costs_df) not in [0, self.num_sim_hours]:
            raise ValueError(
                f"PowNet: Marginal cost timeseries must be of length {self.num_sim_hours}."
            )

        self.contract_costs = {
            (col, idx): value
            for col in contract_costs_df.columns
            for idx, value in contract_costs_df[col].items()
        }

    def _load_hydropower(self) -> None:

        # Units with hourly timeseries
        if os.path.exists(os.path.join(self.model_dir, "hydropower.csv")):
            self.hydro_capacity, self.hydro_unit_node = (
                self._load_capacity_and_update_fuelmap_and_get_unit_node(
                    "hydropower.csv", fuel_type="hydropower"
                )
            )
            self.hydro_max_capacity = self.hydro_capacity.max().to_dict()

        # Units with daily timeseries
        if os.path.exists(os.path.join(self.model_dir, "hydropower_daily.csv")):
            self.daily_hydro_capacity, self.daily_hydro_unit_node = (
                self._load_capacity_and_update_fuelmap_and_get_unit_node(
                    "hydropower_daily.csv", fuel_type="hydropower"
                )
            )
            daily_hydro_max_capacity = self.daily_hydro_capacity.max().to_dict()
            self.hydro_max_capacity.update(daily_hydro_max_capacity)

        # Units with weekly timeseries
        if os.path.exists(os.path.join(self.model_dir, "hydropower_weekly.csv")):
            self.weekly_hydro_capacity, self.weekly_hydro_unit_node = (
                self._load_capacity_and_update_fuelmap_and_get_unit_node(
                    "hydropower_weekly.csv", fuel_type="hydropower"
                )
            )

        if os.path.exists(os.path.join(self.model_dir, "hydro_min_capacity.csv")):
            self.hydro_min_capacity = pd.read_csv(
                os.path.join(self.model_dir, "hydro_min_capacity.csv")
            )

        # Check that the names do not repeat across different types
        repeated_units = set(self.hydro_unit_node.keys()).intersection(
            self.daily_hydro_unit_node.keys()
        )
        if repeated_units:
            raise ValueError(
                f"PowNet: Found hydropower units to formulate with both hourly and daily formulations: {repeated_units}"
            )

        # Check that the names do not repeat across different types
        repeated_units_weekly = set(self.hydro_unit_node.keys()).intersection(
            self.weekly_hydro_unit_node.keys()
        )
        if repeated_units_weekly:
            raise ValueError(
                f"PowNet: Found hydropower units to formulate with both hourly and weekly formulations: {repeated_units_weekly}"
            )

        # Check that the names do not repeat across different types
        repeated_units_daily_weekly = set(
            self.daily_hydro_unit_node.keys()
        ).intersection(self.weekly_hydro_unit_node.keys())
        if repeated_units_daily_weekly:
            raise ValueError(
                f"PowNet: Found hydropower units to formulate with both daily and weekly formulations: {repeated_units_daily_weekly}"
            )

    def _load_nondispatchable_must_take_units(self):
        # A system can comprise only thermal units
        if not os.path.exists(os.path.join(self.model_dir, "nondispatch_unit.csv")):
            return

        must_take_info = pd.read_csv(
            os.path.join(self.model_dir, "nondispatch_unit.csv"), header=0
        ).set_index("name")["must_take"]

        unit_types = {
            "hydro": self.hydro_unit_node,
            "daily_hydro": self.daily_hydro_unit_node,
            "weekly_hydro": self.weekly_hydro_unit_node,
            "solar": self.solar_unit_node,
            "wind": self.wind_unit_node,
            "import": self.import_unit_node,
        }

        must_take_units = {
            unit_type: [unit for unit in units if must_take_info.get(unit) == 1]
            for unit_type, units in unit_types.items()
        }
        for unit_type in unit_types:
            setattr(
                self,
                f"{unit_type}_must_take_units",
                must_take_units.get(
                    unit_type, []
                ),  # Return an empty list if the unit type is not present
            )

    def _create_timeseries_of_edges(self, data: list, column_name: str) -> pd.DataFrame:
        """
        Creates a time series DataFrame from given data.

        Args:
            data: The data to be used for the time series.
            column_name: Name of the data or what it represents

        Returns:
            A DataFrame with the time series data.
        """
        df = pd.DataFrame(
            data,
            index=pd.MultiIndex.from_tuples(self.edges, names=["source", "sink"]),
            columns=[column_name],
        ).T
        # Repeat values for every hour of the year
        df = df.loc[df.index.repeat(self.num_sim_hours)].reset_index(drop=True)
        df.index += 1
        return df

    def _load_contracted_capacity(self) -> None:
        nondispatch_df = self._check_and_load_csv("nondispatch_unit.csv")
        if nondispatch_df.empty:
            return
        # Replace -1 in the contracted_capacity column to GRB.INFINITY
        nondispatch_df["contracted_capacity"] = (
            nondispatch_df["contracted_capacity"]
            .astype(float)
            .replace(-1, GRB.INFINITY)
        )

        unit_types = {
            "hydro": self.hydro_unit_node,
            "solar": self.solar_unit_node,
            "wind": self.wind_unit_node,
            "import": self.import_unit_node,
        }
        for unit_type, units in unit_types.items():
            setattr(
                self,
                f"{unit_type}_contracted_capacity",
                nondispatch_df.loc[nondispatch_df["name"].isin(units.keys())]
                .set_index("name")["contracted_capacity"]
                .to_dict(),
            )

        # Add daily hydro units to the contracted capacity under "hydro"
        self.hydro_contracted_capacity.update(
            nondispatch_df.loc[nondispatch_df["name"].isin(self.daily_hydro_unit_node)]
            .set_index("name")["contracted_capacity"]
            .to_dict()
        )

        # Add daily hydro units to the contracted capacity under "hydro"
        self.hydro_contracted_capacity.update(
            nondispatch_df.loc[nondispatch_df["name"].isin(self.weekly_hydro_unit_node)]
            .set_index("name")["contracted_capacity"]
            .to_dict()
        )

    def load_data(self):
        """Load the input data for the power system model.
        Timeseries are loaded as dataframes with the index starting at 1.
        """

        #################
        # Thermal units
        #################
        self.load_thermal_unit_params()

        #################
        # Demand (timeseries)
        #################

        self.demand = self._load_timeseries_from_csv(
            "demand_export.csv", header_levels=0
        )

        self.total_demand = self.demand.sum(axis=1)

        # Demand nodes
        self.demand_nodes = self.demand.columns.tolist()
        # Identify the node with the maximum demand
        self.max_demand_node = self.demand.idxmax().idxmax()

        #################
        # Hydropower
        #################

        self._load_hydropower()

        #################
        # Renewables (timeseries)
        #################

        self.solar_capacity, self.solar_unit_node = (
            self._load_capacity_and_update_fuelmap_and_get_unit_node(
                "solar.csv", "solar"
            )
        )
        self.solar_max_capacity = self.solar_capacity.max().to_dict()

        self.wind_capacity, self.wind_unit_node = (
            self._load_capacity_and_update_fuelmap_and_get_unit_node("wind.csv", "wind")
        )
        self.wind_max_capacity = self.wind_capacity.max().to_dict()

        self.import_capacity, self.import_unit_node = (
            self._load_capacity_and_update_fuelmap_and_get_unit_node(
                "import.csv", "import"
            )
        )
        self.import_max_capacity = self.import_capacity.max().to_dict()

        self._load_contracted_capacity()

        #################
        # All generators
        #################
        generators = (
            list(self.thermal_unit_node.keys())
            + list(self.hydro_unit_node.keys())
            + list(self.daily_hydro_unit_node.keys())
            + list(self.weekly_hydro_unit_node.keys())
            + list(self.solar_unit_node.keys())
            + list(self.wind_unit_node.keys())
            + list(self.import_unit_node.keys())
        )
        set_generators = set(generators)
        if len(generators) != len(set_generators):
            raise ValueError(
                "PowNet: Generator names cannot repeat across different types."
            )
        self.all_generators = set_generators

        #################
        # Must-take non-dispatchable units
        # hydro, solar, wind, import
        #################
        self._load_nondispatchable_must_take_units()

        #################
        # Transmission
        #################

        transmission: pd.DataFrame = self._check_and_load_csv("pownet_transmission.csv")

        # Nodes are connected by transmission lines
        if not transmission.empty:
            self.nodes = set(transmission.source).union(set(transmission.sink))

            # Edges are the transmission lines
            self.edges = gp.tuplelist(
                transmission.set_index(["source", "sink"]).index.tolist()
            )

            # The line susceptance is a function of hydroclimatic conditions (temperature),
            # so it is best being a timeseries. Line susceptance is used when the line flow
            # is modeled with voltage angle.
            self.susceptance = self._create_timeseries_of_edges(
                data=transmission.susceptance.values, column_name="susceptance"
            )

            # Similar to susceptance, the line capacity is also a timeseries. We use line capacity when
            # the line flow is modeled with Kirchhoff's laws.
            self.line_capacity = self._create_timeseries_of_edges(
                data=transmission.line_capacity.values, column_name="line_capacity"
            )

            self.max_line_capacity = self.line_capacity.max().max()

            # Capacity of each line segment
            self.rated_line_capacities = (
                transmission[["source", "sink", "line_capacity"]]
                .set_index(["source", "sink"])
                .to_dict()["line_capacity"]
            )

            # Source sink locations of the line segments
            try:
                self.line_locations = pd.read_csv(
                    os.path.join(self.model_dir, "transmission.csv"),
                    header=0,
                    usecols=[
                        "source",
                        "sink",
                        "source_lon",
                        "source_lat",
                        "sink_lon",
                        "sink_lat",
                    ],
                ).set_index(["source", "sink"])

            except ValueError as e:
                error_msg = e.args[0]
                if not ("columns expected but not found" in error_msg):
                    raise ValueError(f"Unexpected error: {error_msg}")

            # A user can use DataProcessor to generate pownet_cycle_map.json
            if self.dc_opf == "kirchhoff":
                if os.path.exists(
                    os.path.join(self.model_dir, "pownet_cycle_map.json")
                ):
                    with open(
                        os.path.join(self.model_dir, "pownet_cycle_map.json")
                    ) as f:
                        self.cycle_map = json.load(f)

        # When there is no transmission.csv, we expect only one demand node
        else:
            if len(self.demand_nodes) != 1:
                raise ValueError(
                    "PowNet: When there is no transmission.csv, there must be only one demand node."
                )
            self.nodes = set(self.demand.columns)


        #################
        # System requirements
        #################
        if self.spin_reserve_mw is not None:
            self.spin_requirement = pd.Series(
                self.spin_reserve_mw, index=range(1, self.num_sim_hours + 1)
            )
        else:
            self.spin_requirement = self.demand.sum(axis=1) * self.spin_reserve_factor

        #################
        # List of units
        #################
        self.thermal_units = list(self.thermal_unit_node.keys())
        self.hydro_units = (
            list(self.hydro_unit_node.keys())
            + list(self.daily_hydro_unit_node.keys())
            + list(self.weekly_hydro_unit_node.keys())
        )
        self.solar_units = list(self.solar_unit_node.keys())
        self.wind_units = list(self.wind_unit_node.keys())
        self.import_units = list(self.import_unit_node.keys())

        #################
        # Node information
        #################
        self._store_generators_by_node()
        self._store_edges_by_node()

        #################
        # Energy storage is loaded last because
        # it is linked to generators and nodes
        #################
        self.load_ess_params()

        #################
        # Contract costs
        #################
        self._load_contract_costs()

    def check_data(self):
        """
        Perform checks on the input data to ensure consistency and correctness.
        """
        ##################################
        # Simulation horizon is a multiple of 24 and greater than 24
        ##################################

        if self.sim_horizon < 24 or self.sim_horizon % 24 != 0:
            raise ValueError(
                "PowNet: Simulation horizon must be a multiple of 24 and greater than 24."
            )

        ##################################
        # Nodes are connected to the grid
        ##################################
        if not set(self.demand_nodes).issubset(self.nodes):
            raise ValueError(
                f"PowNet: Demand nodes must be connected to the grid: {set(self.demand_nodes) - self.nodes}"
            )

        nodes_to_check = [
            ("hydro_unit_node", "Hydropower units"),
            ("daily_hydro_unit_node", "Daily hydropower units"),
            ("weekly_hydro_unit_node", "Weekly hydropower units"),
            ("solar_unit_node", "Solar units"),
            ("wind_unit_node", "Wind units"),
            ("import_unit_node", "Import units"),
        ]

        for nodes, node_type in nodes_to_check:
            if not set(getattr(self, nodes).values()).issubset(self.nodes):
                raise ValueError(
                    f"PowNet: {node_type} must be connected to the grid: {set(getattr(self, nodes).values()) - self.nodes}"
                )

        ##################################
        # Factors are between 0 and 1
        ##################################

        if not 0 <= self.spin_reserve_factor <= 1:
            raise ValueError("PowNet: Spin reserve factor must be between 0 and 1.")
        if not 0 <= self.gen_loss_factor <= 1:
            raise ValueError("PowNet: Generation loss factor must be between 0 and 1.")
        if not 0 <= self.line_loss_factor <= 1:
            raise ValueError("PowNet: Line loss factor must be between 0 and 1.")
        if not 0 <= self.line_capacity_factor <= 1:
            raise ValueError("PowNet: Line capacity factor must be between 0 and 1.")

        ##################################
        # Timeseries have the correct length
        ##################################

        if len(self.demand) != self.num_sim_hours:
            raise ValueError(
                f"PowNet: Demand timeseries must be of length {self.num_sim_hours} but got {len(self.demand)}."
            )

        attrs_to_check = [
            "solar_capacity",
            "wind_capacity",
            "import_capacity",
            "hydro_capacity",
            "susceptance",
            "line_capacity",
        ]
        for attr in attrs_to_check:
            temp_df = getattr(self, attr)
            if (not temp_df.empty) and (len(temp_df) != self.num_sim_hours):
                raise ValueError(
                    f"PowNet: {attr} must be of length {self.num_sim_hours} but got {len(temp_df)}."
                )

        if len(self.daily_hydro_capacity) not in [0, self.num_sim_days]:
            raise ValueError(
                f"PowNet: Daily hydropower timeseries must be of length {self.num_sim_days}."
            )

        if len(self.weekly_hydro_capacity) not in [0, self.num_sim_days]:
            raise ValueError(
                f"PowNet: Weekly hydropower timeseries must be of length {self.num_sim_days}."
            )
        
        ##################################
        # Capacities are non-negative
        ##################################

        attrs_to_check = [
            "solar_capacity",
            "wind_capacity",
            "import_capacity",
            "hydro_capacity",
            "susceptance",
            "line_capacity",
        ]
        for attr in attrs_to_check:
            temp_df = getattr(self, attr)
            if (not temp_df.empty) and (temp_df < 0).any().any():
                raise ValueError(f"PowNet: {attr} must be non-negative.")

        ##################################
        # The derated capacities of thermal units must be above its minimum capacity
        ##################################

        if not (self.thermal_derated_capacity >= self.thermal_min_capacity).all().all():
            # Identify units with derated capacity below the minimum capacity
            units_below_min_capacity = (
                self.thermal_derated_capacity[
                    self.thermal_derated_capacity < self.thermal_min_capacity
                ]
                .stack()
                .index.tolist()
            )
            raise ValueError(
                f"PowNet: The derated capacity of thermal units must be above the minimum capacity:\n{units_below_min_capacity}"
            )

        ##################################
        # Spinning reserve cannot be larger than the whole system's demand
        ##################################

        if self.spin_reserve_mw is not None:
            if (self.spin_reserve_mw > self.demand.sum(axis=1)).any():
                raise ValueError(
                    "PowNet: Spin reserve cannot be larger than demand at any time."
                )

        ##################################
        # Consistency in the number of units
        ##################################

        # The number of columns contracts must equal the number of generators
        number_of_non_fossil_generators = len(
            self.hydro_unit_node
            | self.daily_hydro_unit_node
            | self.weekly_hydro_unit_node
            | self.solar_unit_node
            | self.wind_unit_node
            | self.import_unit_node
        )

        # Number of nondispatch contracts
        if len(self.nondispatch_contracts) != number_of_non_fossil_generators:
            raise ValueError(
                f"PowNet: The number of non-dispatchable contracts must equal the number of non-fossil generators. {len(self.nondispatch_contracts)} != {number_of_non_fossil_generators}"
            )

        number_of_generators = (
            len(self.thermal_unit_node) + number_of_non_fossil_generators
        )
        if len(self.fuelmap) != number_of_generators:
            raise ValueError(
                f"PowNet: The number of units in the fuelmap must be equal to the number of generators. {len(self.fuelmap)} != {number_of_generators}"
            )

        # Number of nodes in the node_generator dictionary must be equal to the number of nodes
        if len(self.node_generator) != len(self.nodes):
            raise ValueError(
                f"PowNet: The number of nodes in the node_generator dictionary must be equal to the number of nodes. {len(self.node_generator)} != {len(self.nodes)}"
            )

        # Number of generators in the node_generator dictionary must be equal to the number of generators
        if sum(len(v) for v in self.node_generator.values()) != number_of_generators:
            raise ValueError(
                f"PowNet: The number of generators in the node_generator dictionary must be equal to the number of generators. {sum(len(v) for v in self.node_generator.values())} != {number_of_generators}"
            )

        # Number of nodes in the node_edge dictionary must be equal to the number of nodes
        if len(self.node_edge) != len(self.nodes):
            raise ValueError(
                f"PowNet: The number of nodes in the node_edge dictionary must be equal to the number of nodes. {len(self.node_edge)} != {len(self.nodes)}"
            )

        # Number of edges in the node_edge dictionary must be equal to TWICE the number of edges
        if sum(len(v) for v in self.node_edge.values()) != 2 * len(self.edges):
            raise ValueError(
                f"PowNet: The number of edges in the node_edge dictionary must be equal to the number of edges. {sum(len(v) for v in self.node_edge.values())} != {2 * len(self.edges)}"
            )

        ##################################
        # Names cannot repeat across different types
        ##################################
        if self.all_generators.intersection(self.demand_nodes):
            raise ValueError(
                "PowNet: Generator names cannot be the same as the name of demand nodes."
            )
        if set(self.ess_unit_attach.keys()).intersection(self.all_generators):
            raise ValueError(
                "PowNet: Energy storage names cannot be the same as the name of generators."
            )

        ##################################
        # ESS must be connected to either a node or a generator
        ##################################

        assigned_ess = (
            list(self.ess_hydro_units.keys())
            + list(self.ess_daily_hydro_units.keys())
            + list(self.ess_weekly_hydro_units.keys())
            + list(self.ess_solar_units.keys())
            + list(self.ess_wind_units.keys())
            + list(self.ess_thermal_units.keys())
            + list(self.ess_substation_units.keys())
        )
        if len(assigned_ess) != len(self.ess_unit_attach):
            raise ValueError(
                "PowNet: Energy storage systems must be connected to either a node or a generator."
            )

    def print_summary(self):
        input_summary = textwrap.dedent(
            f"""
        \n\nPowNet Input Data Summary:
        {'Timestamp':<25} = {self.timestamp}
        {'Model name':<25} = {self.model_name}
        {'Year':<25} = {self.year}
        ---- System characteristics ----
        {'No. of nodes':<25} = {len(self.nodes)}
        {'No. of edges':<25} = {len(self.edges)}
        {'No. of thermal units':<25} = {len(self.thermal_unit_node)}
        {'No. of demand nodes':<25} = {len(self.demand_nodes)}
        {'Peak demand':<25} = {round(self.demand.sum(axis=1).max())} MW

        ---- Renewable capacities ----
        {'Hydropower units':<25} = {len(self.hydro_unit_node)}
        {'Daily hydropower units':<25} = {len(self.daily_hydro_unit_node)}
        {'Weekly hydropower units':<25} = {len(self.weekly_hydro_unit_node)}
        {'Solar units':<25} = {len(self.solar_unit_node)}
        {'Wind units':<25} = {len(self.wind_unit_node)}
        {'Import units':<25} = {len(self.import_unit_node)}

        ---- Energy storage ----
        {'No. of hydropower with ESS':<25} = {len(self.ess_hydro_units)}
        {'No. of daily hydropower with ESS':<25} = {len(self.ess_daily_hydro_units)}
        {'No. of weekly hydropower with ESS':<25} = {len(self.ess_weekly_hydro_units)}
        {'No. of Solar with ESS':<25} = {len(self.ess_solar_units)}
        {'No. of Wind with ESS':<25} = {len(self.ess_wind_units)}
        {'No. of Thermal units with ESS':<25} = {len(self.ess_thermal_units)}
        {'No. of Grid ESS':<25} = {len(self.ess_substation_units)}

        ---- Modeling parameters ----
        {'Simulation horizon':<25} = {self.sim_horizon} hours
        {'Number of simulation days':<25} = {self.num_sim_days}
        {'Use spin variable':<25} = {self.use_spin_var}
        {'Power flow':<25} = {self.dc_opf}
        {'Spin reserve factor:':<25} = {self.spin_reserve_factor if self.spin_reserve_mw is None else 'Use an absolute value in MW.'}
        {'Spin reserve amount (MW):':<25} = {self.spin_reserve_mw if self.spin_reserve_mw is not None else 'Using a factor.'}
        {'Generation loss factor':<25} = {self.gen_loss_factor}
        {'Line loss factor':<25} = {self.line_loss_factor}
        {'Line capacity factor':<25} = {self.line_capacity_factor}
        {'Load shortfall penalty':<25} = {self.load_shortfall_penalty_factor}
        {'Reserve shortfall penalty':<25} = {self.spin_shortfall_penalty_factor}\n

        """
        )
        logger.warning(input_summary)

    def load_and_check_data(self):
        """Load and check the input data."""
        self.load_data()
        self.check_data()
        self.print_summary()

    def update_capacity(self, capacity_df: pd.DataFrame, unit_type: str) -> None:
        """Update a capacity timeseries of a given unit type (hydro, solar, wind, and import).

        Args:
            capacity_df: The new capacity timeseries.
            unit_type: The type of the unit (hydro, solar, wind, import).

        Raises:
            ValueError: If the given unit type is not supported.
            ValueError: If the length of the timeseries does not match the existing capacity timeseries.
            ValueError: If the timeseries does not contain all units of the given type.
        """

        allowed_unit_types = ["hydro", "daily_hydro","solar", "wind", "import"]
        if unit_type not in allowed_unit_types:
            raise ValueError(f"Given unit type: {unit_type} not supported.")

        current_capacity = getattr(self, f"{unit_type}_capacity")

        if len(capacity_df) != len(current_capacity):
            raise ValueError(
                "PowNet: The length of the hydropower timeseries must remain the same."
            )
        
        # Check that index matches
        if not capacity_df.index.equals(current_capacity.index):
            raise ValueError(
                "PowNet: The index of the hydropower timeseries must remain the same."
            )
        
        # Check that all hydropower units are present
        if set(capacity_df.columns) != set(current_capacity.columns):
            raise ValueError(
                "PowNet: Unit names in the capacity timeseries must remain the same."
            )
        # Save a copy to prevent unintended changes
        setattr(self, f"{unit_type}_capacity", capacity_df.copy())

    def get_unit_contracts(self) -> dict[str, str]:
        all_contracts = self.fuel_contracts.copy()
        all_contracts.update(self.nondispatch_contracts)
        all_contracts.update(self.ess_contracts)
        return all_contracts
