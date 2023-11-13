import os

import networkx as nx
import pandas as pd

from pownet.folder_sys import get_model_dir

filename = os.path.join(get_model_dir(), 'dummy_trade', 'transmission.csv')
transmission_data = pd.read_csv(filename, header=0)

# Construct the incidence matrix (node-branch)
graph = nx.from_pandas_edgelist(
    transmission_data,
    source='source',
    target='sink'
    )
K_matrix = pd.DataFrame(
    nx.incidence_matrix(graph).todense(),
    columns = graph.edges,
    index = graph.nodes
    )

# Construct the cycle matrix
cycles = nx.cycle_basis(graph)


