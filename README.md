![license MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
[![CI Tests](https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/actions/workflows/python-app.yml/badge.svg)](https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/actions)
[![GitHub Release](https://img.shields.io/github/v/release/Critical-Infrastructure-Systems-Lab/PowNet)](https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/releases/tag/v2.0)
[![Read the Docs](https://img.shields.io/readthedocs/pownet)](https://pownet.readthedocs.io/en/latest/)

# PowNet: Unit Commitment / Economic Dispatch model in Python
PowNet is a least-cost optimization model for simulating the Unit Commitment and Economic Dispatch (UC/ED) of large-scale (regional to country) power systems. In PowNet, a power system is represented by a set of nodes that include power plants, high-voltage substations, and import/export stations (for cross-border systems). The model schedules and dispatches the electricity supply from power plant units to meet hourly electricity demand in substations at a minimum cost. It considers the techno-economic constraints of both generating units and high-voltage transmission network. The power flow calculation is based on a Direct Current (DC) network (with N-1 criterion), which provides a reasonable balance between modelling accuracy and data and computational requirements. PowNet can easily integrate information about variable renewable resources (e.g., hydro, wind, solar) into the UC/ED process. For example, it can be linked with models that estimate the electricity supply available from renewable resources as a function of the climatic conditions. In addition, PowNet has provision to account for the effect of droughts on the generation of dispatchable thermal units (e.g., coal, oil, gas-fired units) that depend on freshwater availability. These features facilitate the application of PowNet to problems in the water-energy nexus domain that investigate the impact of water availability on electricity supply and demand. 

Read the PowNet Documentation here: https://pownet.readthedocs.io/en/latest


## Installing and using PowNet
To use PowNet, a user needs to supply it with CSV files. For guidance on creating these CSV files, please see examples provided [here](https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/tree/master/model_library). Please ensure that column names matches with those from the examples.

As for installing PowNet, there are multiple options depending on whether we want to modify the source code. However, the following step is highly recommended for any user: creating a virtual environment to manage dependencies. If using Conda, we can create an envrionment with the following command

```
conda create --name your_env_name_here
conda activate your_env_name_here
```

If deciding on a name for the environment takes too long, please feel free to name the environment as "pownet".

### Option 1: Regular user
A regular user is someone who has created their input files and wish to just run PowNet. In this case, it is best to simply install PowNet as a package from PyPI. We can achieve this with the following command:

```
pip install pownet
```

Once the package has been installed, we can now go to our working directory. In this example, we assume the following folder structure:

```
working_directory/
├── scripts/
│   └── [run_quickstart.py](https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/blob/master/scripts/run_quickstart.py)
├── model_library/
│   └── dummy/
│       ├── demand_export.csv
│       ├── thermal_unit.csv
│       ├── nondispatch_unit.csv
│       ├── hydropower.csv
│       ├── import.csv
│       ├── contract_cost.csv
│       └── transmission.csv
└── outputs/
```

A Python script called "[run_quickstart.py](https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/blob/master/scripts/run_quickstart.py)" provides an example on running a simulation, saving the simulation outputs, and visualizing the outputs.

### Option 2: Power user (no pun intended)
In case we wish to modify the source code, PowNet should be installed as an editable package. First, download or clone the PowNet repository to your local machine. For example: if we want to clone to "C://user/pownet",

```
git clone https://github.com/your-username/pownet.git C://user/pownet
```

Next, open a terminal and navigate to the directory where we cloned the repository:

```
cd C://user/pownet
```

Now, we can install this PowNet package using pip, which is a manager for Python packages:

```
pip install -e .
```

This command installs the package in "editable" mode (-e) using pyproject.toml that is located in the root directory of PowNet. The editable mode allows us to edit PowNet codebase when we need to modify or implement new features. The pyproject.toml file specifies the dependencies required to run PowNet.

A quick start tutorial to run a simple case study is provided here: https://pownet.readthedocs.io/en/latest/pages/quickstarter.html

## Overview of PowNet

![overview_pownet](./docs/overview_pownet.png)


