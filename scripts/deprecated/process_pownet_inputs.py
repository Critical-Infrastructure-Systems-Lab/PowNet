''' This script prepares the input files based on user inputs. This script calls the InputProcessor class.
- Append line capacities to transmission.csv
- create fuel_price.csv
- create pownet_cycle_map.json
- create derate_factor.csv
- create pownet_derate_factor.csv
- create pownet_derated_capacity.csv
'''

from pownet.input_processor import InputProcessor

frequency = 50
model_name = 'thailand'

input_processor = InputProcessor(
    year = 2016,
    model_name=model_name, 
    frequency=frequency
    )

input_processor.transform_transmission_inputs()
input_processor.create_cycle_map()

input_processor.create_derate_factors(derate_factor=1)
input_processor.create_derated_max_capacities()
# input_processor.create_fuelprice()