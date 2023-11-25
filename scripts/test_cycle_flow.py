import os

from gurobipy import GRB

import gurobipy as gp
import pandas as pd
import networkx as nx
import numpy as np

from pownet.core.input import SystemInput
from pownet.core.builder import ModelBuilder
from pownet.folder_sys import get_model_dir



filename = os.path.join(get_model_dir(), 'thailand', 'transmission.csv')
transmission_data = pd.read_csv(filename, header=0)

# Construct the incidence matrix (node-branch)
graph = nx.from_pandas_edgelist(
    transmission_data,
    source='source',
    target='sink',
    )
# K_matrix = pd.DataFrame(
#     nx.incidence_matrix(graph, oriented=True).todense(),
#     columns = graph.edges,
#     index = graph.nodes,
#     )

# Construct the cycle matrix
cycles = nx.cycle_basis(graph)
cycle_map = {f'cycle_{idx+1}': cycle for idx, cycle in enumerate(cycles)}


# Construct the cycle matrix C[arc, cycle]. We first need to list all the arcs
inputs = SystemInput(T=24, model_name='dummy_cycle')

cycle_incidence = pd.DataFrame(
    0,
    index = pd.MultiIndex.from_tuples(inputs.arcs, names=["source", "sink"]),
    columns = cycle_map.keys()
    )

builder = ModelBuilder(inputs)
builder.model = gp.Model('UCED_Simulation')
builder.k = 0
builder._add_variables()

# The flow is positive with respect to the edges specified by the user
for cycle_id, cycle in cycle_map.items():
    # Kirchhoff formulation requires summing along the loop direction.
    # If an arc is in cycle_graph and the input file, then 1. Otherwise, -1.
    cycle_graph = nx.path_graph(cycle)
    cycle_arcs = list(cycle_graph.edges)
    # Append the last arc connecting the last node to the first node
    cycle_arcs.append(
        (cycle_arcs[-1][-1], cycle_arcs[0][0]))
    
    # We also need the reactance (susceptance) to calculate the factors in the cycle-incidence
    cycle_susceptance = pd.DataFrame() 
    for flow in cycle_arcs:
        if flow in inputs.arcs:
            cycle_incidence.loc[flow, cycle_id] = 1
            cycle_susceptance = pd.concat(
                [cycle_susceptance, inputs.suscept[flow]],
                axis = 1
                )
        else:
            cycle_incidence.loc[(flow[1], flow[0]), cycle_id] = -1
            cycle_susceptance = pd.concat(
                [cycle_susceptance, inputs.suscept[(flow[1], flow[0])]],
                axis = 1
                )

    # Try constructing the constraint
    # Equation 23b in Horsch et al (2018)
    builder.model.addConstrs(
        (
         gp.quicksum(
             (cycle_incidence.loc[(a, b), cycle_id]
                 * 1/cycle_susceptance.loc[t + builder.T*builder.k, [(a, b)]]
                 * builder.flow[a, b, t])[0]
                 for (a, b) in cycle_susceptance.columns
                 ) 
             == 0
            for t in builder.timesteps
        ),
        name = f'kirchhoff_{cycle_id}'
        )

builder.model.update()
builder.model.write('test_cycle.lp')

