import gurobipy as gp
from gurobipy import GRB

model = gp.Model("thailand_13.mps")

model.optimize()
# Check model status
if model.status == gp.GRB.INFEASIBLE:
    model.computeIIS()
    model.write("thailand_13.ilp")

else:
    print("Optimal solution found")
