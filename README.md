![license MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
[![CI Tests](https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/actions/workflows/python-app.yml/badge.svg)](https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/actions)
[![GitHub Release](https://img.shields.io/github/v/release/Critical-Infrastructure-Systems-Lab/PowNet)](https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/releases/tag/v2.0)
[![Read the Docs](https://img.shields.io/readthedocs/pownet)](https://pownet.readthedocs.io/en/latest/)

# PowNet: Unit Commitment / Economic Dispatch model in Python
PowNet is a least-cost optimization model for simulating the Unit Commitment and Economic Dispatch (UC/ED) of large-scale (regional to country) power systems. In PowNet, a power system is represented by a set of nodes that include power plants, high-voltage substations, and import/export stations (for cross-border systems). The model schedules and dispatches the electricity supply from power plant units to meet hourly electricity demand in substations at a minimum cost. It considers the techno-economic constraints of both generating units and high-voltage transmission network. The power flow calculation is based on a Direct Current (DC) network (with N-1 criterion), which provides a reasonable balance between modelling accuracy and data and computational requirements. PowNet can easily integrate information about variable renewable resources (e.g., hydro, wind, solar) into the UC/ED process. For example, it can be linked with models that estimate the electricity supply available from renewable resources as a function of the climatic conditions. In addition, PowNet has provision to account for the effect of droughts on the generation of dispatchable thermal units (e.g., coal, oil, gas-fired units) that depend on freshwater availability. These features facilitate the application of PowNet to problems in the water-energy nexus domain that investigate the impact of water availability on electricity supply and demand. 

A quick start tutorial is provided here: https://pownet.readthedocs.io/en/latest/pages/quickstarter.html

Read the PowNet Documentation here: https://pownet.readthedocs.io/en/latest

## Overview of PowNet

![overview_pownet](./docs/overview_pownet.png)


