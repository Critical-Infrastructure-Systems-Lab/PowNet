![license MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
[![CI Tests](https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/actions/workflows/python-app.yml/badge.svg)](https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/actions)
[![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/phumthep/23c151ad08ede7f698ce7cfbc2c09a0a/raw/covbadge.json)](https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/actions)
[![GitHub Release](https://img.shields.io/github/v/release/Critical-Infrastructure-Systems-Lab/PowNet)](https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/releases/tag/v2.0)
[![Read the Docs](https://img.shields.io/readthedocs/pownet)](https://pownet.readthedocs.io/en/latest/)
[![status](https://joss.theoj.org/papers/f7509a62fde550bec7ae3d1da0181b7d/status.svg)](https://joss.theoj.org/papers/f7509a62fde550bec7ae3d1da0181b7d)

# PowNet: A Production Cost Modeling Framework for Large-scale Power Systems
PowNet is an open-source production cost model (PCM) framework written in Python, designed to simulate the operational scheduling of large-scale (regional or national) power systems. It determines the least-cost schedule for power generation by solving the unit commitment (UC) and economic dispatch (ED) problems – a process commonly used for applications like day-ahead market simulation. Designed for users focused on power system analysis rather than complex model development, PowNet uses simple spreadsheet files for data inputs, significantly simplifying model setup and modification. As for advanced users, the framework's modular design provides modeling flexibility to implement customized analysis or explore complex modeling algorithms.

## Key functionalities
- Models power systems including generator techno-economic constraints and network limits
- Uses computationally efficient linearized DC power flow for network analysis
- Supports variable renewable energy (VRE) sources, such as hydro, wind, and solar
- Built for computational speed using the high-performance Gurobipy modeling framework with support for the open-source HiGHS solver
- Includes features allowing the analysis of water-energy nexus impacts (e.g., drought effects on thermal units)

PowNet enables analysts to readily study grid operations, VRE integration, and water-energy interactions in a low-code environment. For advanced users, it retains the flexibility needed to explore complex model configurations and research modeling algorithms.

Read the Documentation for more information at https://pownet.readthedocs.io/en/latest.

## Using PowNet
To use PowNet, a user needs to supply it with CSV files. For guidance on creating these CSV files, please see examples provided [here](https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/tree/master/model_library). Please ensure that column names matches with those from the examples. Details on preparing some input files can be found [here](https://critical-infrastructure-systems-lab.github.io/manual/docs/CIS-Lab-software).

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
│   └── run_quickstart.py
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

A tutorial "[quickstart.py](./examples/quickstart.ipynb)" provides an example on running a simulation, saving the simulation outputs, and visualizing the outputs.

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


## Overview of PowNet

![overview_pownet](./joss_submission/overview_pownet.png)


# Citing this software
If you use PowNet 2.0 in your work, please cite the following [JOSS article](https://joss.theoj.org/papers/10.21105/joss.08035):

```
@article{
  Bunnak2025,
  title = {PowNet 2.0: A production cost modeling framework for large-scale power systems},
  author = {Bunnak, Phumthep and Eldardiry, Hisham and Pavičević, Matija and Feng, Jerry Zhuoer and Galelli, Stefano},
  year = {2025},
  publisher = {The Open Journal},
  volume = {10},
  number = {111},
  pages = {8035},
  journal = {Journal of Open Source Software}
  doi = {10.21105/joss.08035},
  url = {https://doi.org/10.21105/joss.08035},
}
```
