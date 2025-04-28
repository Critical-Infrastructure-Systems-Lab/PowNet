
.. autosummary::
    :toctree: _source/
    
**Mathematical Formulation**
==============================

**The Unit Commitment Problem**

PowNet solves the unit commitment problem (UCP), which is an optimization problem
to determine the optimal schedule for starting up, shutting down, and outputing power of power stations
(like coal, natural gas, hydro, etc.) over a specific time horizon (typically day-ahead).
The primary goal is to minimize the total operational cost, which includes fuel costs, start-up/shutdown costs for thermal units,
and potentially other operational expenses, while ensuring that electricity generation consistently meets
the fluctuating demand and respects various operational constraints.

**Mathematical Formulation**

The UCP in PowNet is formulated as a Mixed-Integer Linear Program (MILP). This means
the model uses a combination of continuous variables (like power output) and integer (specifically binary) variables,
primarily to represent the on/off status of thermal generators and their start-up/shutdown decisions.

The model's objective function aims to minimize total system costs, including:
    * Variable costs based on fuel consumption (heat rate) and operational expenses
    * Fixed costs incurred when thermal units are online
    * Start-up costs for thermal units
    * Costs associated with renewable generation and imports
    * Penalties for failing to meet demand or required operating reserves
    * Penalties for violating generation contracts

This objective is minimized subject to a comprehensive set of constraints representing real-world physical and operational limitations:
    * **Thermal Unit Constraints:** Generation limits (min/max power), minimum up-time and down-time requirements, and ramping limits (how quickly units can change output).
    * **Renewable/Import Limits:** Constraints on the maximum available power from sources like solar, wind, hydro, and imports at each time step.
    * **Transmission Network Constraints:** Modeled using a linearized DC power flow approximation, which balances computational efficiency with network representation.
    * **System Constraints:** Nodal energy balance (ensuring power supply equals demand plus losses at each location) and system-wide spinning reserve requirements (maintaining sufficient online capacity to handle unexpected outages or demand spikes).

While there are multiple ways to formulate the mathematical problem, the formulations implemented were chosen based on benchmarking exercises for computational efficiency.
Formal mathematical descriptions can be found in :cite:p:`bunnak2025bridging`.
