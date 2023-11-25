from pownet.processing.inputs import InputProcessor

frequency = 50
model_name = 'malaysia'

input_processor = InputProcessor(model_name=model_name, frequency=frequency)
input_processor.transform_transmission_inputs()
input_processor.get_cycle_map()
