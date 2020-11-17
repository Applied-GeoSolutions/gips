#!/usr/bin/env python
################################################################################
#    GIPS: Geospatial Image Processing System
#
#    AUTHOR: Matthew Hanson
#    EMAIL:  matt.a.hanson@gmail.com
#
#    Copyright (C) 2014-2018 Applied Geosolutions
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program. If not, see <http://www.gnu.org/licenses/>
################################################################################

"""
setup for GIPS
"""

import os
from setuptools import setup, find_packages
import shutil
import glob
import traceback
import imp

__version__ = imp.load_source('gips.version', 'gips/version.py').__version__

# collect console scripts to install
console_scripts = []
for f in glob.glob('gips/scripts/*.py'):
    name = os.path.splitext(os.path.basename(f))[0]
    if name not in ['__init__', 'core']:
        script = 'gips_%s = gips.scripts.%s:main' % (name, name.lower())
        console_scripts.append(script)


setup(
    name='gips',
    version=__version__,
    description='Geospatial Image Processing System',
    author='Matthew Hanson',
    author_email='matt.a.hanson@gmail.com',
    license='GNU General Public License v3 (GPLv3)',
    python_requires='>=3',
    packages=find_packages(),
    package_data={
        '': ['*.shp', '*.prj', '*.shx', '*.dbf', '*.csv'],
        'gips': [
            'acolite.cfg',
            'data/landsat/input_file_tmp.inp',
            'data/landsat/lndortho.cps_par.ini',
        ],
    },
    install_requires=[
        # better to install here but it seems to cause apt conflicts:  'GDAL', 'numpy',
        'six',
        # because requests is a diva and won't leave its trailer otherwise:
        'urllib3',
        'Cython',
        'rios',
        'python-fmask',
    ],
    entry_points={'console_scripts': console_scripts},
    zip_safe=False,
    classifiers=[
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    ],
)
