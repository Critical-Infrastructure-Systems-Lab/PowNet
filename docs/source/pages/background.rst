
**1. Model Background**
======================

PowNet is a least-cost optimization model for simulating the Unit Commitment and
Economic Dispatch (UC/ED) of large-scale (regional to country) power systems.
In PowNet, a power system is represented by a set of nodes that include power plants,
substations, and import/export stations (for cross-border systems).
The model schedules and dispatches the electricity supply from generators
to meet hourly electricity demand in substations at a minimum cost.
It considers the techno-economic constraints of both generating units
and high-voltage transmission network.
The electricity transmission is represented as a direct current (DC) network
(with N-1 criterion),
which provides a reasonable balance between modeling accuracy and data and computational requirements.
PowNet supports modeling the integration of variable renewable resources
(e.g., hydro, wind, solar) into the UC/ED process.
For example, it can be linked with models that estimate the electricity supply
available from renewable resources as a function of the climatic conditions.
In addition, PowNet has provision to account for the effect of droughts
on the generation of dispatchable thermal units (e.g., coal, oil, gas-fired units)
that depend on freshwater availability.
These features facilitate the application of PowNet to problems in
the water-energy nexus domain that investigate the impact of
water availability on electricity supply and demand.
