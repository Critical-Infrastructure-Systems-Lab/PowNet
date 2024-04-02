![license MIT](https://img.shields.io/github/license/kamal0013/PowNet) 
# PowNet: Unit Commitment / Economic Dispatch model in Python
PowNet is a least-cost optimization model for simulating the Unit Commitment and Economic Dispatch (UC/ED) of large-scale (regional to country) power systems. In PowNet, a power system is represented by a set of nodes that include power plants, high-voltage substations, and import/export stations (for cross-border systems). The model schedules and dispatches the electricity supply from power plant units to meet hourly electricity demand in substations at a minimum cost. It considers the techno-economic constraints of both generating units and high-voltage transmission network. The power flow calculation is based on a Direct Current (DC) network (with N-1 criterion), which provides a reasonable balance between modelling accuracy and data and computational requirements. PowNet can easily integrate information about variable renewable resources (e.g., hydro, wind, solar) into the UC/ED process. For example, it can be linked with models that estimate the electricity supply available from renewable resources as a function of the climatic conditions. In addition, PowNet has provision to account for the effect of droughts on the generation of dispatchable thermal units (e.g., coal, oil, gas-fired units) that depend on freshwater availability. These features facilitate the application of PowNet to problems in the water-energy nexus domain that investigate the impact of water availability on electricity supply and demand. 

# Versions 
The latest and previous versions of PowNet are listed below. Please, check the [release notes](https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/releases) for a list of modifications made in each version. Also, please note that the latest version (v2.0) features substantial changes w.r.t. to the v1.x versions, whose development is no longer supported.

### Current version
PowNet v2.0 <!--([GitHub]() | [Zenodo]())-->

### Previous versions
* PowNet v1.3 ([GitHub](https://github.com/kamal0013/PowNet/tree/v1.3) | [Zenodo](https://zenodo.org/record/4688309#.YHc5euhKguU))
* PowNet v1.2 ([GitHub](https://github.com/kamal0013/PowNet/tree/v1.2) | [Zenodo](https://zenodo.org/record/4020167#.X1hqrGhKguU))
* PowNet v1.1 ([GitHub](https://github.com/kamal0013/PowNet/tree/v1.1) | [Zenodo](https://zenodo.org/record/3756750))

# Instructions

Instructions on how to run and customize the model are presented below.

## Getting started
...

## Technical guide
...

## Installation guide
...

## Quickstarter notebook
...

## API reference
...

## Support and maintenance 
For questions and feedback related to PowNet, please contact Phumthep Bunnak (<pb585@cornell.edu>) or Stefano Galelli (<galelli@cornell.edu>).

## Glossary 
...

## Input data
<!-- We will need to put these datasets on Zenodo -->
Input data are available for the following power fleets:
* Cambodia (2016) 
* Laos (2016)
* Thailand (2016)
<!-- @Phumthep, shall we add the toy case study? -->
<!-- Add when available -->
<!-- * Peninsular Malaysia -->
<!-- * Singapore -->

## License
PowNet is released under the MIT license. 

## Acknowledgement 
If you use PowNet for your research, please cite the following paper:

Chowdhury, A.F.M.K., Kern, J., Dang, T.D. and Galelli, S., 2020. [PowNet: A Network-Constrained Unit Commitment/Economic Dispatch Model for Large-Scale Power Systems Analysis.](http://doi.org/10.5334/jors.302) Journal of Open Research Software, 8(1), p.5.

## Publications
Recent papers that used PowNet:
* Koh, R., Galelli, S. (2024) [Evaluating Streamflow Forecasts in Hydro-Dominated Power Systems--When and Why They Matter.](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2023WR035825) Water Resources Research, 60, e2023WR035825.
* Galelli, S., Dang, T.D., Ng, J.Y., Chowdhury, A.F.M.K., Arias, M.E. (2022) [Curbing hydrological alterations in the Mekong–limits and opportunities of dam re-operation.](https://www.nature.com/articles/s41893-022-00971-z) Nature Sustainability, 5, 1058–1069.
* Koh, R., Kern, J., Galelli, S. (2022) [Hard-coupling water and power system models increases the complementarity of renewable energy sources.](https://www.sciencedirect.com/science/article/abs/pii/S0306261922007255) Applied Energy, 321, 119386.
* Chowdhury, A.K., Dang, T.D., Nguyen, H.T., Koh, R., and Galelli, S., (2021). [The Greater Mekong's climate-water-energy nexus: how ENSO-triggered regional droughts affect power supply and CO2 emissions.](https://doi.org/10.1029/2020EF001814) Earth’s Future, 9, e2020EF001814.
* Chowdhury, A.K., Dang, T.D., Bagchi, A., and Galelli, S., (2020). [Expected benefits of Laos' hydropower development curbed by hydro-climatic variability and limited transmission capacity—opportunities to reform.](https://doi.org/10.1061/(ASCE)WR.1943-5452.0001279) Journal of Water Resources Planning and Management, 146(10), 05020019.
