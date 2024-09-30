
**3. Software Architecture**
============================

-----------------------
PowNet Folder Structure
-----------------------

The folder/files structure of PowNet is summarized as follows:

.. code-block:: text

  pownet/
  ├── data_utils.py
  ├── folder_utils.py
  ├── core/
  │   ├── builder.py
  │   ├── data_processor.py
  │   ├── input.py
  │   ├── output.py
  │   ├── record.py
  │   ├── simulation.py
  │   └── visualizer.py
  └── modeling/
      ├── constraint.py
      ├── model.py
      ├── objfunc.py
      └── variable.py


------------------
Required PowNet Input Files
------------------

A user must provide the following CSV files in the correct format. The following CSV files are
optional and do not need to be provided: hydropower, solar, wind, and import.

PowNet auto-generates other needed files inside the input folder. These files will have
"pownet_" as the prefix.

+-----------------------------+---------------------------------------------------------------+
| File                        | Description                                                   |
+=============================+===============================================================+
| transmission.csv            | Techno-economic parameters of the transmission                | 	       
|                             | system. The user will need to specify columns                 | 
|                             | without the “pownet” prefix. Once a user has                  | 
|                             | specified the necessary columns, they need to                 |
|                             | run the transform_transmission_inputs function                | 
|                             | from input_processor.py to generate columns                   | 
|                             | with the “pownet” prefix.                                     |
|                             |                                                               |
+-----------------------------+---------------------------------------------------------------+
| thermal_unit.csv            | Techno-economic parameters of thermal generators              |
|                             |                                                               |
+-----------------------------+---------------------------------------------------------------+
| unit_marginal_cost.csv      | Timeseries of fuel cost by renewables and import.             |
|                             |                                                               |
+-----------------------------+---------------------------------------------------------------+
| demand_export.csv           | Timeseries of electricity demand at each node.                |
|                             |                                                               |
+-----------------------------+---------------------------------------------------------------+
| hydropower.csv              | Timeseries of hydropower availability by node.                |
|                             |                                                               |
+-----------------------------+---------------------------------------------------------------+
| solar.csv                   | Timeseries of solar availability by node.                     |
|                             |                                                               |
+-----------------------------+---------------------------------------------------------------+
| wind.csv                    | Timeseries of wind availability by node.                      |
|                             |                                                               |
+-----------------------------+---------------------------------------------------------------+
| import.csv                  | Timeseries of import availability by node.                    |
|                             |                                                               |
+-----------------------------+---------------------------------------------------------------+


--------------------
PowNet Output Files
--------------------

+---------------------------------------------------------------+---------------------------------------------+
| File                                                          | Description                                 |
+===============================================================+=============================================+
| YYYYMMDD_hhmm_country_simhorizon_flow_variables.csv           | Flow of electricity in the transmission     |
|                                                               | lines. Indexed with (source, sink, time)    |
|                                                               |                                             |
+---------------------------------------------------------------+---------------------------------------------+
| YYYYMMDD_hhmm_country_simhorizon_node_variables.csv           | hourly power values of different            |
|                                                               | power plants based on nodes type (vartype). |
|                                                               | Indexed with (node, time)                   |
|                                                               |                                             |
+---------------------------------------------------------------+---------------------------------------------+
| YYYYMMDD_hhmm_country_simhorizon_system_variables.csv         | System level variables, i.e. spinning       |
|                                                               | reserve. Indexed with (time).               |
|                                                               |                                             |
+---------------------------------------------------------------+---------------------------------------------+
| YYYYMMDD_hhmm_country_fuelmix.png                             | Output figure showing the generation mix.   |
|                                                               |                                             |
+---------------------------------------------------------------+---------------------------------------------+
| YYYYMMDD_hhmm_unit_plots/YYYYMMDD_hhmm_country_XXXXX.png      | Output figure showing the dispatch for      |
|                                                               | each thermal unit and the unit’s on/off     |
|                                                               | status.                                     |
|                                                               |                                             |
+---------------------------------------------------------------+---------------------------------------------+

