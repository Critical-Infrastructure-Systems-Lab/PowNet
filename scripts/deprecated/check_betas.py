# This script creates a dataframe to check the betas
import pandas as pd
from benchmark_dw import dw_instance, record



master_vars = dw_instance.master_problem.model.getVars()
betas = [gp_var for gp_var in master_vars if gp_var.varname.startswith('B(')]

non_zero_betas = [beta for beta in betas if beta.X > 0]

beta_summary = pd.DataFrame(
    {
      'variable': [v.varname for v in non_zero_betas],
      'value': [v.X for v in non_zero_betas]
      })

p = r'B\((?P<j>\d+),(?P<i>\d+)\)'
beta_summary[['block_id', 'dw_iter']] = beta_summary['variable'].str.extract(p)
beta_summary = beta_summary.sort_values(by=['block_id', 'dw_iter'])

# Create another dataframe with solution on the columns