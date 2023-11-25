import json
import os

import gurobipy as gp
import pandas as pd

from pownet.processing.functions import get_arcs, get_linecap, get_suscept
from pownet.folder_sys import get_model_dir



# Current code does not need these columns
DATE_COLS = ['year', 'month', 'day', 'hour']



class SystemInput:
    def __init__(
            self, 
            T: int, 
            model_name: str,
            F_SPIN: float = 0.15,
            price: str = 'fuel',
            aggregated_generator: bool = False,
            reverse_flow: bool = False
            ) -> None:
        '''
        Read the user inputs that define the power system over one year.

        Returns
        -------
        None

        '''
        self.T = T

        self.model_dir: str = os.path.join(get_model_dir(), model_name)
        
        # User inputs
        self.demand: pd.DataFrame = pd.read_csv(
            os.path.join(self.model_dir, 'demand_export.csv'),
            header=0).drop(DATE_COLS, axis=1)
        self.demand.index += 1
        
        self.derating: pd.DataFrame = pd.read_csv(
            os.path.join(self.model_dir, 'derate_factor.csv'),
            header=0).drop(DATE_COLS, axis=1)
        self.derating.index += 1
        
        self.fuelmap: pd.DataFrame = pd.read_csv(
            os.path.join(self.model_dir, 'fuel_map.csv'),
            header=0)
        
        if aggregated_generator:
            self.node_generator_map: pd.DataFrame = pd.read_csv(
                os.path.join(self.model_dir, 'fuel_map.csv'),
                header=0)
        
        self.fuelprice: pd.DataFrame = pd.read_csv(
            os.path.join(self.model_dir, 'fuel_price.csv'),
            header=0).drop(DATE_COLS, axis=1)
        self.fuelprice.index += 1
        
        self.rnw_cap: pd.DataFrame = pd.read_csv(
            os.path.join(self.model_dir, 'renewable.csv'),
            header=0).drop(DATE_COLS, axis=1)
        self.rnw_cap.index += 1
        
        self.thermal_units: list = pd.read_csv(
            os.path.join(self.model_dir, 'unit_param.csv'), 
            header = 0, index_col='name', usecols = ['name']).index.tolist()
        
        self.transmission: pd.DataFrame = pd.read_csv(
            os.path.join(self.model_dir, 'transmission.csv'),
            header = 0)
        
        self.unit_econ: pd.DataFrame = pd.read_csv(
            os.path.join(self.model_dir, 'unit_param.csv'),
            header = 0, index_col = 'name',
            usecols = ['name', 'operation_cost', 'fixed_cost', 'startup_cost']
            )
        
        self.heat_rate: pd.DataFrame = pd.read_csv(
            os.path.join(self.model_dir, 'unit_param.csv'),
            header = 0, index_col = 'name', 
            usecols = ['name', 'heat_rate']
            )
        
        # Import nodes are treated similary to a renewable but with higher cost
        fn_import =   os.path.join(self.model_dir, 'import.csv')
        if os.path.exists(fn_import):
            self.p_import: pd.DataFrame = pd.read_csv(
                fn_import,
                header=0).drop(DATE_COLS, axis=1)
            self.p_import.index += 1
        
        
        # System nodes
        self.nodes_w_demand: list = self.demand.columns.tolist()
        self.rnw_units: list = self.rnw_cap.columns.tolist()
        self.nodes_import: list = self.p_import.columns.tolist()
        # A node does not need to be connected. In this case,
        # we are concerned about unconnected nodes with demand.
        self.nodes: set = set(self.transmission.source)\
                              .union(set(self.transmission.sink))\
                                .union(set(self.nodes_w_demand))\
        
        # Transmission lines
        self.arcs: gp.tuplelist = get_arcs(
            self.transmission,
            reverse_flow = reverse_flow
            )
        with open(os.path.join(self.model_dir, 'pownet_cycle_map.json')) as f:
            self.cycle_map: dict = json.load(f)
        
        self.linecap: pd.DataFrame = get_linecap(
            self.transmission,
            reverse_flow=reverse_flow
            )
        self.linecap.index += 1
        
        self.suscept: pd.DataFrame = get_suscept(
            self.transmission,
            reverse_flow=reverse_flow
            )
        self.suscept.index += 1
        
        # Thermal unit params
        self.max_cap: dict = pd.read_csv(
            os.path.join(self.model_dir, 'unit_param.csv'),
            header=0, index_col='name', usecols=['name', 'max_capacity']
            ).to_dict()['max_capacity']
        
        self.min_cap: dict = pd.read_csv(
            os.path.join(self.model_dir, 'unit_param.csv'),
            header=0, index_col='name', usecols=['name', 'min_capacity']
            ).to_dict()['min_capacity']
        
        self.TD: dict = pd.read_csv(
            os.path.join(self.model_dir, 'unit_param.csv'),
            header=0, index_col='name', usecols=['name', 'min_downtime']
            ).to_dict()['min_downtime']
        
        self.TU: dict = pd.read_csv(
            os.path.join(self.model_dir, 'unit_param.csv'),
            header=0, index_col='name', usecols=['name', 'min_uptime']
            ).to_dict()['min_uptime']
        
        self.SD: dict = pd.read_csv(
            os.path.join(self.model_dir, 'unit_param.csv'), 
            header=0, index_col='name', usecols=['name', 'min_capacity']
            ).to_dict()['min_capacity']
        self.SU: dict = self.SD.copy()
        
        self.RD: dict = pd.read_csv(
            os.path.join(self.model_dir, 'unit_param.csv'),
            header=0, index_col='name', usecols=['name', 'ramp_rate']
            ).to_dict()['ramp_rate']
        self.RU: dict = self.RD.copy()
        
        # Calculated parameters
        self.max_node: str = self.demand.idxmax().idxmax()
        self.max_linecap: int = self.linecap.max().max()
        # The first index of spin_req is already at 1
        self.spin_req: pd.DataFrame = self.demand.sum(axis=1) * F_SPIN
        
        