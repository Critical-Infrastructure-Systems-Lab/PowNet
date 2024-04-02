"""
This script demonstrates how to read an MPS file with PuLP.
"""

import os

import gurobipy as gp
import highspy
import numpy as np
import pandas as pd

from pownet.folder_sys import get_output_dir


# CSpecify a file to read
mps_folder = os.path.join(get_output_dir(), "laos_24_instances")
mps_files = [file for file in os.listdir(mps_folder) if file.endswith(".mps")]
mps_file = mps_files[0]

# Read the MPS file
h = highspy.Highs()
h.readModel(os.path.join(mps_folder, mps_file))
h.run()

foo = h.getRunTime()


# Extract the solution
h_solution = h.getSolution()

# Check solver status
print(h.getModelStatus())
# h.getModelStatus().name == 'kOptimal'

h_info = h.getInfo()
print(h_info)
h_solution = h.getSolution()

# Check the solution
h_varnames = []
for i in range(h.getNumCol()):
    h_varnames.append(h.getColName(i))

h_solution
pd.DataFrame(
    {
        "varname": h_varnames,
        "value": h_solution.col_value,
    }
)


h.writeSolution("solution.sol", 0)
# Remove header in solution.sol
# We want lines after a line with "# Columns"
with open("solution.sol", "r") as file:
    lines = file.readlines()
    for i, line in enumerate(lines):
        if line.startswith("# Columns"):
            with open("solution_h.sol", "w") as file2:
                file2.write("".join(lines[i + 1 : -7]))
            break

# Remove the RHS section, which starts with "# Rows"
with open("solution_h.sol", "r") as file:
    lines = file.readlines()
    for i, line in enumerate(lines):
        if line.startswith("# Rows"):
            with open("solution_h.sol", "w") as file2:
                file2.write("".join(lines[:i]))
            break

# Have gurobi load the solution
m = gp.read(os.path.join(mps_folder, mps_file))
m.read("solution_h.sol")

# Check extracting the solutions

print(m.getVars())


"""
m.optimize()
# Write solution
m.write("solution_gp.sol")
"""
