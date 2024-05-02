import sys
import os
import re

# -- Project information

project = 'PowNet'
copyright = '2024, Critical Infrastructure Systems (CIS) Lab, Cornell University'
author = 'Critical Infrastructure Systems Lab (CIS), Cornell University'

release = '2.0'
version = '2.0.0'

# -- General configuration

github_username = 'HishamEldardiry'
github_repository = 'PowNet_Documentation'


extensions = [
    'sphinx.ext.duration',
    'sphinx.ext.doctest',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.intersphinx',
    'sphinx.ext.mathjax',
    'sphinx.ext.viewcode',
    'sphinx_rtd_theme',
    'sphinx.ext.viewcode',
    'sphinx_toolbox',
]

intersphinx_mapping = {
    'python': ('https://docs.python.org/3/', None),
    'sphinx': ('https://www.sphinx-doc.org/en/master/', None),
}
intersphinx_disabled_domains = ['std']

templates_path = ['_templates']
html_static_path = ['_static']

# -- Options for HTML output

html_theme = 'sphinx_rtd_theme'
html_theme_options = {
    'version': '',
    'release': '',
}

html_context = {
"display_github": True, # Add 'Edit on Github' link instead of 'View page source'
"last_updated": False,
"commit": False,
}

# -- html_show_sphinx = False

# -- Options for EPUB output
epub_show_urls = 'footnote'

# -- customize the CSS styling
def setup(app):
        app.add_css_file('custom.css')
