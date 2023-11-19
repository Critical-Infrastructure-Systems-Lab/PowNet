import os

import numpy as np
import pandas as pd

from pownet.folder_sys import get_model_dir, get_database_dir


class InputProcessor:
    def __init__(
            self,
            model_name: str,
            frequency: int
            ) -> None:
        
        self.model_name = model_name
        self.frequency = frequency
        
        wavelengths = {50:6000, 60: 5000} # in km
        self.wavelength = wavelengths[frequency]
        
        # Note that we will modify the original file
        model_folder = os.path.join(get_model_dir(), model_name)
        self.transmission_file = os.path.join(model_folder, 'transmission.csv')
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
    

    def transform(self, to_write: bool = True) -> None:
        self.get_transmission_capacity()
        self.get_transmission_susceptance()
        # Write the new columns
        if to_write:
            self.transmission_data.to_csv(self.transmission_file, index=False)
        
        