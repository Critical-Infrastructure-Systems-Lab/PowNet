
**2. Installation Guide**
=========================

Prerequisites
-------------

**PowNet requires python version >=3.10**

PowNet dependencies include:

-  "matplotlib >= 3.7.1"

-  "numpy >= 1.24.3"

-  "pandas >= 1.5.3"

-  "mplcursors >= 0.5.1"

-  "pyomo >= 6.5.0"

-  "gurobipy >= 10.0.3"

-  "networkx >= 3.1.0"

-  "highs >= 1.6.0"

Installation Steps
------------------

**1. Download PowNet from CIS Lab GitHub repository**

.. code:: console

>>> git clone https://github.com/Critical-Infrastructure-Systems-Lab/PowNet.git

**2. Modify the PYTHONPATH environment variable**

.. code:: console
>>> export PYTHONPATH="${PYTHONPATH}:/Path/to/PowNet Directory/src/ "

**3. Run the main script to run PowNet simulation and produce Outputs**

.. code:: console
>>> python main.py
