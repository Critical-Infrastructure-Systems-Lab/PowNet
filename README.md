[![DOI](https://zenodo.org/badge/211224999.svg)](https://zenodo.org/badge/latestdoi/211224999)
# PowNet: Power system analysis model in Python
PowNet is a least-cost optimization model for simulating the Unit Commitment and Economic Dispatch (UC/ED) of large-scale (regional to country) power systems. In PowNet, a power system is represented by a set of nodes that include power plants, high-voltage substations, and import/export stations (for cross-border systems). The model schedules and dispatches the electricity supply from power plant units to meet hourly electricity demand in substations (at a minimum cost). It considers the techno-economic constraints of both generating units and high-voltage transmission network. The power flow calculation is based on a Direct Current (DC) network (with N-1 criterion), which provides a reasonable balance between modelling accuracy and data and computational requirements. PowNet can easily integrate information about variable renewable resources (e.g., hydro, wind, solar) into the UC/ED process. For example, it can be linked with models that estimate the electricity supply available from renewable resources as a function of the climatic conditions. In addition, PowNet has provision to account for the effect of droughts on the generation of dispatchable thermal units (e.g., coal, oil, gas fired units) that depend on freshwater availability. These features facilitate the application of PowNet to problems in the water-energy nexus domain that investigate the impact of water availability on electricity supply and demand. More details about the functionalities of PowNet are provided in Chowdhury et al. (2019).

This repository provides PowNet version 1.1, whose functionalities are demonstrated on the Cambodian power system. Computational requirements and instructions on how to run and customize the model are presented below.

# Requirements
PowNet is written in Python 3.5. It requires the following Python packages: (i) Pyomo, (ii) NumPy, (iii) Pandas, and (iv) Matplotlib (optional for plotting). It also requires Jupyter Notebook and an optimization solver (e.g., Gurobi, CPLEX). Note that the Python packages and Jupyter Notebook are freely available, while academic users can obtain a free license of Gurobi or CPLEX. PowNet has been tested on both Windows 10 and Linux Ubuntu 16.04 operating systems.

# How to run
PowNet is implemented in three Python scripts, namely PowNetModel.py, PowNetDataSetup.py, and PowNetSolver.ipynb. PowNetModel.py contains the main model structure, which is based on the Pyomo optimization package. The data concerning dispatchable units and transmission lines, hourly electricity demand at substations, and hourly electricity availability through variable renewable resources (hydropower in this specific example) are provided in separate .csv files. PowNet can be run as follows:

1.	Run the PowNetDataSetup.py. The script reads the .csv data files and generates a .dat file (sample provided), in which all data are written in a format that is executable by Pyomo;
2.	Run the PowNetSolver.ipynb that executes the model with the prepared data. The script also generates .csv files containing the value of each decision variable, namely (i) operational status of generating units, (ii) electricity supplied by the generators and variable renewable resources, (iii) voltage angles at each node (required to estimate transmission through the lines), and (iv) spinning and non-spinning reserves.

The repository also includes sample output files. A few additional notebooks are provided to help users perform some standard analyses on the output variables. Such analyses include estimation of (i) generation mix, (ii) operating costs, (iii) CO2 emissions, (iv) usage and N-1 violations of transmission lines, and (v) reserves.

# How to customize
The implementation of PowNet for any other power system requires the customization of the three Python scripts. PowNetDataSetup.py, PowNetModel.py, and PowNetSolver.ipynb are labelled with Segments A.1-A.9, B.1-B.13, and C.1-C.5, respectively, to facilitate the following step-by-step operations:

1.	Prepare the system-specific data in .csv files;
2.	Provide information regarding the simulation, such as simulation period, planning horizon, transmission losses (expressed as a percentage), N-1 criterion, reserve margins etc. in Segment A.1;
3.	Declare the lists of nodes and types of dispatchable units in Segment A.3;
4.	Declare the set of dispatchable generators by nodes and types in Segment A.4 and B.1. Also, in Segment B.1, declare the types of generators that must ensure the minimum reserve;
5.	Add type-specific cost functions in the objective function in Segment B.8; 
6.	Customize B.11.3 according to the number of nodes with dispatchable generating units;
7.	To include or exclude any variable renewable resource (e.g., hydro, wind, solar), uncomment or comment the code provided in Segment A.5, A.9, B.2, B.6, B.7, B.10, B.11.2, and C.5.

# License
PowNet is released under the MIT license. Please read it carefully before employing the model.

# Acknowledgment
PowNet development is supported by Singapore's Ministry of Education (MoE) through the Tier 2 project “Linking water availability to hydropower supply – an engineering systems approach” (Award No. MOE2017-T2-1-143).


