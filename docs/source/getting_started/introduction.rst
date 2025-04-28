
.. autosummary::
    :toctree: _source/
    
################
 Introduction
################

**Background**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

PowNet is an open-source Production Cost Model (PCM) framework designed to simulate the least-cost operation
of large-scale power systems, such as those spanning entire regions or countries. Written in Python,
it tackles the fundamental challenge of meeting electricity demand subject to techno-economic constraints.

PowNet is implemented entirely in Python, leveraging popular and established packages. For building and interacting with the optimization model, PowNet uses Gurobipy, the Python API for the high-performance Gurobi optimizer. This choice was driven by Gurobipy's proven performance compared to other frameworks. Other dependencies include Pandas, SciPy, and NetworkX.

PowNet supports multiple optimization solvers:
    * **Gurobi:** A powerful commercial solver (Gurobi provides free academic licenses).
    * **HiGHS:** A competitive open-source solver, providing an accessible alternative.



**Target users and their use cases**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

PowNet caters to both users primarily interested in applying the model and those focused on research and development. Simulating a power system is
achieved in a low-code environment as the user Define power system components (generators, lines, nodes), economic parameters, and time-series data
(demand, renewable availability) using simple CSV files (spreadsheets), making model setup accessible even with basic Python knowledge.

For advanced users, PowNet's modular design allows for easy customization and extension of the model, enabling the integration of new features or constraints. Furthermore, the model's flexibility allows for experimentation with different formulations and algorithms.

Example use cases based on past research publications can be found :doc:`here </reference/publications>`.



**Model functionalities**
~~~~~~~~~~~~~~~~~~~~~~~~~~~

PowNet incorporates several key functionalities to support comprehensive power system analysis:

* **CSV Data Input:** Relies on easily understandable CSV files for all model inputs, simplifying data preparation and management

* **Data Validation:** Includes checks within the workflow to help ensure data consistency

* **Multi-Solver Support:** Compatible with both commercial (Gurobi) and open-source (HiGHS) solvers
* **Comprehensive output processing:** Generates results (e.g., generator dispatch schedules, costs, line flows) as Pandas DataFrames or CSV files for easy analysis and post-processing. Visualization capabilities are also part of the workflow
* **Reservoir Simulation Module:** Includes a dedicated module to simulate the operation of single or cascaded reservoirs, calculating hourly hydropower energy availability based on inflow data and operational rules. This is crucial for systems with significant hydropower capacity and for water-energy nexus studies
* **Stochastic Time Series Generation:** Provides functionality to generate synthetic time series for inputs like electricity demand or VRE availability, based on historical data patterns. This enables Monte Carlo simulations and analysis under uncertainty
* **Custom Constraint API:** While providing a core formulation, PowNet is designed to be extensible, allowing advanced users to define and incorporate custom constraints into the optimization problem


.. bibliography::

