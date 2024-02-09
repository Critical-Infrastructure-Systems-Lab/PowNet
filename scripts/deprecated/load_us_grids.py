import json
import os

from pownet.folder_sys import get_model_dir


filename = os.path.join(get_model_dir(), 'us', 'rts_0.json')

with open(filename) as f:
    data = json.load(f)


sections = data.keys()
