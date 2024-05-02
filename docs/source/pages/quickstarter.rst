
**4. Quickstarter Notebook**
============================

**1. Install Jupyter Notebook**

.. code:: shell

  >>> pip install jupyterlab

**2. Launch a Jupyter Notebook from the terminal**

.. code:: shell

  >>> jupyter lab

**3. Download PowNet from CIS Lab GitHub Repo**

.. code:: shell
  
  >>> ! git clone https://github.com/Critical-Infrastructure-Systems-Lab/PowNet.git

**4. Change directory to PowNet folder**

.. code:: python

  >>> import os
  
  >>> os.chdir('PowNet/')
  
  >>> os.getcwd()

**5. Make changes in user input variables**
  
.. code:: python

  >>> %load main.py

*Make changes in* ``main.py`` *loaded in the notebaook [e.g.,* ``MODEL_NAME`` *to define region of interest,* ``T`` *for Simulation Horizon,
or* ``use_gurobi`` *to choose optimization solver] and then save changes.*

.. code:: python

  >>> %save main.py

**6. Add the PYTHONPATH environment variable**

.. code:: python

  >>> import sys
  
  >>> sys.path.append('/Path/to/PowNet Directory/src/')

**7. Run PowNet Simulation**

.. code:: python

  >>> %run main.py
