import sys
import os
from importlib.metadata import version as get_version


sys.path.insert(0, os.path.abspath("../../src/"))

# Import mock modules for readthedocs
autodoc_mock_imports = [
    "__future__",
    "abc",
    "dataclasses",
    "datetime",
    "re",
    "contextily",
    "geopandas",
    "gurobipy",
    "highspy",
    "logging",
    "matplotlib",
    "math",
    "networkx",
    "numpy",
    "pandas",
    "pmdarima",
    "scipy",
    "shapely",
    "sklearn",
    "statsmodels",
]

# -- Project information

project = "PowNet"
copyright = "2021-2025, Critical Infrastructure Systems (CIS) Lab, Cornell University"
author = "Critical Infrastructure Systems Lab (CIS), Cornell University"

# TODO: Show version and release in the documentation
release = get_version("pownet")
version = ".".join(release.split(".")[:1])

# -- General configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.doctest",
    "sphinx.ext.duration",
    "sphinx.ext.extlinks",
    "sphinx.ext.intersphinx",
    "sphinx.ext.mathjax",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx_rtd_theme",
    "sphinx_mdinclude",
    "nbsphinx",
    "nbsphinx_link",
    "sphinx_autodoc_typehints",
    "sphinxcontrib.bibtex",
]

templates_path = ["_templates"]
html_static_path = ["_static"]

# References are found here
bibtex_bibfiles = ["references.bib"]

# Create the page even when there is an error in the notebook
nbsphinx_allow_errors = True

# -- Options for HTML output
html_theme = "sphinx_rtd_theme"
html_theme_options = {}

html_show_sphinx = False


# -- customize the CSS styling
def setup(app):
    app.add_css_file("custom.css")
