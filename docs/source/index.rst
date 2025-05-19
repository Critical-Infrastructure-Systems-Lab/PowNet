Welcome to PowNet's documentation!
===================================

PowNet is an open-source Python framework simulating the least-cost operational scheduling of large-scale power systems as
a Production Cost Model (PCM). At its heart, it solves the Unit Commitment (UC) and Economic Dispatch (ED) problems using
Mixed-Integer Linear Programming to determine optimal generator schedules that meet hourly demand while respecting operational
and network constraints. Designed for accessibility with simple CSV inputs and support for both Gurobi and the open-source HiGHS solvers,
PowNet includes advanced features like reservoir simulation for hydropower and stochastic time series generation.
Its modular design facilitates straightforward analysis for basic users while offering flexibility for advanced research,
custom constraints, and model extensions.

The software is actively maintained by researchers at the Critical Infrastructure Systems Lab,
School of Civil and Environmental Engineering, Cornell University.


.. For each section, we list the subsections instead of the table of contents to avoid cluttering the sidebar.

**Getting started**

* :doc:`getting_started/introduction`
* :doc:`getting_started/installation`
* :doc:`examples/quickstart`
* :doc:`user_guide/input_files`

.. toctree::
   :hidden:
   :caption: Getting started
   :maxdepth: 1

   getting_started/introduction
   getting_started/installation
   examples/quickstart
   user_guide/input_files


**Examples**

* :doc:`examples/custom_workflow`
* :doc:`examples/synthetic_load`
* :doc:`examples/synthetic_solar`
* :doc:`examples/reservoir_simulation`
* :doc:`examples/reservoir_reoperation`

.. toctree::
   :hidden:
   :caption: Examples
   :maxdepth: 1

   examples/custom_workflow
   examples/synthetic_load
   examples/synthetic_solar
   examples/reservoir_simulation
   examples/reservoir_reoperation


**Technical explanations**

* :doc:`technical/math_formulation`
* :doc:`technical/dispatchable`
* :doc:`technical/linear_power_flow`
* :doc:`technical/time_series_models`
* :doc:`technical/reservoir_model`

.. toctree::
   :hidden:
   :caption: Technical explanations

   technical/math_formulation
   technical/dispatchable
   technical/linear_power_flow
   technical/time_series_models
   technical/reservoir_model


**References**

* :doc:`reference/contributing`
* :doc:`reference/cite_pownet`
* :doc:`reference/publications`
* :doc:`reference/developers`
* :doc:`reference/glossary`
* :doc:`api_ref/pownet`

.. toctree::
   :hidden:
   :caption: References
   :maxdepth: 0

   reference/contributing
   reference/cite_pownet
   reference/publications
   reference/developers
   reference/glossary
   api_ref/pownet
