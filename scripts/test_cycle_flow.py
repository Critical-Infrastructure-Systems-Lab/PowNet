import os

from gurobipy import GRB

import gurobipy as gp
import pandas as pd
import networkx as nx

from pownet.core.input import SystemInput
from pownet.folder_sys import get_model_dir



filename = os.path.join(get_model_dir(), 'dummy_trade', 'transmission.csv')
transmission_data = pd.read_csv(filename, header=0)

# Construct the incidence matrix (node-branch)
graph = nx.from_pandas_edgelist(
    transmission_data,
    source='source',
    target='sink',
    )
K_matrix = pd.DataFrame(
    nx.incidence_matrix(graph, oriented=True).todense(),
    columns = graph.edges,
    index = graph.nodes,
    )

# Construct the cycle matrix
cycles = nx.cycle_basis(graph)

# Try constructing the constraint
inputs = SystemInput(T=24, model_name='dummy_trade')

# Reorder
all_nodes = list(inputs.nodes)

model = gp.Model()

p = model.addVars(
    inputs.thermal_units,
    name = 'p'
    )

prnw = model.addVars(
    inputs.rnw_units,
    vtype = GRB.CONTINUOUS, lb = 0, name = 'prnw')

pimp = model.addVars(
    inputs.nodes_import,
    vtype = GRB.CONTINUOUS, lb = 0, name = 'prnw')

model.update()

generator_list = []
for generator_set in [p, prnw, pimp]:
    generator_list.extend(generator_set.keys())

# We only need power injection by generators
K_matrix_reduced = K_matrix.loc[generator_list]


flow = model.addVars(
    graph.edges, 
    lb = -1e7,
    vtype = GRB.CONTINUOUS
    )