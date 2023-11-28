from pownet.input_processor import InputProcessor

frequency = 50
model_name = 'dummy_trade'

input_processor = InputProcessor(
    year = 2016,
    model_name=model_name, 
    frequency=frequency
    )

input_processor.transform_transmission_inputs()
input_processor.get_cycle_map()

input_processor.get_derate_factors(derate_factor=1)
input_processor.get_derated_max_capacities()