from pownet.processing.inputs import InputProcessor

frequency = 60
model_name = 'dummy_trade'

input_processor = InputProcessor(model_name=model_name, frequency=frequency)

foo = input_processor.transform()

