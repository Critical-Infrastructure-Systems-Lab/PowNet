
**4. PowNet 2.0 Quick Start Guide**
============================
This tutorial demonstrates how to use PowNet 2.0 to simulate a dummy power system over a 24-hour horizon for two simulation days.

1. Installation
-----------------
Download or clone the PowNet 2.0 repository to your local machine. For example: if we want to clone to "C://user/pownet",

.. code-block:: python

    git clone https://github.com/your-username/pownet.git C://user/pownet

Next, open a terminal and navigate to the directory where you cloned the repository:

.. code-block:: python

    cd C://user/pownet

The following step is highly recommended: creating a virtual environment to manage dependencies. If using Conda, you can create an envrionment named "pownet":

.. code-block:: python

    conda create --name pownet
    conda activate pownet

Now, you can install this PowNet package using pip, which is a manager for Python packages:

.. code-block:: python

    pip install -e .

This command installs the package in "editable" mode (-e) using pyproject.toml that is located in the root directory of PowNet. The editable mode allows you to edit PowNet codebase when you need to modify or implement new features. The pyproject.toml file specifies the dependencies required to run PowNet.

Now you have PowNet 2.0 installed and ready to use! You can proceed with the rest of this tutorial to run your first simulation using a small case study.

2. Model Overview
-----------------

The dummy power system includes a variety of generation sources and a single buyer.  

::

        pOil
          |
          |
    Node 3 --- pGas
          |
          |
    Node 1 --- Node 2 --- pHydro --- Buyer
          |               |
          |               |
    Supplier         pBiomass 


3.  Setup
----------

* **Input Folder:** Define the directory containing the power system models (`input_folder`). This folder may contain multiple subdirectories.  Ensure the `input_folder` contains a subdirectory named `model_name` with the necessary model data, which is a set of CSV files.

* **Model Year:** Specify the simulation year (`model_year`). This value must match the year associated with the time series data files within the `input_folder/model_name` directory.

* **Simulation Parameters:**
    *  `sim_horizon`:  Define the simulation horizon in hours (e.g., 24 for a daily simulation).
    *  `steps_to_run`: Specify the number of simulation steps (e.g., 2 for a two-day simulation).
    *  `solver`: Select the optimization solver ('gurobi' or 'highs').

4. Code Example
---------------

The following code has already been made available in the the `scripts` folder as `run_quickstart.py`. However, the code is also presented here.

.. code-block:: python

    """ This script provides an example of how to run PowNet 2.0.
    """

    import os
    from pownet.core import Simulator


    def main():

        # --------- User inputs

        input_folder = "..//model_library"
        output_folder = "..//temptemp"

        model_name = "dummy"
        model_year = 2016

        # Simulation parameters
        sim_horizon = 24
        steps_to_run = 2
        solver = "gurobi"  # or highs

        # --------- End of user inputs

        # Run the simulation
        simulator = Simulator(
            input_folder=input_folder,
            model_name=model_name,
            model_year=model_year,
        )

        simulator.run(
            sim_horizon=sim_horizon,
            steps_to_run=steps_to_run,
            solver=solver,
        )

        # Write the simulation results
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
        simulator.write_results(output_folder)

        # Plot the results
        simulator.plot_fuelmix("bar", output_folder)
        simulator.plot_unit_status(output_folder)


    if __name__ == "__main__":
        main()


5. Running the Simulation
-------------------------

1.  **Save:** Save the code above as a Python file (e.g., `run_tutorial.py`).
2.  **Run:** Execute the script from your terminal using `python run_pownet.py`.

6. Outputs
----------

* **Results:** Simulation results will be saved in the specified `output_folder`.
* **Plots:**  The code generates plots of the fuel mix and unit status, also saved in the `output_folder`.
