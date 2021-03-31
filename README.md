[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.4020167.svg)](https://doi.org/10.5281/zenodo.4020167) ![license MIT](https://img.shields.io/github/license/kamal0013/PowNet) 
# PowNet: Unit Commitment / Economic Dispatch model in Python
PowNet is a least-cost optimization model for simulating the Unit Commitment and Economic Dispatch (UC/ED) of large-scale (regional to country) power systems. In PowNet, a power system is represented by a set of nodes that include power plants, high-voltage substations, and import/export stations (for cross-border systems). The model schedules and dispatches the electricity supply from power plant units to meet hourly electricity demand in substations (at a minimum cost). It considers the techno-economic constraints of both generating units and high-voltage transmission network. The power flow calculation is based on a Direct Current (DC) network (with N-1 criterion), which provides a reasonable balance between modelling accuracy and data and computational requirements. PowNet can easily integrate information about variable renewable resources (e.g., hydro, wind, solar) into the UC/ED process. For example, it can be linked with models that estimate the electricity supply available from renewable resources as a function of the climatic conditions. In addition, PowNet has provision to account for the effect of droughts on the generation of dispatchable thermal units (e.g., coal, oil, gas fired units) that depend on freshwater availability. These features facilitate the application of PowNet to problems in the water-energy nexus domain that investigate the impact of water availability on electricity supply and demand. More details about the functionalities of PowNet are provided in [Chowdhury et al. (2020a)](https://openresearchsoftware.metajnl.com/articles/10.5334/jors.302/).

# Versions and implementations
The latest and previous versions of PowNet are listed below. Please, check the [release notes](https://github.com/kamal0013/PowNet/releases) for a list of modifications made in each version. 
### Current version
PowNet v1.2 ([GitHub](https://github.com/kamal0013/PowNet/tree/v1.2) | [Zenodo](https://zenodo.org/record/4020167#.X1hqrGhKguU))
### Previous version(s)
PowNet v1.1 ([GitHub](https://github.com/kamal0013/PowNet/tree/v1.1) | [Zenodo](https://zenodo.org/record/3756750))

### Implementations
1.	[PowNet-Cambodia](https://github.com/kamal0013/PowNet) – implementation of PowNet for Cambodian power system with data for 2016

2.	[PowNet-Laos](https://github.com/kamal0013/PowNet-Laos) – implementation of PowNet for Laotian power system with data for 2016

3.	[PowNet-Thailand]( https://github.com/kamal0013/PowNet-Thailand) – implementation of PowNet for Thai power system with data for 2016

Computational requirements and instructions on how to run and customize the model are presented below.

# Requirements
PowNet is written in Python 3.5. It requires the following Python packages: (i) Pyomo, (ii) NumPy, (iii) Pandas, and (iv) Matplotlib (optional for plotting). It also requires an optimization solver (e.g., Gurobi, CPLEX). Note that the Python packages are freely available, while academic users can obtain a free license of Gurobi or CPLEX. PowNet has been tested on both Windows 10 and Linux Ubuntu 16.04 operating systems.

# How to run
PowNet is implemented in three Python scripts, namely pownet_model.py, pownet_datasetup.py, and pownet_solver.py. pownet_model.py contains the main model structure, which is based on the Pyomo optimization package. The data concerning dispatchable units and transmission lines, hourly electricity demand at substations, and hourly electricity availability through variable renewable resources (hydropower in this specific example) are provided in separate .csv files. PowNet can be run as follows:

1.	Run the pownet_datasetup.py. The script reads the .csv data files and generates a .dat file (sample provided), in which all data are written in a format that is executable by Pyomo;
2.	Run the pownet_solver.py that executes the model with the prepared data. The script also generates .csv files containing the values of each decision variable, namely (i) operational status of generating units, (ii) electricity supplied by the generators and variable renewable resources, (iii) voltage angles at each node (required to estimate transmission through the lines), and (iv) spinning and non-spinning reserves.

The repository also includes sample output files. A few additional Jupyter notebooks are provided to help users perform some standard analyses on the output variables. Such analyses include estimation of (i) generation mix, (ii) operating costs, (iii) CO2 emissions, (iv) usage and N-1 violations of transmission lines, and (v) reserves. Note that full forms of the abbreviated node-names are provided in Appendix. The Appendix also includes an Excel file with sample estimation of transmission parameters (capacity and susceptance) from physical specifications of the lines (e.g., voltage level, length, size, number of circuits, capacity per circuit etc.).

# How to customize
The implementation of PowNet for any other power system requires the customization of the three Python scripts. pownet_datasetup.py, pownet_model.py, and pownet_solver.py are labelled with Segments A.1-A.9, B.1-B.13, and C.1-C.5, respectively, to facilitate the following step-by-step operations:

1.	Prepare the system-specific data in .csv files;
2.	Provide information regarding the simulation, such as simulation period, planning horizon, transmission losses (expressed as a percentage), N-1 criterion, reserve margins etc. in Segment A.1;
3.	Declare the lists of nodes and types of dispatchable units in Segment A.3;
4.	Declare the set of dispatchable generators by nodes and types in Segment A.4 and B.1. Also, in Segment B.1, declare the types of generators that must ensure the minimum reserve;
5.	Add type-specific cost functions in the objective function in Segment B.8; 
6.	Customize B.11.3 according to the number of nodes with dispatchable generating units;
7.	To include or exclude any variable renewable resource (e.g., hydro, wind, solar), uncomment or comment the code provided in Segment A.2, A.5, A.9, B.2, B.6, B.7, B.10, B.11.2, and C.5.

# Schematics
A basic framework of PowNet is shown in the figure below (adapted from [Chowdhury et al., 2020c](https://www.essoar.org/doi/abs/10.1002/essoar.10504393.1)).

![]( https://github.com/kamal0013/PowNet/blob/master/Appendix/fig_pownet_model.PNG)

Figure below (adapted from [Chowdhury et al., 2020a](https://openresearchsoftware.metajnl.com/articles/10.5334/jors.302/)) shows the main generation and transmission components of the Cambodian power system (as of 2016), used to describe PowNet in this repository. The data are mostly extracted from publicly available technical reports, published by Electricite Du Cambodge (EDC).

![]( https://github.com/kamal0013/PowNet/blob/master/Appendix/fig_Cambodia_grid.jpg)

# Citation
If you use PowNet for your research, please cite the following paper:

Chowdhury, A.F.M.K., Kern, J., Dang, T.D. and Galelli, S., 2020. PowNet: A Network-Constrained Unit Commitment/Economic Dispatch Model for Large-Scale Power Systems Analysis. Journal of Open Research Software, 8(1), p.5. DOI: http://doi.org/10.5334/jors.302.

In addition, each release of PowNet is archived on Zenodo with a DOI, that can be found [here](https://zenodo.org/record/4020167#.X1hsSWhKguU).

# License
PowNet is released under the MIT license. 

# Contact
For questions and feedback related to PowNet, please send an email to afm.chowdhury@uon.edu.au (AFM Kamal Chowdhury) or stefano_galelli@sutd.edu.sg (Stefano Galelli).

# Acknowledgment
PowNet development is supported by Singapore's Ministry of Education (MoE) through the Tier 2 project “Linking water availability to hydropower supply – an engineering systems approach” (Award No. MOE2017-T2-1-143).

# Publications
Following is a list of papers that used PowNet:
1.	Chowdhury, A.K., Dang, T.D., Nguyen, H.T., Koh, R., and Galelli, S., (2020c). The Greater Mekong's climate-water-energy nexus: how ENSO-triggered regional droughts affect power supply and CO2 emissions. Submitted to Earth’s Future, DOI: https://doi.org/10.1002/essoar.10504393.1.
2.	Chowdhury, A.K., Dang, T.D., Bagchi, A., and Galelli, S., (2020b). Expected benefits of Laos' hydropower development curbed by hydro-climatic variability and limited transmission capacity—opportunities to reform. Journal of Water Resources Planning and Management, DOI: https://doi.org/10.1061/(ASCE)WR.1943-5452.0001279, [(RG-link)](https://www.researchgate.net/publication/341276238_Expected_benefits_of_Laos'_hydropower_development_curbed_by_hydro-climatic_variability_and_limited_transmission_capacity--opportunities_to_reform).
3.	Chowdhury, A.K., Kern, J., Dang, T.D. and Galelli, S., (2020a). PowNet: A Network-Constrained Unit Commitment/Economic Dispatch Model for Large-Scale Power Systems Analysis. Journal of Open Research Software, 8(1), p.5. DOI: http://doi.org/10.5334/jors.302, [(RG-link)]( https://www.researchgate.net/publication/339885402_PowNet_A_Network-Constrained_Unit_CommitmentEconomic_Dispatch_Model_for_Large-Scale_Power_Systems_Analysis).
