
.. |logo_image| image:: https://github.com/3dem/emhub/wiki/images/emtools-logo.png
   :height: 60px

|logo_image|

**emtools** is a Python package with utilities for manipulating CryoEM images
and metadata such as STAR files or SQLITE databases. It also contains other
miscellaneous utils for processes handling and monitoring, among others.

The library is composed by several modules that provide mainly classes to
perform certain operations.

For more detailed information check the documentation at:

https://3dem.github.io/emdocs/emtools/


Installation
------------

.. code-block:: bash

    pip install emtools

Or for development:

.. code-block:: bash

    git clone git@github.com:3dem/emtools.git
    pip install -e emtools/

Usage
-----

Testing
-------

.. code-block:: bash

    python -m unittest emtools.tests.test_utils
    python -m unittest emtools.tests.test_metadata
    python -m unittest emtools.tests.test_pipeline

How to cite
-----------

Please cite the code repository DOI: xxx

Authors
-------

 * Jose Miguel de la Rosa-Trevín, St.Jude Children's Research Hospital, Memphis, TN


 




