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