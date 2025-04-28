
.. autosummary::
    :toctree: _source/

#######################
Installation
#######################

`PowNet` is a Python package available on `PyPI`. It is designed to be compatible with `Python 3.12` and above. Depending on your needs, you can choose between two installation options: a regular user or a power user. The following sections will guide you through the installation process for both options.

The following step is highly recommended for any user: creating a virtual environment to manage dependencies. If using `Conda`, we can create an envrionment with the following command

.. code-block:: bash

    conda create --name your_env_name_here
    conda activate your_env_name_here

If deciding on a name for the environment takes too long, please feel free to name the environment as "pownet".

**Option 1: Regular user**

A regular user is someone who has created their input files and wish to just run `PowNet`. In this case, it is best to simply install `PowNet` as a package from PyPI. We can achieve this with the following command:

.. code-block:: bash

    pip install pownet


**Option 2: Power user (no pun intended)**

In case we wish to modify the source code, `PowNet` should be installed as an editable package. First, download or clone the `PowNet` repository to your local machine. For example: if we want to clone to "C://user/pownet",

.. code-block:: bash

    git clone https://github.com/your-username/pownet.git C://user/pownet


Next, open a terminal and navigate to the directory where we cloned the repository:

.. code-block:: bash

    cd C://user/pownet

Now, we can install this `PowNet` package using pip, which is a manager for Python packages:

.. code-block:: bash

    pip install -e .

This command installs the package in "editable" mode (-e) using pyproject.toml that is located in the root directory of `PowNet`. The editable mode allows us to edit `PowNet` codebase when we need to modify or implement new features. The pyproject.toml file specifies the dependencies required to run `PowNet`.
