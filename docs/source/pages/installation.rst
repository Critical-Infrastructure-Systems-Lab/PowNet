
**2. Installation Guide**
=========================

Prerequisites
-------------

**PowNet requires python version >=3.10**

PowNet dependencies are listed in `pyproject.toml <https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/blob/master/pyproject.toml>`_.

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
