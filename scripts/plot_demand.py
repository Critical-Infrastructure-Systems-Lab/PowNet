import os

import matplotlib.pyplot as plt

from pownet.core.input import SystemInput

T = 24*2

# One year has 8760 hours. If T = 24, then we have 365 steps.
# steps = floor(8760/self.T)
steps = 1

model_folder = 'user_inputs'

# We need a folder to store the figures
if not os.path.exists('..//outputs'):
    os.makedirs('..//outputs')

system_input = SystemInput(T=T, model_folder=model_folder)

demand = system_input.demand[:24].sum(axis=1)


fig, ax = plt.subplots(figsize=(8, 5))
demand.plot(ax=ax)
ax.legend(bbox_to_anchor=(1, 1))
ax.set_ylabel('Power (MW)')
ax.set_xlabel('Hour')
ax.set_ylim(bottom=0)


