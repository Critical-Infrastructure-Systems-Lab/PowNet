
.. autosummary::
    :toctree: _source/
    
################################
Preparing PowNet inputs
################################

To run a `PowNet` simulation, you need to provide a set of CSV files that describe your power system. These files should be placed together within a dedicated folder. Based on the files you provide, `PowNet`'s ``DataProcessor`` class may auto-generate additional processed files within the same folder. These generated files typically have the ``pownet_`` prefix and are used directly by the simulation engine.

**IMPORTANT** Ensure that for files describing techno-economic parameters (like ``thermal_unit.csv``, ``transmission.csv``, etc.), the column names match the expected format exactly as detailed below. It is recommended that a user uses the provided examples as file templates.

Required User Inputs
======================

These files *must* be provided by the user:

* ``demand_export.csv``:
    * **Description**: An hourly timeseries of electricity demand (in MW) for each load node in the system.
    * **Format**: Each column represents a node, and each row represents an hour of the year (8760 rows expected for a standard year). Date/time columns (like year, month, day, hour) can be included for reference but are ignored by `PowNet`.
    * **Note**: When your system has only a single node, or all power stations are aggrgated to a node, then this file should contain only a single column being the demand of that node. Otherwise, nodes are defined in ``transmission.csv`` as described later in this section.

* ``contract_cost.csv``:
    * **Description**: Specifies the hourly costs (e.g., USD/MWh or USD/MW) associated with different supply or fuel contracts. These contracts are linked to specific generator units via ``thermal_unit.csv`` and ``nondispatch_unit.csv``.
    * **Format**: Each column represents a contract name (which must match names used in other files), and each row represents an hour.

Optional User Inputs
======================

These files describe different components of the power system. While optional, you typically need to provide files relevant to the system components you want to model (e.g., provide ``thermal_unit.csv`` if you have thermal generators).

* ``thermal_unit.csv``:
    * **Description**: Defines the techno-economic parameters for thermal generators.
    * **Columns**:
        * ``name``: Unique identifier for the thermal unit.
        * ``node``: Network node where the unit connects.
        * ``unit_type``: User-defined type (e.g., CCGT, OCGT). This is for processing modeling outputs.
        * ``fuel_type``: Type of fuel (e.g., 'coal', 'gas', 'oil').
        * ``fuel_contract``: Name of the contract defined in ``contract_cost.csv``.
        * ``max_capacity``: Maximum power output (MW).
        * ``min_capacity``: Minimum stable power output (MW).
        * ``heat_rate``: Heat rate (e.g., MMBtu/MWh or GJ/MWh).
        * ``operation_cost``: Variable O&M cost (e.g., USD/MWh).
        * ``fixed_cost``: Fixed O&M cost (e.g., USD/MW/hr).
        * ``startup_cost``: Cost per startup event (e.g., USD/startup).
        * ``ramp_rate``: Maximum ramp up/down rate (MW/hr).
        * ``min_uptime``: Minimum hours unit must stay online after starting (hr).
        * ``min_downtime``: Minimum hours unit must stay offline after shutting down (hr).
        * ``latitude`` (optional): Latitude coordinate.
        * ``longitude`` (optional): Longitude coordinate.
        * ``must_take`` (0 or 1): 1 if the unit has a take-or-pay contract.

* ``nondispatch_unit.csv``:
    * **Description**: Defines parameters for non-dispatchable units (hydro, solar, wind, imports). Often used to link these units to cost contracts.
    * **Columns**:
        * ``name``: Unit name (must match name in the corresponding timeseries file, e.g., ``solar.csv``).
        * ``contracted_capacity``: Contracted capacity limit (MW). Use -1 for no explicit contractual limit, so the unit is limited by ints installed capacity.
        * ``contract``: Name of the contract defined in ``contract_cost.csv``.
        * ``must_take`` (0 or 1): 1 if generation must be taken if available (subject to capacity).

* ``energy_storage.csv``:
    * **Description**: Defines parameters for energy storage systems.
    * **Columns**:
        * ``name``: Unique identifier for the storage unit.
        * ``attach_to``: Name of the solar or wind unit or network node the storage is associated with.
        * ``inject_to``: Network node where discharged energy is injected.
        * ``max_charge``: Maximum charging rate (MW).
        * ``max_discharge``: Maximum discharging rate (MW).
        * ``max_capacity``: Maximum energy storage capacity (MWh).
        * ``min_capacity``: Minimum energy storage level (MWh).
        * ``charge_efficiency``: Charging efficiency factor (0 to 1).
        * ``discharge_efficiency``: Discharging efficiency factor (0 to 1).
        * ``self_discharge_rate``: Hourly self-discharge rate (0 to 1).
        * ``cost_contract``: Name of the contract (from ``contract_cost.csv``) associated with charging/discharging costs.

* ``transmission.csv``:
    * **Description**: Defines a system's nodes and their properties. `PowNet` can calculate line parameters if needed, but user-provided values take precedence.
    * **Required Columns**:
        * ``source``: Starting node of the line.
        * ``sink``: Ending node of the line.
        * ``source_kv``: Voltage level at the source (kV).
        * ``sink_kv``: Voltage level at the sink (kV).
        * ``distance``: Length of the line (km).
        * ``n_circuits``: Number of parallel circuits.
    * **Optional Columns**:
        * ``user_line_cap``: User-defined line capacity (MW). Use -1 or omit to let `PowNet` calculate.
        * ``user_susceptance``: User-defined line susceptance (Siemens). Use -1 or omit to let `PowNet` calculate.
        * ``source_lon``, ``source_lat``: Coordinates for the source node (needed for map plotting).
        * ``sink_lon``, ``sink_lat``: Coordinates for the sink node (needed for map plotting).

* ``hydropower.csv`` / ``hydropower_daily.csv``:
    * **Description**: Hourly (``hydropower.csv``) or daily (``hydropower_daily.csv``) timeseries of maximum available hydropower generation (e.g., in MW) for each hydro unit. `Do not provide` both for the same unit.
    * **Format**: Uses a two-level column header. Level 1: Unit name. Level 2: Node name where the unit connects. Rows correspond to hours or days.

* ``solar.csv``:
    * **Description**: Hourly timeseries of maximum available solar power generation (e.g., in MW) for each solar unit.
    * **Format**: Two-level column header (Level 1: Unit name, Level 2: Node name). Rows correspond to hours.

* ``wind.csv``:
    * **Description**: Hourly timeseries of maximum available wind power generation (e.g., in MW) for each wind unit.
    * **Format**: Two-level column header (Level 1: Unit name, Level 2: Node name). Rows correspond to hours.

* ``import.csv``:
    * **Description**: Hourly timeseries of maximum available power import (e.g., in MW) for each import source/node.
    * **Format**: Two-level column header (Level 1: Source/Unit name, Level 2: Node name). Rows correspond to hours.

Auto-Generated Inputs (by `PowNet`'s DataProcessor)
=======================================================

These files are automatically generated by `PowNet`'s ``DataProcessor`` based on the user inputs. You do not need to create them manually, but they will appear in your input folder.

* ``pownet_transmission.csv``:
    * Contains processed transmission line data used directly by the model, including calculated or user-provided ``line_capacity`` and ``susceptance``.

* ``pownet_cycle_map.json``:
    * Defines basic cycles in the transmission network, used for the Kirchhoff power flow formulation.

* ``pownet_thermal_derated_capacity.csv``:
    * Hourly maximum power output for each thermal unit, potentially considering derating factors.

* ``pownet_ess_derated_capacity.csv``:
    * Hourly maximum storage capacity (MWh) for energy storage systems, potentially considering derating.
