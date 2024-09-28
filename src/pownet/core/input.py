""" input.py: SystemInput class loads and checks the input data. It is used by other PowNet objects to access the input data. """

from datetime import datetime
import logging
import json
import os
import textwrap

import gurobipy as gp
import pandas as pd

from pownet.folder_utils import get_model_dir

logger = logging.getLogger(__name__)


class SystemInput:
    def __init__(
        self,
        model_name: str,
        year: int,
        sim_horizon: int,
        use_spin_var: bool = True,
        dc_opf: str = "kirchhoff",
        spin_reserve_factor: float = 0.15,
        line_loss_factor: float = 0.075,
        line_capacity_factor: float = 0.9,
        load_shortfall_penalty_factor: float = 1000,
        load_curtail_penalty_factor: float = 10,
        spin_shortfall_penalty_factor: float = 1000,
    ) -> None:
        """This class reads the input data for the power system model."""

        self.model_name = model_name
        self.year = year
        self.sim_horizon = sim_horizon
        self.use_spin_var = use_spin_var

        # The timestamp is used to create a unique folder for the model
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M")

        self.model_id: str = f"{self.timestamp}_{self.model_name}_{self.sim_horizon}"

        # DC representation of the power flow model
        if dc_opf not in ["kirchhoff", "voltage_angle"]:
            raise ValueError(
                "PowNet: Line flow must be either 'kirchhoff' or 'voltage_angle'."
            )
        self.dc_opf = dc_opf

        # The spin reserve factor is a fraction of total demand
        self.spin_reserve_factor = spin_reserve_factor

        # The line loss factor is also called the inefficiency factor.
        # It is the fraction of power lost in the transmission line.
        self.line_loss_factor = line_loss_factor

        # The line capacity factor is the fraction of the line capacity
        # that can be used. It is used to account for the uncertainty in
        # the line capacity.
        self.line_capacity_factor = line_capacity_factor

        # The shortfall penalty is the cost of not meeting the demand. (USD/MWh)
        self.load_shortfall_penalty_factor = load_shortfall_penalty_factor
        self.load_curtail_penalty_factor = load_curtail_penalty_factor

        # The reserve penalty is the cost of not meeting the reserve requirement. (USD/MWh)
        self.spin_shortfall_penalty_factor = spin_shortfall_penalty_factor

        # folder structure: pownet_root/model_library/
        self.model_dir = os.path.join(get_model_dir(), model_name)

        #################
        # Complex attributes that will be defined in load_data
        #################

        # Thermal units
        self.thermal_unit_node: dict[str, str] = {}
        self.thermal_fuel_cost: dict[str, str] = {}

        self.thermal_fixed_cost: dict[str, float] = {}
        self.thermal_opex: dict[str, float] = {}
        self.thermal_startup_cost: dict[str, float] = {}
        self.thermal_heat_rate: dict[str, float] = {}

        self.thermal_rated_capacity: dict[str, float] = {}
        self.thermal_derated_capacity: dict[str, float] = {}
        self.thermal_min_capacity: dict[str, float] = {}

        self.TD: dict[str, int] = {}
        self.TU: dict[str, int] = {}
        self.SD: dict[str, float] = {}
        self.SU: dict[str, float] = {}
        self.RD: dict[str, float] = {}
        self.RU: dict[str, float] = {}

        # Other data
        self.demand: pd.DataFrame = pd.DataFrame()

        self.unit_marginal_cost: pd.DataFrame = pd.DataFrame()

        self.hydro_capacity: pd.DataFrame = pd.DataFrame()
        self.hydro_timestep: str = ""
        self.hydro_unit_node: dict[str, str] = {}

        self.solar_capacity: pd.DataFrame = pd.DataFrame()
        self.solar_unit_node: dict[str, str] = {}

        self.wind_capacity: pd.DataFrame = pd.DataFrame()
        self.wind_unit_node: dict[str, str] = {}

        self.import_capacity: pd.DataFrame = pd.DataFrame()
        self.import_unit_node: dict[str, str] = {}

        self.demand_nodes: list[str] = []
        self.edges: gp.tuplelist = gp.tuplelist()
        self.line_capacity: pd.DataFrame = pd.DataFrame()
        self.susceptance: pd.DataFrame = pd.DataFrame()
        self.cycle_map: dict = {}

        self.max_demand_node: str = ""
        self.max_line_capacity: int = 0
        self.spin_requirement: pd.DataFrame = pd.DataFrame()

        self.fuelmap: dict[str, str] = {}  # Maps each unit to its fuel type

        # List of units
        self.thermal_units: list[str] = []
        self.hydro_units: list[str] = []
        self.solar_units: list[str] = []
        self.wind_units: list[str] = []
        self.import_units: list[str] = []

        # Generators by node
        self.node_generator: dict[str, list[str]] = {}

        # Edges by node
        self.node_edge: dict[str, list[str]] = {}

    def _load_csv(self, filename: str, header_levels: int) -> pd.DataFrame:
        """Helper function to load CSV with default options.
        Note:
        - Files are located in the model directory
        - Date columns are dropped from the DataFrame
        """
        date_cols = ["year", "month", "day", "hour", "date"]
        # If there are header levels, we drop the date columns at the lowest level
        col_level = None
        if header_levels > 0:
            col_level = 0
        return pd.read_csv(
            os.path.join(self.model_dir, filename),
            header=list(range(header_levels + 1)),
        ).drop(date_cols, level=col_level, axis=1, errors="ignore")

    def _check_and_load_timeseries(
        self, filename: str, header_levels: int
    ) -> pd.DataFrame:
        """Check if the timeseries file exists and load it.
        Timeseries of unit capacities are column indexed with unit name and the connected node.
        """
        if os.path.exists(os.path.join(self.model_dir, filename)):
            df = self._load_csv(filename, header_levels=header_levels)
            df.index += 1
            return df
        return pd.DataFrame()

    def _get_column_pairs_as_dict(self, df: pd.DataFrame) -> list:
        """
        Extracts dictionary pairs from the DataFrame's multi-index columns.

        Args:
            df: The DataFrame with multi-index columns.

        Returns:
            A dictionary where keys are the first-level column values and values are the second-level column values.
        """
        column_pairs = df.columns.to_flat_index().tolist()
        return dict(column_pairs)

    def load_thermal_unit_params(self):
        """Load the techno-economic parameters of thermal units from thermal_unit.csv"""
        thermal_unit_df = pd.read_csv(
            os.path.join(self.model_dir, "thermal_unit.csv"), header=0, index_col="name"
        )
        self.thermal_unit_node = thermal_unit_df["node"].to_dict()

        self.thermal_fuel_cost = thermal_unit_df["fuel_cost"].to_dict()

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
        self.thermal_derated_capacity = self._load_csv(
            "pownet_derated_capacity.csv", header_levels=0
        )
        self.thermal_derated_capacity.index += 1

        # The fuel type of each thermal unit
        self.fuelmap.update(thermal_unit_df["fuel_type"].to_dict())

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

    def _add_units_to_node(self, node, unit_node_dict):
        """
        Helper method to add units to the node_generator dictionary.
        """
        for unit, unit_node in unit_node_dict.items():
            if unit_node == node:
                self.node_generator[node].append(unit)

    def _load_capacity_and_update_fuelmap(
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

        self.demand = self._load_csv("demand_export.csv", header_levels=0)
        self.demand.index += 1

        # Demand nodes
        self.demand_nodes = self.demand.columns.tolist()
        # Identify the node with the maximum demand
        self.max_demand_node = self.demand.idxmax().idxmax()

        #################
        # Marginal costs of renewables and import (timeseries)
        #################

        self.unit_marginal_cost = self._load_csv(
            "pownet_marginal_cost.csv", header_levels=0
        )
        self.unit_marginal_cost.index += 1

        #################
        # Hydropower (timeseries)
        #################

        # CHOOSE pownet_hydropower.csv over hydropower.csv because
        # the former is created from the reservoir module in PowNet

        if os.path.exists(os.path.join(self.model_dir, "pownet_hydropower.csv")):
            self.hydro_capacity, self.hydro_unit_node = (
                self._load_capacity_and_update_fuelmap(
                    "pownet_hydropower.csv", fuel_type="hydropower"
                )
            )

        elif os.path.exists(os.path.join(self.model_dir, "hydropower.csv")):
            self.hydro_capacity, self.hydro_unit_node = (
                self._load_capacity_and_update_fuelmap(
                    "hydropower.csv", fuel_type="hydropower"
                )
            )

        else:
            self.hydro_capacity = pd.DataFrame()

        # Hydropower can be given at hourly or daily resolution,
        # which the optimization model must match.
        hours_in_year = 8760
        days_in_year = 365
        if len(self.hydro_capacity) == hours_in_year:
            self.hydro_timestep = "hourly"
        elif len(self.hydro_capacity) == days_in_year:
            self.hydro_timestep = "daily"
        elif len(self.hydro_capacity) == 0:
            self.hydro_timestep = "none"
        else:
            raise ValueError(
                "PowNet: Hydropower timeseries must be either of length 8760 or 365."
            )

        #################
        # Renewables (timeseries)
        #################

        self.solar_capacity, self.solar_unit_node = (
            self._load_capacity_and_update_fuelmap("solar.csv", "solar")
        )
        self.wind_capacity, self.wind_unit_node = (
            self._load_capacity_and_update_fuelmap("wind.csv", "wind")
        )
        self.import_capacity, self.import_unit_node = (
            self._load_capacity_and_update_fuelmap("import.csv", "import")
        )

        #################
        # Transmission
        #################

        transmission: pd.DataFrame = pd.read_csv(
            os.path.join(self.model_dir, "pownet_transmission.csv"), header=0
        )

        # Nodes are connected by transmission lines
        self.nodes: set = set(transmission.source).union(set(transmission.sink))

        # Edges are the transmission lines
        self.edges = gp.tuplelist(
            transmission.set_index(["source", "sink"]).index.tolist()
        )

        # The line susceptance is a function of hydroclimatic conditions (temperature),
        # so it is best being a timeseries. Line susceptance is used when the line flow
        # is modeled with voltage angle.
        self.susceptance = pd.DataFrame(
            transmission.susceptance.values,
            index=pd.MultiIndex.from_tuples(self.edges, name=["source", "sink"]),
            columns=["susceptance"],
        ).T
        self.susceptance = self.susceptance.loc[
            self.susceptance.index.repeat(365 * 24)
        ].reset_index(drop=True)
        self.susceptance.index += 1

        # Similar to susceptance, the line capacity is also a timeseries. We use line capacity when
        # the line flow is modeled with Kirchhoff's laws.
        self.line_capacity = pd.DataFrame(
            transmission.line_capacity.values,
            index=pd.MultiIndex.from_tuples(self.edges, name=["source", "sink"]),
            columns=["line_capacity"],
        ).T
        self.line_capacity = self.line_capacity.loc[
            self.line_capacity.index.repeat(365 * 24)
        ].reset_index(drop=True)
        self.line_capacity.index += 1

        self.max_line_capacity = self.line_capacity.max().max()

        # A user can use DataProcessor to generate pownet_cycle_map.json
        if self.dc_opf == "kirchhoff":
            with open(os.path.join(self.model_dir, "pownet_cycle_map.json")) as f:
                self.cycle_map = json.load(f)

        #################
        # System requirements
        #################

        self.spin_requirement = self.demand.sum(axis=1) * self.spin_reserve_factor

        #################
        # List of units
        #################
        self.thermal_units = list(self.thermal_unit_node.keys())
        self.hydro_units = list(self.hydro_unit_node.keys())
        self.solar_units = list(self.solar_unit_node.keys())
        self.wind_units = list(self.wind_unit_node.keys())
        self.import_units = list(self.import_unit_node.keys())

        #################
        # Node information
        #################
        self._store_generators_by_node()
        self._store_edges_by_node()

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
        # Similarly for hydropower, solar, wind, and import units
        if not set(self.hydro_unit_node.values()).issubset(self.nodes):
            raise ValueError(
                f"PowNet: Hydropower units must be connected to the grid: {set(self.hydro_unit_node.values()) - self.nodes}"
            )
        if not set(self.solar_unit_node.values()).issubset(self.nodes):
            raise ValueError(
                f"PowNet: Solar units must be connected to the grid: {set(self.solar_unit_node.values()) - self.nodes}"
            )
        if not set(self.wind_unit_node.values()).issubset(self.nodes):
            raise ValueError(
                f"PowNet: Wind units must be connected to the grid: {set(self.wind_unit_node.values()) - self.nodes}"
            )
        if not set(self.import_unit_node.values()).issubset(self.nodes):
            raise ValueError(
                f"PowNet: Import units must be connected to the grid: {set(self.import_unit_node.values()) - self.nodes}"
            )

        ##################################
        # Factors are between 0 and 1
        ##################################

        if not 0 <= self.spin_reserve_factor <= 1:
            raise ValueError("PowNet: Spin reserve factor must be between 0 and 1.")
        if not 0 <= self.line_loss_factor <= 1:
            raise ValueError("PowNet: Line loss factor must be between 0 and 1.")
        if not 0 <= self.line_capacity_factor <= 1:
            raise ValueError("PowNet: Line capacity factor must be between 0 and 1.")

        ##################################
        # Timeseries are of length 8760
        ##################################

        if len(self.demand) != 8760:
            raise ValueError("PowNet: Demand timeseries must be of length 8760.")
        if len(self.unit_marginal_cost) not in [0, 8760]:
            raise ValueError("PowNet: Marginal cost timeseries must be of length 8760.")
        if len(self.solar_capacity) not in [0, 8760]:
            raise ValueError("PowNet: Solar timeseries must be of length 8760.")
        if len(self.wind_capacity) not in [0, 8760]:
            raise ValueError("PowNet: Wind timeseries must be of length 8760.")
        if len(self.import_capacity) not in [0, 8760]:
            raise ValueError("PowNet: Import timeseries must be of length 8760.")

        if len(self.susceptance) != 8760:
            raise ValueError("PowNet: Line susceptance must be of length 8760.")
        if len(self.line_capacity) != 8760:
            raise ValueError("PowNet: Line capacity must be of length 8760.")

        # Hydropower is different
        if len(self.hydro_capacity) not in [0, 8760, 365]:
            raise ValueError(
                "PowNet: Hydropower timeseries must be of length 8760 or 365."
            )

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
        # Consistency in the number of units
        ##################################

        # The number of columns in self.marginal_cost must be equal to the number of units
        # (thermal, hydro, solar, wind, import)
        number_of_non_fossil_generators = len(
            self.hydro_unit_node
            | self.solar_unit_node
            | self.wind_unit_node
            | self.import_unit_node
        )
        if len(self.unit_marginal_cost.columns) != number_of_non_fossil_generators:
            raise ValueError(
                f"PowNet: The number of columns in marginal cost timeseries must be equal to the number of non-fossil generators. {len(self.unit_marginal_cost.columns)} != {number_of_non_fossil_generators}"
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
                f"PowNet: The number of edges in the node_edge dictionary must be equal to the number of edges. {sum(len(v) for v in self.node_edge.values())} != {2*len(self.edges)}"
            )

        ##################################
        # Generator names cannot repeat across different generator types and slack units (demand nodes)
        ##################################
        generators = (
            set(self.thermal_units)
            | set(self.hydro_units)
            | set(self.solar_units)
            | set(self.wind_units)
            | set(self.import_units)
        )
        if len(generators) != number_of_generators:
            raise ValueError(
                "PowNet: Generator names cannot repeat across different types."
            )

        ##################################
        # Generator names cannot be the same as the name of demand nodes
        ##################################
        if generators.intersection(self.demand_nodes):
            raise ValueError(
                "PowNet: Generator names cannot be the same as the name of demand nodes."
            )

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
        {'Peak demand':<25} = {self.demand.max().max()} MW

        ---- Renewable capacities ----
        {'Hydropower units':<25} = {len(self.hydro_unit_node)}
        {'Solar units':<25} = {len(self.solar_unit_node)}
        {'Wind units':<25} = {len(self.wind_unit_node)}
        {'Import units':<25} = {len(self.import_unit_node)}

        ---- Modeling parameters ----
        {'Simulation horizon':<25} = {self.sim_horizon} hours
        {'Use spin variable':<25} = {self.use_spin_var}
        {'Power flow':<25} = {self.dc_opf}
        {'Spin reserve factor':<25} = {self.spin_reserve_factor}
        {'Line loss factor':<25} = {self.line_loss_factor}
        {'Line capacity factor':<25} = {self.line_capacity_factor}
        {'Load shortfall penalty':<25} = {self.load_shortfall_penalty_factor}
        {'Reserve shortfall penalty':<25} = {self.spin_shortfall_penalty_factor}\n

        """
        )
        logger.info(input_summary)

    def load_and_check_data(self):
        self.load_data()
        self.check_data()

    def update_hydro_capacity(self, hydropower: pd.DataFrame):
        """Update the hydropower timeseries."""
        # Check that the dimension of the hydropower timeseries remains the same
        if len(hydropower) != len(self.hydro_capacity):
            raise ValueError(
                "PowNet: The length of the hydropower timeseries must remain the same."
            )
        # Check that all hydropower units are present
        if set(hydropower.columns) != set(self.hydro_capacity.columns):
            raise ValueError(
                "PowNet: The hydropower timeseries must contain all hydropower units."
            )
        self.hydro_capacity = hydropower.copy()
