from pownet.processing.inputs import InputProcessor

frequency = 50
model_name = 'malaysia'

input_processor = InputProcessor(model_name=model_name, frequency=frequency)

foo = input_processor.transform()

