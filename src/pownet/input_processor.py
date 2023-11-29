from collections import defaultdict
import json
import os

import networkx as nx
import numpy as np
import pandas as pd

from pownet.folder_sys import get_model_dir, get_database_dir
from pownet.processing.functions import get_dates


class InputProcessor:
    def __init__(
            self,
            year: int,
            model_name: str,
            frequency: int
            ) -> None:
        
        self.year = year
        self.model_name = model_name
        self.frequency = frequency
        
        wavelengths = {50:6000, 60: 5000} # in km
        self.wavelength = wavelengths[frequency]
        
        # Note that we will modify the original file
        self.model_folder = os.path.join(get_model_dir(), model_name)
        
        self.transmission_file = os.path.join(self.model_folder, 'transmission.csv')
        self.transmission_data = pd.read_csv(self.transmission_file, header=0)
        
        # We use these parameters for calculations
        self.transmission_params = pd.read_csv(
            os.path.join(get_database_dir(), 'transmission_params.csv'),
            ).set_index('kv').to_dict(orient='dict')
        
    
    def calc_stability_limit(
            self, 
            source_kv: int, 
            sink_kv: int, 
            distance: float, 
            wavelength: int, 
            n_circuits: int
            ) -> float:
        ''' From Chapter 5 of Power System Analysis and Design 5th (EQ 5.4.30)
        '''
        max_kv = max(source_kv, sink_kv)
        reactance_per_km = self.transmission_params['reactance_ohms_per_km'][max_kv]
        # Calculate the Surge Impedance Limit (SIL)
        sil = source_kv*sink_kv/reactance_per_km/1000 # Divide by 1000 to get MW
        stability_limit_per_circuit = sil/np.sin(2*np.pi*distance/wavelength)
        return round(n_circuits*stability_limit_per_circuit, 0)
        
    
    # Calculate the steady-state stability limit
    def calc_thermal_limit(
            self,
            source_kv: int ,
            sink_kv: int,
            n_circuits: int
            ) -> float:
        ''' From Chapter 5 of Power System Analysis and Design 5th. See Example 5.6b.
        The full-load current at 1 per-unit factor is
              I = P/(sqrt(3) * V)
        Here, P is the surge impedance factor (SIL) and V is the voltage of the
        receiving bus. This voltage is the minimum voltage between the two ends.
        '''
        max_kv = max(source_kv, sink_kv)
        n_conductors = self.transmission_params['n_conductors'][max_kv]
        current_capacity = self.transmission_params['current_capacity_amps'][max_kv] # in A
        
        total_current_capacity = n_conductors*current_capacity/1000 # in kilo-A
        thermal_limit_per_circuit = total_current_capacity*np.sqrt(3)*max_kv
        return round(n_circuits*thermal_limit_per_circuit, 0)
    
    
    def get_transmission_capacity(self) -> None:
        self.transmission_data['pownet_stability_limit'] = self.transmission_data.apply(
            lambda x: self.calc_stability_limit(
                x['source_kv'], x['sink_kv'], x['distance'], self.wavelength, x['n_circuits']
                ),
            axis=1
            )
        
        self.transmission_data['pownet_thermal_limit'] = self.transmission_data.apply(
            lambda x: self.calc_thermal_limit(
                x['source_kv'], x['sink_kv'], x['n_circuits']
                ),
            axis=1
            )
        # The transmission limit is the minimum of the thermal limit and
        # the steady-state steability limit. Normally, distance is the deciding factor.
        self.transmission_data['pownet_line_capacity'] =\
            self.transmission_data[['pownet_thermal_limit', 'pownet_stability_limit']]\
            .min(axis=1)
    
    
    def get_transmission_susceptance(self) -> None:
        ''' This is the susceptance of the line segment. The unit is in siemens-km
        '''
        source_sink = pd.DataFrame(
            self.transmission_data['source_kv'].values,
            columns = ['source_kv'])
        
        source_sink['sink_kv'] = self.transmission_data['sink_kv']
        source_sink['max_kv'] = source_sink.max(axis=1)
        
        source_sink['reactance_per_km'] = source_sink.apply(
            lambda x: self.transmission_params['reactance_ohms_per_km'][x['max_kv']],
            axis = 1
            )
        
        self.transmission_data['pownet_reactance_pu'] =\
            source_sink['reactance_per_km'] * self.transmission_data['distance']
            
        self.transmission_data['pownet_susceptance'] = self.transmission_data.apply(
            lambda x: int(x['source_kv'] * x['sink_kv'] / x['pownet_reactance_pu']),
            axis = 1)
    

    def transform_transmission_inputs(self, to_write: bool = True) -> None:
        self.get_transmission_capacity()
        self.get_transmission_susceptance()
        # Write the new columns
        if to_write:
            self.transmission_data.to_csv(self.transmission_file, index=False)
            
            
    def create_cycle_map(self, to_write: bool = True) -> None:
        # Find all the basic cycles in the transmission system
        graph = nx.from_pandas_edgelist(
            self.transmission_data,
            source='source',
            target='sink',
            )
        cycles = nx.cycle_basis(graph)
        
        # We save this map to use by the ModelBuilder
        cycle_map = {f'cycle_{idx+1}': cycle for idx, cycle in enumerate(cycles)}
        
        # Save in the model_library/model_name folder so we only need to find
        # the cycles once
        with open(os.path.join(self.model_folder, 'pownet_cycle_map.json'), 'w') as f:
            json.dump(cycle_map, f)
        
        
    def get_derate_factors(
            self, 
            derate_factor: float = 1.00, 
            to_write: bool = True
            ) -> None:
        ''' Create a csv file called "pownet_derate_factor.csv" in
        moddel_library/{model_name} folder
        '''
        derate_df = get_dates(self.year)
        # Get the thermal units
        model_dir = os.path.join(get_model_dir(), self.model_name)
        thermal_units = pd.read_csv(os.path.join(model_dir, 'unit_param.csv'))['name'].values
        derate_df[thermal_units] = derate_factor
        
        if to_write:
            derate_df.to_csv(
                os.path.join(self.model_folder, 'pownet_derate_factor.csv'),
                index = False
                )
            
            
    def create_derated_max_capacities(
            self,
            to_write: bool = True
            ) -> None:
        ''' Create a dict of derated generation capacity of thermal units.
        The structure of this is
        {
            'unit_a': {
                1: maxcap*derated_factor_1,
                2: maxcap*derated_factor_2,
                ...
                T: maxcap*derated_factor_T
                }
            }
        '''
        derate_path = os.path.join(self.model_folder, 'pownet_derate_factor.csv')
        derate_df = pd.read_csv(derate_path, header=0)
        
        max_cap = pd.read_csv(
            os.path.join(self.model_folder, 'unit_param.csv'),
            header=0, index_col='name', usecols=['name', 'max_capacity']
            ).to_dict()['max_capacity']
        
        derated_max_cap = pd.DataFrame()
        for thermal_unit in max_cap.keys():
            derated_max_cap[thermal_unit] = derate_df[thermal_unit]*max_cap[thermal_unit]
        
        derated_max_cap = pd.concat(
            [get_dates(year=self.year), derated_max_cap],
            axis =1
            )
        # Pownet indexing starts at 1 and usually ends at 8760.
        derated_max_cap.index += 1
        
        derated_max_cap.to_csv(
            os.path.join(self.model_folder, 'pownet_derated_capacity.csv'),
            index = False
            )
        
        
    def create_fuelprice(self) -> None:
        ''' Create a dataframe of hourly fuel price of each generator
        from fuel_map.csv.
        '''
        fuel_map = pd.read_csv(
            os.path.join(self.model_folder, 'fuel_map.csv')
            ).dropna()
        
        fuelprice = fuel_map[['name', 'fuel_price_optional']].set_index('name').T
        fuelprice.index = [0]
        
        fuelprice = pd.concat(
            [get_dates(year=self.year), fuelprice],
            axis = 1
            )
        fuelprice = fuelprice.ffill()
        
        fuelprice.to_csv(
            os.path.join(self.model_folder, 'fuel_price.csv'),
            index = False
            )
        
        
    
        

        