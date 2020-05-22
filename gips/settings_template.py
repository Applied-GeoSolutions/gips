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

# GIPS complete settings file

# Used for anonymous FTP
EMAIL = '$EMAIL'


# Site files and data tiles vectors can be retrieved from a database
DATABASES = {
#    'tiles': {
#        'NAME': '',
#        'USER': '',
#        'PASSWORD': '',
#        'HOST': '',
#        'PORT': '5432',
#    }
    'inventory': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': '$TLD/gips-inv-db.sqlite3',
    },
}

# STATS_FORMAT = {} # defaults to empty dict

# For NASA EarthData Authentication
EARTHDATA_USER = ""
EARTHDATA_PASS = ""

# For USGS machine-to-machine authentication
USGS_USER = ""
USGS_PASS = ""

# For USGS machine-to-machine authentication
ESA_USER = ""
ESA_PASS = ""

# For SciHub authentication
SCIHUB_USER = ""
SCIHUB_PASS = ""

REPOS = {
    'aod': {
        'repository': '$TLD/aod',
    },
    'landsat': {
        'repository': '$TLD/landsat',
        # Landsat specific settings
        '6S': True,            # atm correction for VIS/NIR/SWIR bands
        'MODTRAN': False,       # atm correction for LWIR
        'extract': False,       # extract files from tar.gz before processing instead of direct access
        'username': USGS_USER,
        'password': USGS_PASS,
        # 'ACOLITE_DIR':  '',   # ACOLITE installation for atm correction over water
    },
    'modis': {
        'repository': '$TLD/modis',
        'username': EARTHDATA_USER,
        'password': EARTHDATA_PASS
    },
    'sentinel2': {
        'repository': '$TLD/sentinel2',
        # sign up for access to data source here:  https://scihub.copernicus.eu/dhus/#/self-registration
        'username': ESA_USER,
        'password': ESA_PASS,
        'extract': False,  # extract files from tar.gz before processing instead of direct access
    },
    'smap': {
        'repository': '$TLD/smap',
        'username': EARTHDATA_USER,
        'password': EARTHDATA_PASS,
    },
    'gpm': {
        'repository': '$TLD/gpm',
    },
    # these drivers tend to more specialized and experimental so turned off by default
    'cdl': {
        'repository': '$TLD/cdl',
    },
    'prism': {
        'repository': '$TLD/prism',
    },
    'sar': {
        'repository': '$TLD/sar',
    },
    #'sarannual': {
    #    'repository': '$TLD/sarannual',
    #},
    'merra': {
        'repository': '$TLD/merra',
        'username': EARTHDATA_USER,
        'password': EARTHDATA_PASS
    },
    'daymet': {
        'repository': '$TLD/daymet',
    },
    'hls': {
        'repository': '$TLD/hls',
    },
    'chirps': {
        'repository': '$TLD/chirps',
    },
    'sentinel1': {
        'repository': '$TLD/sentinel1',
        'username': SCIHUB_USER,
        'password': SCIHUB_PASS,
    },
}


"""
# to add repository add new key to the REPOS dictionary
    'dataname': {
        # path to driver directory location (default to gips/data/dataname/ if not given)
        'driver': '',
        # path to top level directory of data
        'repository': '',
        # override location of tiles vector (default to gips/data/dataname/tiles.shp)
       'tiles': '',
        #'tiles': 'mydatabase:mydatatype_tiles',        # database format
        #'tiles': '~/randomdir/dataname_tiles.shp'      # file format
    }
"""
