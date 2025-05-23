
.. autosummary::
    :toctree: _source/
    
**Reservoir model**
=======================

**Reservoir Dynamics**

Reservoir storage hinges on a simple balance: water in (inflows) minus water out (releases, spills, losses) equals the change in storage. In discrete time (daily or hourly), we enforce:
    :math:`S_{t+1}=S_t+I_t-R_t-E_t`

where :math:`S_t` is the storage, :math:`I_t` the inflow, :math:`R_t` the release, and :math:`E_t` the evaporation.

In optimization formulations, the balance equation becomes an equality constraint linking decision variables (release, spill) and state variables (storage). Physical limits on storage (dead storage, maximum capacity) are imposed as inequality constraints to ensure feasible reservoir levels.

Besides storage, elevation is also often used as a measure of the state of a reservoir. The storage-elevation relationship :math:`S = f(h)` and its inverse :math:`h = f^{-1}(S)` can be non-linear and is defined by emprical volume curve :math:`vol\_curve`.

**Reservoir Operations**

We have two core modes of operation: rule-curve scheduling and dispatch-driven re-operation:
    
    * **Rule-curve scheduling**: Operators follow seasonal guidelines (rule curves) to choose releases to track a daily storage target while satisfying mass balance, spill, and min/max flow constraints. It has a deterministic target, such as daily storage or level targets derived from historical rule curves. Our optimization then minimizes the deviation from the target path.
    * **Dispatch-driven re-operation**: We invert a power‐dispatch target into release decisions. We adapt reservoir releases to meet daily or hourly power-generation targets from system dispatch, while still honoring mass balance and environmental rules. Our optimization there for solve for release sequence that minimizes mismatch between computed hydropower and dispatch targets, subject to mass balance, ramp-rate bounds, ecologoical minima, and turbine & grid limits. This is done based on hydropower physics, where we calculate the power :math:`P_t` from :math:`\eta` the turbine efficiency, :math:`\rho` the water density, :math:`g` the gravitational constant, :math:`H_t` the hydraulic head (water level above turbine center), and :math:`Q^{turbine}_t` the water flow through the turbine:
        :math:`P_t = \eta \cdot \rho \cdot g \cdot H_t \cdot Q^{turbine}_t`

**Environmental Flow & Hydropeaking Constraints**

To protect downstream ecosystems, maintain habitat, and prevent fish stranding, operations must respect minimum flow requirements and limit daily ramp‐rates (hydropeaking):
    
    * Minimum enviornmental flow: We determine the minimum amount of water that should be released from a reservoir to maintain the health of the downstream ecosystem. The minimum flow is set at different percentages of the inflow, subject to how the inflow compares with the mean annual flow.
    * Hydropeaking: Hydropeaking is the rapid and frequent changes in river flow to optimize hydropower operation. We adjust the release based on a hydropeaking factor and the minimum environmental flow, ensuring daily changes remain within a percentage of capacity.

**Cascade Coordination & Basin-Level Aggregation** 

In multi‐reservoir systems, upstream releases and spills directly become downstream inflows, creating interdependence. To manage reservoirs in a basin, we follow the modeling principles:

    * Sequential Processing: Order reservoirs by cascade level; each reservoir receives the combined outflow of upstream units as its inflow.
    * Simulation: Each reservoir at level uses the aggregated inflow from all upstream nodes.
    * Aggregation: Sum across reservoir columns to produce basin‐level time series for water release and hydropower, enabling performance metrics and system modeling.