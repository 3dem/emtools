# **************************************************************************
# *
# * Authors:  J. M. de la Rosa Trevin (delarosatrevin@gmail.com)
# * Authors:  Grigory Sharov (sharov.grigory@gmail.com)
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 3 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'delarosatrevin@gmail.com'
# *
# **************************************************************************

"""A setuptools based setup module.
See:
https://packaging.python.org/en/latest/distributing.html
https://github.com/pypa/sampleproject
"""

# Always prefer setuptools over distutils
from setuptools import setup, find_packages
# To use a consistent encoding
from codecs import open
from os import path
import emtools

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

# Arguments marked as "Required" below must be included for upload to PyPI.
# Fields marked as "Optional" may be commented out.

setup(
    name='emtools',  # Required
    version=emtools.__version__,  # Required
    description='Basic utilities for CryoEM data manipulation',  # Required
    long_description=long_description,  # Optional
    url='https://github.com/3dem/emtools',  # Optional
    author='J.M. De la Rosa Trevin, Grigory Sharov',  # Optional
    author_email='delarosatrevin@gmail.com, gsharov@mrc-lmb.cam.ac.uk',  # Optional
    classifiers=[  # Optional
        'Development Status :: 1 - Planning',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3'
    ],
    keywords='electron-microscopy cryo-em structural-biology image-processing',  # Optional
    packages=find_packages(),
    project_urls={  # Optional
        'Bug Reports': 'https://github.com/3dem/emtools/issues',
        'Source': 'https://github.com/3dem/emtools',
    },
)
