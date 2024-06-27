import os
import matplotlib.pyplot as plt
import gurobipy as gp

from pownet.folder_sys import get_output_dir

MODEL_NAME = "cambodia"


pdir = os.path.dirname(os.getcwd())
path_mps = os.path.join(
    get_output_dir(), f"{MODEL_NAME}_24_instances", f"{MODEL_NAME}_0.mps"
)

model = gp.read(path_mps)

A_mat = model.getA()

fig, ax = plt.subplots(figsize=(7, 7))
ax.spy(A_mat, markersize=1)
ax.set_xlabel("Variable ID")
ax.set_ylabel("Constraint ID")
plt.show()
