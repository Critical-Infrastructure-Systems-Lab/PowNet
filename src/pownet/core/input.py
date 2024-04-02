import json
import os

import gurobipy as gp
import pandas as pd

from pownet.config import get_spin_reserve_factor
from pownet.processing.functions import get_arcs, get_linecap, get_suscept
from pownet.folder_sys import get_model_dir


# Current code does not need these columns
DATE_COLS = ["year", "month", "day", "hour", "date"]


class SystemInput:
    def __init__(
        self,
        T: int,
        formulation: str,
        model_name: str,
        price: str = "fuel",
        reverse_flow: bool = False,
    ) -> None:

        self.T: int = T
        self.formulation: str = formulation
        self.model_name: str = model_name

        self.model_dir: str = os.path.join(get_model_dir(), model_name)

        # User inputs
        self.year: int = pd.read_csv(
            os.path.join(self.model_dir, "demand_export.csv"), header=0
        )["year"].iloc[0]

        self.thermal_units: list = pd.read_csv(
            os.path.join(self.model_dir, "unit_param.csv"),
            header=0,
            index_col="name",
            usecols=["name"],
        ).index.tolist()

        self.transmission: pd.DataFrame = pd.read_csv(
            os.path.join(self.model_dir, "transmission.csv"), header=0
        )

        self.unit_econ: pd.DataFrame = pd.read_csv(
            os.path.join(self.model_dir, "unit_param.csv"),
            header=0,
            index_col="name",
            usecols=["name", "operation_cost", "fixed_cost", "startup_cost"],
        )

        self.heat_rate: pd.DataFrame = pd.read_csv(
            os.path.join(self.model_dir, "unit_param.csv"),
            header=0,
            index_col="name",
            usecols=["name", "heat_rate"],
        )

        # Read timeseries data
        # The index of timeseries starts at 1
        self.demand: pd.DataFrame = pd.read_csv(
            os.path.join(self.model_dir, "demand_export.csv"), header=0
        ).drop(DATE_COLS, axis=1, errors="ignore")
        self.demand.index += 1

        self.derating: pd.DataFrame = pd.read_csv(
            os.path.join(self.model_dir, "pownet_derate_factor.csv"), header=0
        ).drop(DATE_COLS, axis=1, errors="ignore")
        self.derating.index += 1

        self.fuelprice: pd.DataFrame = pd.read_csv(
            os.path.join(self.model_dir, "fuel_price.csv"), header=0
        ).drop(DATE_COLS, axis=1, errors="ignore")
        self.fuelprice.index += 1

        # Read timeseries data for renewables
        hydro_fn = os.path.join(self.model_dir, "hydro.csv")
        if os.path.exists(hydro_fn):
            self.hydro_cap: pd.DataFrame = pd.read_csv(hydro_fn, header=0).drop(
                DATE_COLS, axis=1, errors="ignore"
            )
            self.hydro_cap.index += 1
            self.hydro_units: list = self.hydro_cap.columns.tolist()
        else:
            self.hydro_cap = pd.DataFrame()
            self.hydro_units = []

        solar_fn = os.path.join(self.model_dir, "solar.csv")
        if os.path.exists(solar_fn):
            self.solar_cap: pd.DataFrame = pd.read_csv(solar_fn, header=0).drop(
                DATE_COLS, axis=1, errors="ignore"
            )
            self.solar_cap.index += 1
            self.solar_units: list = self.solar_cap.columns.tolist()
        else:
            self.solar_cap = pd.DataFrame()
            self.solar_units = []

        wind_fn = os.path.join(self.model_dir, "wind.csv")
        if os.path.exists(wind_fn):
            self.wind_cap: pd.DataFrame = pd.read_csv(wind_fn, header=0).drop(
                DATE_COLS, axis=1, errors="ignore"
            )
            self.wind_cap.index += 1
            self.wind_units: list = self.wind_cap.columns.tolist()
        else:
            self.wind_cap = pd.DataFrame()
            self.wind_units = []

        # Import nodes are treated similary to a renewable but with higher cost
        fn_import = os.path.join(self.model_dir, "import.csv")
        if os.path.exists(fn_import):
            self.p_import: pd.DataFrame = pd.read_csv(fn_import, header=0).drop(
                DATE_COLS, axis=1, errors="ignore"
            )
            self.p_import.index += 1
            self.nodes_import: list = self.p_import.columns.tolist()
        else:
            self.p_import = pd.DataFrame()
            self.nodes_import = []

        # System nodes
        self.nodes_w_demand: list = self.demand.columns.tolist()

        # Map units to their fuel type beginning with thermal units,
        # then hydro, solar, wind, import, and demand nodes
        self.fuelmap = pd.read_csv(
            os.path.join(self.model_dir, "unit_param.csv"),
            header=0,
            usecols=["name", "fuel_type"],
        ).set_index("name").to_dict()['fuel_type']

        self.fuelmap.update(
            {node: "hydro" for node in self.hydro_units}
        )
        self.fuelmap.update(
            {node: "solar" for node in self.solar_units}
        )
        self.fuelmap.update(
            {node: "wind" for node in self.wind_units}
        )
        self.fuelmap.update(
            {node: "import" for node in self.nodes_import}
        )

        self.fuelmap.update(
            {node: "slack" for node in self.nodes_w_demand}
        )

        # A node does not need to be connected. In this case,
        # we are concerned about unconnected nodes with demand.
        self.nodes: set = (
            set(self.transmission.source)
            .union(set(self.transmission.sink))
            .union(set(self.nodes_w_demand))
        )
        # Transmission lines
        self.arcs: gp.tuplelist = get_arcs(
            self.transmission,
            reverse_flow=reverse_flow,
        )

        self.linecap: pd.DataFrame = get_linecap(
            self.transmission,
            reverse_flow=reverse_flow,
        )
        self.linecap.index += 1

        self.suscept: pd.DataFrame = get_suscept(
            self.transmission,
            reverse_flow=reverse_flow,
        )
        self.suscept.index += 1

        # User should use the PowNet processing function to identify the basic cycles
        if formulation == "kirchhoff":
            with open(os.path.join(self.model_dir, "pownet_cycle_map.json")) as f:
                self.cycle_map: dict = json.load(f)

        # Thermal unit params
        self.full_max_cap: dict = pd.read_csv(
            os.path.join(self.model_dir, "unit_param.csv"),
            header=0,
            index_col="name",
            usecols=["name", "max_capacity"],
        ).to_dict()["max_capacity"]

        # The maximum capacity is reduced by the derating factor
        self.max_cap: dict = (
            pd.read_csv(
                os.path.join(self.model_dir, "pownet_derated_capacity.csv"), header=0
            )
            .drop(DATE_COLS, axis=1, errors="ignore")
            .to_dict()
        )

        self.min_cap: dict = pd.read_csv(
            os.path.join(self.model_dir, "unit_param.csv"),
            header=0,
            index_col="name",
            usecols=["name", "min_capacity"],
        ).to_dict()["min_capacity"]

        self.TD: dict = pd.read_csv(
            os.path.join(self.model_dir, "unit_param.csv"),
            header=0,
            index_col="name",
            usecols=["name", "min_downtime"],
        ).to_dict()["min_downtime"]

        self.TU: dict = pd.read_csv(
            os.path.join(self.model_dir, "unit_param.csv"),
            header=0,
            index_col="name",
            usecols=["name", "min_uptime"],
        ).to_dict()["min_uptime"]

        self.SD: dict = pd.read_csv(
            os.path.join(self.model_dir, "unit_param.csv"),
            header=0,
            index_col="name",
            usecols=["name", "min_capacity"],
        ).to_dict()["min_capacity"]
        self.SU: dict = self.SD.copy()

        self.RD: dict = pd.read_csv(
            os.path.join(self.model_dir, "unit_param.csv"),
            header=0,
            index_col="name",
            usecols=["name", "ramp_rate"],
        ).to_dict()["ramp_rate"]
        self.RU: dict = self.RD.copy()

        # Calculated parameters
        self.max_node: str = self.demand.idxmax().idxmax()
        self.max_linecap: int = self.linecap.max().max()
        # The first index of spin_req is already at 1
        SPIN_FACTOR = get_spin_reserve_factor()
        self.spin_req: pd.DataFrame = self.demand.sum(axis=1) * SPIN_FACTOR
