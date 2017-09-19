#!/usr/bin/env python
################################################################################
#    GIPS: Geospatial Image Processing System
#
#    AUTHOR: Matthew Hanson
#    EMAIL:  matt.a.hanson@gmail.com
#
#    Copyright (C) 2014 Applied Geosolutions
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
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


import os
import re
from datetime import datetime, date
import shutil
import glob
import traceback
from copy import deepcopy
import commands
import tempfile
import tarfile

import numpy
import gippy
from gippy import algorithms
from usgs import api
from homura import download

from gips.data.core import Repository, Asset, Data
from gips.atmosphere import SIXS, MODTRAN
import gips.atmosphere
from gips.utils import RemoveFiles, basename, settings, verbose_out
from gips import utils



requirements = ['Py6S>=1.5.0']


def binmask(arr, bit):
    """ Return boolean array indicating which elements as binary have a 1 in
        a specified bit position. Input is Numpy array.
    """
    return arr & (1 << (bit - 1)) == (1 << (bit - 1))


class landsatRepository(Repository):
    """ Singleton (all class methods) to be overridden by child data classes """
    name = 'Landsat'
    description = 'Landsat 5 (TM), 7 (ETM+), 8 (OLI)'
    _tile_attribute = 'pr'

    @classmethod
    def feature2tile(cls, feature):
        tile = super(landsatRepository, cls).feature2tile(feature)
        return tile.zfill(6)


class landsatAsset(Asset):
    """ Landsat asset (original raw tar file) """
    Repository = landsatRepository

    # tassled cap coefficients for L5 and L7
    _tcapcoef = [
        [0.3561, 0.3972, 0.3904, 0.6966, 0.2286, 0.1596],
        [-0.3344, -0.3544, -0.4556, 0.6966, -0.0242, -0.2630],
        [0.2626, 0.2141, 0.0926, 0.0656, -0.7629, -0.5388],
        [0.0805, -0.0498, 0.1950, -0.1327, 0.5752, -0.7775],
        [-0.7252, -0.0202, 0.6683, 0.0631, -0.1494, -0.0274],
        [0.4000, -0.8172, 0.3832, 0.0602, -0.1095, 0.0985]
    ]

    # combine sensormeta with sensor
    _sensors = {
        #'LT4': {
        #    'description': 'Landsat 4',
        #},
        'LT5': {
            'description': 'Landsat 5',
            'startdate': datetime(1984, 3, 1),
            'enddate': datetime(2013, 1, 1),
            'bands': ['1', '2', '3', '4', '5', '6', '7'],
            'oldbands': ['1', '2', '3', '4', '5', '6', '7'],
            'colors': ["BLUE", "GREEN", "RED", "NIR", "SWIR1", "LWIR", "SWIR2"],
            # TODO - update bands with actual L5 values (these are L7)
            'bandlocs': [0.4825, 0.565, 0.66, 0.825, 1.65, 11.45, 2.22],
            'bandwidths': [0.065, 0.08, 0.06, 0.15, 0.2, 2.1, 0.26],
            'E': [1983, 1796, 1536, 1031, 220.0, 0, 83.44],
            'K1': [0, 0, 0, 0, 0, 607.76, 0],
            'K2': [0, 0, 0, 0, 0, 1260.56, 0],
            'tcap': _tcapcoef,
        },
        'LE7': {
            'description': 'Landsat 7',
            'startdate': datetime(1999, 4, 15),
            #bands = ['1','2','3','4','5','6_VCID_1','6_VCID_2','7','8']
            'bands': ['1', '2', '3', '4', '5', '6_VCID_1', '7'],
            'oldbands': ['1', '2', '3', '4', '5', '61', '7'],
            'colors': ["BLUE", "GREEN", "RED", "NIR", "SWIR1", "LWIR", "SWIR2"],
            'bandlocs': [0.4825, 0.565, 0.66, 0.825, 1.65, 11.45, 2.22],
            'bandwidths': [0.065, 0.08, 0.06, 0.15, 0.2, 2.1, 0.26],
            'E': [1997, 1812, 1533, 1039, 230.8, 0, 84.90],
            'K1': [0, 0, 0, 0, 0, 666.09, 0],
            'K2': [0, 0, 0, 0, 0, 1282.71, 0],
            'tcap': _tcapcoef,
        },
        'LC8': {
            'description': 'Landsat 8',
            'startdate': datetime(2013, 4, 1),
            'bands': ['1', '2', '3', '4', '5', '6', '7', '9', '10', '11'],
            'oldbands': ['1', '2', '3', '4', '5', '6', '7', '9', '10', '11'],
            'colors': ["COASTAL", "BLUE", "GREEN", "RED", "NIR",
                       "SWIR1", "SWIR2", "CIRRUS", "LWIR", "LWIR2"],
            'bandlocs': [0.443, 0.4825, 0.5625, 0.655, 0.865,
                         1.610, 2.2, 1.375, 10.8, 12.0],
            'bandwidths': [0.01, 0.0325, 0.0375, 0.025, 0.02,
                           0.05, 0.1, 0.015, 0.5, 0.5],
            'E': [2638.35, 2031.08, 1821.09, 2075.48, 1272.96,
                  246.94, 90.61, 369.36, 0, 0],
            'K1': [0, 0, 0, 0, 0,
                   0, 0, 0, 774.89, 480.89],
            'K2': [0, 0, 0, 0, 0,
                   0, 0, 0, 1321.08, 1201.14],
            'tcap': [
                [0.3029, 0.2786, 0.4733, 0.5599, 0.508, 0.1872],
                [-0.2941, -0.243, -0.5424, 0.7276, 0.0713, -0.1608],
                [0.1511, 0.1973, 0.3283, 0.3407, -0.7117, -0.4559],
                [-0.8239, 0.0849, 0.4396, -0.058, 0.2013, -0.2773],
                [-0.3294, 0.0557, 0.1056, 0.1855, -0.4349, 0.8085],
                [0.1079, -0.9023, 0.4119, 0.0575, -0.0259, 0.0252],
            ]
        },
        'LC8SR': {
            'description': 'Landsat 8 Surface Reflectance',
            'startdate': datetime(2013, 4, 1),
        }

    }

    _assets = {
        'DN': {
            'sensors': ['LT5', 'LE7', 'LC8'],
            'enddate': datetime(2017, 4, 30),
            'pattern': (
                r'^L(?P<sensor>[A-Z])(?P<satellie>\d)'
                r'(?P<path>\d{3})(?P<row>\d{3})'
                r'(?P<acq_year>\d{4})(?P<acq_day>\d{3})'
                r'(?P<gsi>[A-Z]{3})(?P<version>\d{2})\.tar\.gz$'
            ),
        },
        'SR': {
            'sensors': ['LC8SR'],
            'pattern': r'^L.*?-SC.*?\.tar\.gz$',
        },
        'C1': {
            'sensors': ['LT5', 'LE7', 'LC8'],
            'pattern': (
                r'^L(?P<sensor>\w)(?P<satellite>\d{2})_'
                r'(?P<correction_level>.{4})_(?P<path>\d{3})(?P<row>\d{3})_'

                r'(?P<acq_year>\d{4})(?P<acq_month>\d{2})(?P<acq_day>\d{2})_'
                r'(?P<proc_year>\d{4})(?P<proc_month>\d{2})(?P<proc_day>\d{2})_'
                r'(?P<coll_num>\d{2})_(?P<coll_cat>.{2})\.tar\.gz$'
            ),
            'latency': 12,
        },
    }

    # Field ids are retrieved with `api.dataset_fields()` call
    _ee_datasets = {
        'LANDSAT_8_C1': {
            'path_field': '20514',
            'row_field': '20516',
        },
        'LANDSAT_ETM_C1': {
            'path_field': '19884',
            'row_field': '19887',
        },
        'LANDSAT_TM_C1': {
            'path_field': '19873',
            'row_field': '19879',
        },
    }

    # Set the startdate to the min date of the asset's sensors
    for asset, asset_info in _assets.iteritems():
        asset_info['startdate'] = min(
            [_sensors[sensor]['startdate']
                for sensor in asset_info['sensors']]
        )

    _defaultresolution = [30.0, 30.0]

    def __init__(self, filename):
        """ Inspect a single file and get some metadata """
        super(landsatAsset, self).__init__(filename)

        fname = os.path.basename(filename)

        verbose_out(("fname", fname), 2)

        sr_pattern_re = re.compile(self._assets['SR']['pattern'])
        dn_pattern_re = re.compile(self._assets['DN']['pattern'])
        c1_pattern_re = re.compile(self._assets['C1']['pattern'])

        sr_match = sr_pattern_re.match(fname)
        dn_match = dn_pattern_re.match(fname)
        c1_match = c1_pattern_re.match(fname)

        if sr_match:
            verbose_out('SR asset', 2)
            self.asset = 'SR'
            self.sensor = 'LC8SR'
            self.version = int(fname[20:22])
            self.tile = fname[3:9]
            self.date = datetime.strptime(fname[9:16], "%Y%j")

        elif dn_match:
            verbose_out('DN asset', 2)
            self.tile = dn_match.group('path') + dn_match.group('row')
            year = dn_match.group('acq_year')
            doy = dn_match.group('acq_day')
            self.date = datetime.strptime(year + doy, "%Y%j")

            self.asset = 'DN'
            self.sensor = fname[0:3]
            self.version = int(fname[19:21])
        elif c1_match:
            utils.verbose_out('C1 asset', 2)

            self.tile = c1_match.group('path') + c1_match.group('row')
            year = c1_match.group('acq_year')
            month = c1_match.group('acq_month')
            day = c1_match.group('acq_day')
            self.date = datetime.strptime(year + month + day, "%Y%m%d")

            self.asset = 'C1'
            self.sensor = "L{}{}".format(c1_match.group('sensor'), int(c1_match.group('satellite')))
            self.collection_number = c1_match.group('coll_num')
            self.collection_category = c1_match.group('coll_cat')
            self.version = 1e6 * int(self.collection_number) + \
                    (self.date - datetime(2017, 1, 1)).days + \
                    {'RT': 0, 'T2': 0.5, 'T1': 0.9}[self.collection_category]
        else:
            msg = "No matching landsat asset type for '{}'".format(fname)
            raise RuntimeError(msg, filename)

        if self.asset in ['DN', 'C1']:
            smeta = self._sensors[self.sensor]
            self.meta = {}
            for i, band in enumerate(smeta['colors']):
                wvlen = smeta['bandlocs'][i]
                self.meta[band] = {
                    'bandnum': i + 1,
                    'wvlen': wvlen,
                    'wvlen1': wvlen - smeta['bandwidths'][i] / 2.0,
                    'wvlen2': wvlen + smeta['bandwidths'][i] / 2.0,
                    'E': smeta['E'][i],
                    'K1': smeta['K1'][i],
                    'K2': smeta['K2'][i],
                }
            self.visbands = [col for col in smeta['colors'] if col[0:4] != "LWIR"]
            self.lwbands = [col for col in smeta['colors'] if col[0:4] == "LWIR"]

        if self.sensor not in self._sensors.keys():
            raise Exception("Sensor %s not supported: %s" % (self.sensor, filename))

    @classmethod
    def query_service(cls, asset, tile, date):
        available = []

        if asset in ['DN', 'SR']:
            verbose_out('Landsat "{}" assets are no longer fetchable'.format(asset), 4)
            return available

        path = tile[:3]
        row = tile[3:]
        fdate = date.strftime('%Y-%m-%d')

        username = settings().REPOS['landsat']['username']
        password = settings().REPOS['landsat']['password']
        api_key = api.login(username, password)['data']
        available = []
        for dataset in cls._ee_datasets.keys():
            response = api.search(
                dataset, 'EE',
                start_date=fdate, end_date=fdate,
                where={
                    cls._ee_datasets[dataset]['path_field']: path,
                    cls._ee_datasets[dataset]['row_field']: row,
                },
                api_key=api_key
            )['data']

            for result in response['results']:
                available.append({
                    'basename': result['displayId'] + '.tar.gz',
                    'sceneID': result['entityId'],
                    'dataset': dataset,
                })

        return available

    @classmethod
    def fetch(cls, asset, tile, date):
        fdate = date.strftime('%Y-%m-%d')
        response = cls.query_service(asset, tile, date)
        if len(response) > 0:
            verbose_out('Fetching %s %s %s' % (asset, tile, fdate), 1)
            if len(response) != 1:
                raise Exception('Single date, single location, '
                                'returned more than one result')
            result = response[0]
            utils.verbose_out(str(response), 4)
            sceneID = result['sceneID']
            stage_dir = cls.Repository.path('stage')
            sceneIDs = [str(sceneID)]

            username = settings().REPOS['landsat']['username']
            password = settings().REPOS['landsat']['password']
            api_key = api.login(username, password)['data']
            url = api.download(
                result['dataset'], 'EE', sceneIDs, 'STANDARD', api_key
            )['data'][0]
            with utils.make_temp_dir(prefix='dwnld', dir=stage_dir) as dldir:
                download(url, dldir)
                granules = os.listdir(dldir)
                if len(granules) == 0:
                    raise Exception(
                        'Download appears to have not produced a file: {}'
                        .format(str(granules))
                    )
                os.rename(
                    os.path.join(dldir, granules[0]),
                    os.path.join(stage_dir, granules[0]),
                )

    def updated(self, newasset):
        '''
        Compare the version for this to that of newasset.
        Return true if newasset version is greater.
        '''
        return (self.sensor == newasset.sensor and
                self.tile == newasset.tile and
                self.date == newasset.date and
                self.version < newasset.version)

def unitless_bands(*bands):
    return [{'name': b, 'units': Data._unitless} for b in bands]

class landsatData(Data):
    name = 'Landsat'
    version = '1.0.0'

    Asset = landsatAsset

    _lt5_startdate = date(1984, 3, 1)
    _lc8_startdate = date(2013, 5, 30)

    # Group products belong to ('Standard' if not specified)
    _productgroups = {
        'Index': ['bi', 'evi', 'lswi', 'msavi2', 'ndsi', 'ndvi', 'ndwi',
                  'satvi', 'vari'],
        'Tillage': ['ndti', 'crc', 'sti', 'isti'],
        'LC8SR': ['ndvi8sr'],
        'ACOLITE': [
            'rhow', 'oc2chl', 'oc3chl', 'fai', 'spm655', 'turbidity',
            'acoflags',
            # 'rhoam',  # Dropped for the moment due to issues in ACOLITE
        ],
    }
    __toastring = 'toa: use top of the atmosphere reflectance'
    __visible_bands_union = [color for color in Asset._sensors['LC8']['colors'] if 'LWIR' not in color]
    _products = {
        #'Standard':
        'rad': {
            'assets': ['DN', 'C1'],
            'description': 'Surface-leaving radiance',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 1,
            # units given by https://landsat.usgs.gov/landsat-8-l8-data-users-handbook-section-5
            'bands': [{'name': n, 'units': 'W/m^2/sr/um'} for n in __visible_bands_union],
        },
        'ref': {
            'assets': ['DN', 'C1'],
            'description': 'Surface reflectance',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands(*__visible_bands_union)
        },
        'temp': {
            'assets': ['DN', 'C1'],
            'description': 'Brightness (apparent) temperature',
            'toa': True,
            'startdate': _lt5_startdate,
            'latency': 1,
            # units given by https://landsat.usgs.gov/landsat-8-l8-data-users-handbook-section-5
            'bands': [{'name': n, 'units': 'degree Kelvin'} for n in ['LWIR', 'LWIR2']],
        },
        'acca': {
            'assets': ['DN', 'C1'],
            'description': 'Automated Cloud Cover Assessment',
            'arguments': [
                'X: erosion kernel diameter in pixels (default: 5)',
                'Y: dilation kernel diameter in pixels (default: 10)',
                'Z: cloud height in meters (default: 4000)'
            ],
            'nargs': '*',
            'toa': True,
            'startdate': _lt5_startdate,
            'latency': 1,
            # percentage, so unitless, per landsat docs:
            # https://landsat.usgs.gov/how-percentage-cloud-cover-calculated
            'bands': unitless_bands('finalmask', 'cloudmask', 'ambclouds', 'pass1'),
        },
        'fmask': {
            'assets': ['DN', 'C1'],
            'description': 'Fmask cloud cover',
            'nargs': '*',
            'toa': True,
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands('finalmask', 'cloudmask',
                                    'PCP', 'clearskywater', 'clearskyland'),
        },
        'cloudmask': {
            'assets': ['C1'],
            'description': 'Cloud (and shadow) mask product based on cloud bits of the quality band',
            'toa': True,
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands('cloudmask'),
        },
        'tcap': {
            'assets': ['DN', 'C1'],
            'description': 'Tassled cap transformation',
            'toa': True,
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands('Brightness', 'Greenness', 'Wetness', 'TCT4', 'TCT5', 'TCT6'),
        },
        'dn': {
            'assets': ['DN', 'C1'],
            'description': 'Raw digital numbers',
            'toa': True,
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': [{'name': n, 'units': 'W/m^2/sr/um'} for n in __visible_bands_union],
        },
        'volref': {
            'assets': ['DN', 'C1'],
            'description': 'Volumetric water reflectance - valid for water only',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 1,
            # reflectance is unitless therefore volref should be unitless
            'bands': unitless_bands(*__visible_bands_union),
        },
        'wtemp': {
            'assets': ['DN', 'C1'],
            'description': 'Water temperature (atmospherically correct) - valid for water only',
            # It's not really TOA, but the product code will take care of atm correction itself
            'toa': True,
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': [{'name': n, 'units': 'degree Kelvin'} for n in ['LWIR', 'LWIR2']],
        },
        'bqa': {
            'assets': ['DN', 'C1'],
            # TODO prior description was too long; is this a good-enough short replacement?
            'description': 'The quality band extracted into separate layers.',
            # 'description': ('The bit-packed information in the QA bands is translation of binary strings. '
            # 'As a simple example, the integer value "1" translates to the binary value "0001." The binary value '
            # '"0001" has 4 bits, written right to left as bits 0 ("1"), 1 ("0"), 2 ("0"), and 3 ("0"). '
            # 'Each of the bits 0-3 represents a yes/no indication of a physical value.'),
            'toa': True,
            'startdate': _lc8_startdate,
            'latency': 1,
            'bands': unitless_bands('allgood', 'notfilled', 'notdropped', 'notterrain',
                                    'notsnow', 'notcirrus', 'notcloud'),
        },
        'bqashadow': {
            'assets': ['DN', 'C1'],
            'description': 'LC8 QA + Shadow Smear',
            'arguments': [
                'X: erosion kernel diameter in pixels (default: 5)',
                'Y: dilation kernel diameter in pixels (default: 10)',
                'Z: cloud height in meters (default: 4000)'
            ],
            'nargs': '*',
            'toa': True,
            'startdate': _lc8_startdate,
            'latency': 1,
            'bands': unitless_bands('bqashadow'),
        },
        #'Indices': {
        'bi': {
            'assets': ['DN', 'C1'],
            'description': 'Brightness Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands('bi'),
        },
        'evi': {
            'assets': ['DN', 'C1'],
            'description': 'Enhanced Vegetation Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands('evi'),
        },
        'lswi': {
            'assets': ['DN', 'C1'],
            'description': 'Land Surface Water Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands('lswi'),
        },
        'msavi2': {
            'assets': ['DN', 'C1'],
            'description': 'Modified Soil-Adjusted Vegetation Index (revised)',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands('msavi2'),
        },
        'ndsi': {
            'assets': ['DN', 'C1'],
            'description': 'Normalized Difference Snow Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands('ndsi'),
        },
        'ndvi': {
            'assets': ['DN', 'C1'],
            'description': 'Normalized Difference Vegetation Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands('ndvi'),
        },
        'ndwi': {
            'assets': ['DN', 'C1'],
            'description': 'Normalized Difference Water Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands('ndwi'),
        },
        'satvi': {
            'assets': ['DN', 'C1'],
            'description': 'Soil-Adjusted Total Vegetation Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands('satvi'),
        },
        'vari': {
            'assets': ['DN', 'C1'],
            'description': 'Visible Atmospherically Resistant Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands('vari'),
        },
        #'Tillage Indices': {
        'ndti': {
            'assets': ['DN', 'C1'],
            'description': 'Normalized Difference Tillage Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands('ndti'),
        },
        'crc': {
            'assets': ['DN', 'C1'],
            'description': 'Crop Residue Cover',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands('crc'),
        },
        'sti': {
            'assets': ['DN', 'C1'],
            'description': 'Standard Tillage Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands('sti'),
        },
        'isti': {
            'assets': ['DN', 'C1'],
            'description': 'Inverse Standard Tillage Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 1,
            'bands': unitless_bands('isti'),
        },
        # NEW!!!
        'ndvi8sr': {
            'assets': ['SR'],
            'description': 'Normalized Difference Vegetation from LC8SR',
            'startdate': _lc8_startdate,
            'latency': 1,
            'bands': unitless_bands('ndvi8sr'),
        },
        'landmask': {
            'assets': ['SR'],
            'description': 'Land mask from LC8SR',
            'startdate': _lc8_startdate,
            'latency': 1,
            'bands': unitless_bands('landmask'),
        },
    }

    gips.atmosphere.add_acolite_product_dicts(_products, 'DN', 'C1')

    for product, product_info in _products.iteritems():
        product_info['startdate'] = min(
            [landsatAsset._assets[asset]['startdate']
                for asset in product_info['assets']]
        )

        if 'C1' in product_info['assets']:
            product_info['latency'] = landsatAsset._assets['C1']['latency']
        else:
            product_info['latency'] = float("inf")

    def _process_indices(self, image, metadata, sensor, indices):
        """Process the given indices and add their files to the inventory.

        Image is a GeoImage suitable for generating the indices.
        Metadata is passed in to the gippy indices() call.  Sensor is
        used to generate index filenames and saving info about the
        product to self. Indices is a dict of desired keys; keys and
        values are the same as requested products in process().
        """
        verbose_out("Starting on {} indices: {}".format(len(indices), indices.keys()), 2)
        for prod_and_args, split_p_and_a in indices.items():
            verbose_out("Starting on {}".format(prod_and_args), 3)
            temp_fp = self.temp_product_filename(sensor, prod_and_args)
            # indices() assumes many indices per file; we just want one
            imgout = algorithms.indices(image, [split_p_and_a[0]], temp_fp)
            imgout.add_meta(metadata)
            archived_fp = self.archive_temp_path(temp_fp)
            self.AddFile(sensor, prod_and_args, archived_fp)

    @classmethod
    def set_band_names(cls, geo_image, names):
        for i in range(len(geo_image)):
            geo_image.set_bandname(names[i], i + 1)

    @Data.proc_temp_dir_manager
    def process(self, products=None, overwrite=False, **kwargs):
        """ Make sure all products have been processed """
        verbose_out('starting landsat processing!', 3)
        products = super(landsatData, self).process(products, overwrite, **kwargs)
        if len(products) == 0:
            return

        start = datetime.now()

        assets = set() # assets needed for this process() run
        for key, val in products.requested.items():
            assets.update(self._products[val[0]]['assets'])

        if assets == set(['C1', 'DN']):
            if 'C1' in self.assets: # prefer C1
                asset = 'C1'
            elif 'DN' in self.assets:
                asset = 'DN'
            else:
                raise ValueError(
                    'No valid asset found for C1 nor DN for {} {}'.format(
                        self.basename))
        else:
            if len(assets) > 1:
                # TODO document the reason why not
                raise ValueError("Cannot create products from"
                                 " this combination of assets:  {}".format(assets))
            asset = list(assets)[0]

        a_obj = self.assets[asset] # TODO replace the latter with the former

        # TODO: De-hack this
        # Better approach, but needs some thought, is to loop over assets
        # Ian, you are right. I just don't have enough time to do it.

        if asset == 'SR':

            datafiles = self.assets['SR'].datafiles()

            imgpaths = dict()

            for datafile in datafiles:

                key = datafile.partition('_')[2].split('.')[0]
                path = os.path.join('/vsitar/' + self.assets['SR'].filename, datafile)

                imgpaths[key] = path

            # print imgpaths

            sensor = 'LC8SR'

            for key, val in products.requested.items():
                fname = self.temp_product_filename(sensor, key)

                if val[0] == "ndvi8sr":
                    img = gippy.GeoImage([imgpaths['sr_band4'], imgpaths['sr_band5']])

                    missing = float(img[0].nodata())

                    red = img[0].read().astype('float32')
                    nir = img[1].read().astype('float32')

                    wvalid = numpy.where((red != missing) & (nir != missing) & (red + nir != 0.0))

                    red[wvalid] *= 1.E-4
                    nir[wvalid] *= 1.E-4

                    # TODO: change this so that these pixels become missing
                    red[(red != missing) & (red < 0.0)] = 0.0
                    red[red > 1.0] = 1.0
                    nir[(nir != missing) & (nir < 0.0)] = 0.0
                    nir[nir > 1.0] = 1.0

                    ndvi = missing + numpy.zeros_like(red)
                    ndvi[wvalid] = (nir[wvalid] - red[wvalid])/(nir[wvalid] + red[wvalid])

                    verbose_out("writing " + fname, 2)
                    imgout = gippy.GeoImage.create_from(img, fname, img, 1, 'float32')
                    imgout.set_nodata(-9999.)
                    imgout.set_offset(0.0)
                    imgout.set_gain(1.0)
                    imgout.set_bandname('NDVI', 1)
                    imgout[0].write(ndvi)

                if val[0] == "landmask":
                    img = gippy.GeoImage([imgpaths['cfmask'], imgpaths['cfmask_conf']])

                    cfmask = img[0].read()
                    # array([  0,   1,   2,   3,   4, 255], dtype=uint8)
                    # 0 means clear! but I want 1 to mean clear

                    cfmask[cfmask > 0] = 2
                    cfmask[cfmask == 0] = 1
                    cfmask[cfmask == 2] = 0

                    verbose_out("writing " + fname, 2)
                    imgout = gippy.GeoImage.create_from(img, fname, 1, 'byte')
                    imgout.set_bandname('Land mask', 1)
                    imgout[0].write(cfmask)

                archive_fp = self.archive_temp_path(fname)
                self.AddFile(sensor, key, archive_fp)

        elif asset == 'DN' or asset == 'C1':
            # This block contains everything that existed in the first generation Landsat driver
            # Add the sensor for this date to the basename
            self.basename = self.basename + '_' + self.sensors[asset]

            # Read the assets
            with utils.error_handler('Error reading ' + basename(self.assets[asset].filename)):
                img = self._readraw()

            meta = self.assets[asset].meta
            visbands = self.assets[asset].visbands
            lwbands = self.assets[asset].lwbands
            md = self.meta_dict()

            # running atmosphere if any products require it
            toa = True
            for val in products.requested.values():
                toa = toa and (self._products[val[0]].get('toa', False) or 'toa' in val)
            if not toa:
                start = datetime.now()

                if not settings().REPOS[self.Repository.name.lower()]['6S']:
                    raise Exception('6S is required for atmospheric correction')
                with utils.error_handler('Problem running 6S atmospheric model'):
                    wvlens = [(meta[b]['wvlen1'], meta[b]['wvlen2']) for b in visbands]
                    geo = self.metadata['geometry']
                    atm6s = SIXS(visbands, wvlens, geo, self.metadata['datetime'],
                                 sensor=self.sensor_set[0])
                    md["AOD Source"] = str(atm6s.aod[0])
                    md["AOD Value"] = str(atm6s.aod[1])

            # Break down by group
            groups = products.groups()
            # ^--- has the info about what products the user requested

            # create non-atmospherically corrected apparent reflectance and temperature image
            reflimg = gippy.GeoImage(img)
            theta = numpy.pi * self.metadata['geometry']['solarzenith'] / 180.0
            sundist = (1.0 - 0.016728 * numpy.cos(numpy.pi * 0.9856 * (float(self.day) - 4.0) / 180.0))
            for col in self.assets[asset].visbands:
                reflimg[col] = img[col] * (1.0 /
                        ((meta[col]['E'] * numpy.cos(theta)) / (numpy.pi * sundist * sundist)))
            for col in self.assets[asset].lwbands:
                reflimg[col] = (((img[col].pow(-1)) * meta[col]['K1'] + 1).log().pow(-1)
                        ) * meta[col]['K2'] - 273.15

            # This is landsat, so always just one sensor for a given date
            sensor = self.sensors[asset]

            # Process standard products (this is in the 'DN' block)
            for key, val in groups['Standard'].items():
                start = datetime.now()
                # TODO - update if no atmos desired for others
                toa = self._products[val[0]].get('toa', False) or 'toa' in val
                # Create product
                with utils.error_handler(
                        'Error creating product {} for {}'
                        .format(key, basename(self.assets[asset].filename)),
                        continuable=True):
                    fname = self.temp_product_filename(sensor, key)
                    if val[0] == 'acca':
                        raise NotImplementedError("ACCA is currently not functional with gippy 1.0")
                        s_azim = self.metadata['geometry']['solarazimuth']
                        s_elev = 90 - self.metadata['geometry']['solarzenith']
                        erosion, dilation, cloudheight = 5, 10, 4000
                        if len(val) >= 4:
                            erosion, dilation, cloudheight = [int(v) for v in val[1:4]]
                        res_set = set((p.x(), p.y()) for p in (
                            reflimg[b].resolution() for b in (a_obj.visbands + a_obj.lwbands)))
                        assert res_set, 'no resolutions found in reflimg' # sanity check
                        if len(res_set) > 1:
                            raise Exception("ACCA requires all bands to have the same "
                                            "spatial resolution; found: " + str(list(res_set)))
                        imgout = algorithms.acca(reflimg, fname, s_elev,
                                                 s_azim, erosion, dilation, cloudheight)
                    elif val[0] == 'fmask':
                        raise NotImplementedError(
                                "fmask is currently not functional with gippy 1.0")
                        # currently errors out due to some 'water' band not being present
                        tolerance, dilation = 3, 5
                        if len(val) >= 3:
                            tolerance, dilation = [int(v) for v in val[1:3]]
                        imgout = algorithms.fmask(reflimg, fname, tolerance, dilation)

                    elif val[0] == 'cloudmask':
                        npqa = self._readqa()
                        # https://landsat.usgs.gov/collectionqualityband
                        # cloudmaskmask = (cloud and (cc_med or cc_high)) or csc_med or csc_high
                        # cloud iff bit 4
                        # (cc_med or cc_high) iff bit 6
                        # (csc_med or csc_high) iff bit 8

                        def get_bit(np_array, i):
                            """Return an array with the ith bit extracted from each cell."""
                            return (np_array >> i) & 0b1

                        np_cloudmask = numpy.logical_not(
                            get_bit(npqa, 4) &
                            get_bit(npqa, 6) |
                            get_bit(npqa, 8)
                        )

                        # We already have an implicit dependency on scipy (from
                        # Py6S), but life might be more simple if we just move
                        # the whole cloudmask extraction into gippy.
                        from scipy import ndimage
                        np_cloudmask_erroded = ndimage.binary_erosion(
                            np_cloudmask,
                            structure=numpy.ones((10, 10), dtype=numpy.uint8),
                        )

                        imgout = gippy.GeoImage.create_from(img, fname, 1, 'byte')
                        verbose_out("writing " + fname, 2)
                        imgout.set_bandname(
                                self._products[val[0]]['bands'][0]['name'], 1)
                        imgout.add_meta('GIPS_LANDSAT_VERSION', self.version)
                        imgout[0].set_nodata(0.)
                        imgout[0].write(
                            np_cloudmask_erroded.astype(numpy.uint8)
                        )
                    elif val[0] == 'rad':
                        imgout = gippy.GeoImage.create_from(img, fname, len(visbands), 'int16')
                        self.set_band_names(imgout, visbands)
                        imgout.set_nodata(-32768)
                        imgout.set_gain(0.1)
                        if toa:
                            for col in visbands:
                                img[col].save(imgout[col])
                        else:
                            for col in visbands:
                                ((img[col] - atm6s.results[col][1]) /
                                    atm6s.results[col][0]).save(imgout[col])
                        # Mask out any pixel for which any band is nodata
                        #imgout.ApplyMask(img.DataMask())
                    elif val[0] == 'ref':
                        imgout = gippy.GeoImage.create_from(img, fname, len(visbands), 'int16')
                        self.set_band_names(imgout, visbands)
                        imgout.set_nodata(-32768)
                        imgout.set_gain(0.0001)
                        if toa:
                            for c in visbands:
                                reflimg[c].save(imgout[c])
                        else:
                            for c in visbands:
                                (((img[c] - atm6s.results[c][1]) / atm6s.results[c][0])
                                        * (1.0 / atm6s.results[c][2])).save(imgout[c])
                        # Mask out any pixel for which any band is nodata
                        #imgout.ApplyMask(img.DataMask())
                    elif val[0] == 'tcap':
                        raise NotImplmentedError('tcap is incompatible with gippy 1.0 (segfaults)')
                        tmpimg = gippy.GeoImage(reflimg)
                        tmpimg.select(['BLUE', 'GREEN', 'RED', 'NIR', 'SWIR1', 'SWIR2'])
                        arr = numpy.array(self.Asset._sensors[self.sensor_set[0]]['tcap']).astype('float32')
                        imgout = algorithms.linear_transform(tmpimg, fname, arr)
                        outbands = ['Brightness', 'Greenness', 'Wetness', 'TCT4', 'TCT5', 'TCT6']
                        self.set_band_names(imgout, outbands)
                    elif val[0] == 'temp':
                        imgout = gippy.GeoImage.create_from(img, fname, len(lwbands), 'int16')
                        self.set_band_names(imgout, lwbands)
                        imgout.set_nodata(-32768)
                        imgout.set_gain(0.1)
                        [reflimg[col].save(imgout[col]) for col in lwbands]
                    elif val[0] == 'dn':
                        rawimg = self._readraw()
                        rawimg.set_gain(1.0)
                        rawimg.set_offset(0.0)
                        imgout = rawimg.save(fname)
                        rawimg = None
                    elif val[0] == 'volref':
                        bands = deepcopy(visbands)
                        bands.remove("SWIR1")
                        imgout = gippy.GeoImage.create_from(reflimg, fname, len(bands), 'int16')
                        [imgout.set_bandname(band, i + 1) for i, band in enumerate(bands)]
                        imgout.set_nodata(-32768)
                        imgout.set_gain(0.0001)
                        r = 0.54    # Water-air reflection
                        p = 0.03    # Internal Fresnel reflectance
                        pp = 0.54   # Water-air Fresnel reflectance
                        n = 1.34    # Refractive index of water
                        Q = 1.0     # Downwelled irradiance / upwelled radiance
                        A = ((1 - p) * (1 - pp)) / (n * n)
                        srband = reflimg['SWIR1'].read()
                        nodatainds = srband == reflimg['SWIR1'].nodata()
                        for band in bands:
                            bimg = reflimg[band].read()
                            diffimg = bimg - srband
                            diffimg = diffimg / (A + r * Q * diffimg)
                            diffimg[bimg == reflimg[band].nodata()] = imgout[band].nodata()
                            diffimg[nodatainds] = imgout[band].nodata()
                            imgout[band].write(diffimg)
                    elif val[0] == 'wtemp':
                        imgout = gippy.GeoImage.create_from(img, fname, len(lwbands), 'int16')
                        self.set_band_names(imgout, lwbands)
                        imgout.set_nodata(-32768)
                        imgout.set_gain(0.1)
                        tmpimg = gippy.GeoImage(img)
                        for col in lwbands:
                            band = tmpimg[col]
                            m = meta[col]
                            lat = self.metadata['geometry']['lat']
                            lon = self.metadata['geometry']['lon']
                            dt = self.metadata['datetime']
                            atmos = MODTRAN(m['bandnum'], m['wvlen1'], m['wvlen2'], dt, lat, lon, True)
                            e = 0.95
                            band = (tmpimg[col] - (atmos.output[1] + (1 - e) * atmos.output[2])
                                    ) / (atmos.output[0] * e)
                            band = (((band.pow(-1)) * meta[col]['K1'] + 1).log().pow(-1)
                                    ) * meta[col]['K2'] - 273.15
                            band.save(imgout[col])

                    elif val[0] == 'bqa':
                        if 'LC8' not in self.sensor_set:
                            verbose_out('LC8 not in sensor set, skipping bqa product', 1)
                            continue
                        # at least one issue, which is a NameError
                        raise NotImplementedError("bqa product is currently not functioning")
                        imgout = gippy.GeoImage.create_from(fname, img, 7, 'int16')
                        qadata = self._readqa()
                        notfilled = ~binmask(qadata, 1)
                        notdropped = ~binmask(qadata, 2)
                        notterrain = ~binmask(qadata, 3)
                        notcirrus = ~binmask(qadata, 14) & binmask(qadata, 13)
                        notcloud = ~binmask(qadata, 16) & binmask(qadata, 15)
                        allgood = notfilled * notdropped * notterrain * notcirrus * notcloud
                        imgout[0].write(allgood.astype('int16'))
                        imgout[1].write(notfilled.astype('int16'))
                        imgout[2].write(notdropped.astype('int16'))
                        imgout[3].write(notterrain.astype('int16'))
                        imgout[4].write(notsnow.astype('int16'))
                        imgout[5].write(notcirrus.astype('int16'))
                        imgout[6].write(notcloud.astype('int16'))

                    elif val[0] == 'bqashadow':
                        if 'LC8' not in self.sensor_set:
                            continue
                        raise NotImplementedError("bqashadow is not supported for gippy 1.0;"
                                                  " gippy.algorithms.AddShadowMask doesn't exist")
                        imgout = gippy.GeoImage.create_from(img, fname, 1, 'uint16')
                        imgout[0].set_nodata(0)
                        qadata = self._readqa()
                        fill = binmask(qadata, 1)
                        dropped = binmask(qadata, 2)
                        terrain = binmask(qadata, 3)
                        cirrus = binmask(qadata, 14)
                        othercloud = binmask(qadata, 16)
                        cloud = (cirrus + othercloud) + 2 * (fill + dropped + terrain)
                        abfn = fname + '-intermediate'
                        abimg = gippy.GeoImage.create_from(img, abfn, 1, 'uint16')
                        abimg[0].set_nodata(2)
                        abimg[0].write(cloud.astype(numpy.uint16))
                        abimg.save()
                        abimg = None
                        abimg = gippy.GeoImage(abfn + '.tif')
                        s_azim = self.metadata['geometry']['solarazimuth']
                        s_elev = 90 - self.metadata['geometry']['solarzenith']
                        erosion, dilation, cloudheight = 5, 10, 4000
                        if len(val) >= 4:
                            erosion, dilation, cloudheight = [int(v) for v in val[1:4]]
                        imgout = AddShadowMask(
                            abimg, imgout, 0, s_elev, s_azim, erosion,
                            dilation, cloudheight, {'notes': 'dev-version'}
                        )
                        imgout.save()
                        abimg = None
                        os.remove(abfn + '.tif')
                    fname = imgout.filename()
                    imgout.add_meta(md)
                    imgout = None
                    archive_fp = self.archive_temp_path(fname)
                    self.AddFile(sensor, key, archive_fp)
                    product_finished_msg = ' -> {}: processed in {}'.format(
                            os.path.basename(archive_fp), datetime.now() - start)
                    utils.verbose_out(product_finished_msg, level=2)

            # Process Indices (this is in the 'DN' block)
            indices0 = dict(groups['Index'], **groups['Tillage'])
            if len(indices0) > 0:
                start = datetime.now()
                indices = {}
                indices_toa = {}
                for key, val in indices0.items():
                    if 'toa' in val:
                        indices_toa[key] = val
                    else:
                        indices[key] = val
                # Run TOA
                if len(indices_toa) > 0:
                    self._process_indices(reflimg, md, sensor, indices_toa)

                # Run atmospherically corrected
                if len(indices) > 0:
                    for col in visbands:
                        img[col] = ((img[col] - atm6s.results[col][1]) / atm6s.results[col][0]
                                ) * (1.0 / atm6s.results[col][2])
                    self._process_indices(img, md, sensor, indices)
                verbose_out(' -> %s: processed %s in %s' % (
                        self.basename, indices0.keys(), datetime.now() - start), 1)
            img = None
            # cleanup scene directory by removing (most) extracted files
            with utils.error_handler('Error removing extracted files', continuable=True):
                if settings().REPOS[self.Repository.name.lower()]['extract']:
                    for bname in self.assets[asset].datafiles():
                        if bname[-7:] != 'MTL.txt':
                            files = glob.glob(os.path.join(self.path, bname) + '*')
                            RemoveFiles(files)
                # TODO only wtemp uses MODTRAN; do the dir removal there?
                modtran_path = os.path.join(self.path, 'modtran')
                if os.path.exists(modtran_path):
                    shutil.rmtree(modtran_path)

            if groups['ACOLITE']:
                start = datetime.now()
                # TEMPDIR FOR PROCESSING
                aco_proc_dir = tempfile.mkdtemp(
                    prefix='aco_proc_',
                    dir=os.path.join(self.Repository.path(), 'stage')
                )
                with utils.error_handler(
                        'Error creating ACOLITE products {} for {}'
                        .format(
                            groups['ACOLITE'].keys(),
                            basename(self.assets[asset].filename)
                        ),
                        continuable=True):
                    # amd is 'meta' (common to all products) and product info dicts
                    amd = {
                        'meta': md.copy()
                    }
                    for p in groups['ACOLITE']:
                        amd[p] = {
                            'fname': os.path.join(
                                self.path, self.basename + '_' + p + '.tif'
                            )
                        }
                        amd[p].update(self._products[p])
                        amd[p].pop('assets')
                    prodout = gips.atmosphere.process_acolite(
                            self.assets[asset], aco_proc_dir, amd)
                    endtime = datetime.now()
                    for k, fn in prodout.items():
                        self.AddFile(sensor, k, fn)
                    verbose_out(
                        ' -> {}: processed {} in {}'
                        .format(self.basename, prodout.keys(), endtime - start),
                        1
                    )
                shutil.rmtree(aco_proc_dir)
                ## end ACOLITE
        verbose_out('finished landsat processing!', 3)

    def filter(self, pclouds=100, sensors=None, **kwargs):
        """Check if Data object passes filter.

        User can't enter pclouds, but can pass in --sensors.  kwargs
        isn't used.
        """
        if pclouds < 100:
            self.meta()
            if self.metadata['clouds'] > pclouds:
                return False
        if sensors:
            if type(sensors) is str:
                sensors = [sensors]
            sensors = set(sensors)
            # ideally, the data class would be trimmed by
            if not sensors.intersection(self.sensor_set):
                return False
        return True

    def meta(self):
        """ Read in Landsat MTL (metadata) file """

        # test if metadata already read in, if so, return # TODO that's not what this does tho?
        if 'C1' in self.assets.keys():
            asset = 'C1'
        elif 'DN' in self.assets.keys():
            asset = 'DN'
        else:
            raise ValueError("neither C1 nor DN found in asset types for this scene: {}".format(
                    self.assets.keys()))

        datafiles = self.assets[asset].datafiles()

        # locate MTL file and save it to disk if it isn't saved already
        mtlfilename = [f for f in datafiles if 'MTL.txt' in f][0]
        if os.path.exists(mtlfilename) and os.stat(mtlfilename).st_size == 0:
            os.remove(mtlfilename)
        if not os.path.exists(mtlfilename):
            mtlfilename = self.assets[asset].extract([mtlfilename])[0]
        # Read MTL file
        with utils.error_handler('Error reading metadata file ' + mtlfilename):
            text = open(mtlfilename, 'r').read()
        if len(text) < 10:
            raise Exception('MTL file is too short. {}'.format(mtlfilename))

        sensor = self.assets[asset].sensor
        smeta = self.assets[asset]._sensors[sensor]

        # Process MTL text - replace old metadata tags with new
        # NOTE This is not comprehensive, there may be others
        text = text.replace('ACQUISITION_DATE', 'DATE_ACQUIRED')
        text = text.replace('SCENE_CENTER_SCAN_TIME', 'SCENE_CENTER_TIME')

        for (ob, nb) in zip(smeta['oldbands'], smeta['bands']):
            text = re.sub(r'\WLMIN_BAND' + ob, 'RADIANCE_MINIMUM_BAND_' + nb, text)
            text = re.sub(r'\WLMAX_BAND' + ob, 'RADIANCE_MAXIMUM_BAND_' + nb, text)
            text = re.sub(r'\WQCALMIN_BAND' + ob, 'QUANTIZE_CAL_MIN_BAND_' + nb, text)
            text = re.sub(r'\WQCALMAX_BAND' + ob, 'QUANTIZE_CAL_MAX_BAND_' + nb, text)
            text = re.sub(r'\WBAND' + ob + '_FILE_NAME', 'FILE_NAME_BAND_' + nb, text)
        for l in ('LAT', 'LON', 'MAPX', 'MAPY'):
            for c in ('UL', 'UR', 'LL', 'LR'):
                text = text.replace('PRODUCT_' + c + '_CORNER_' + l, 'CORNER_' + c + '_' + l + '_PRODUCT')
        text = text.replace('\x00', '')
        # Remove junk
        lines = text.split('\n')
        mtl = dict()
        for l in lines:
            meta = l.replace('\"', "").strip().split('=')
            if len(meta) > 1:
                key = meta[0].strip()
                item = meta[1].strip()
                if key != "GROUP" and key != "END_GROUP":
                    mtl[key] = item

        # Extract useful metadata
        lats = (float(mtl['CORNER_UL_LAT_PRODUCT']), float(mtl['CORNER_UR_LAT_PRODUCT']),
                float(mtl['CORNER_LL_LAT_PRODUCT']), float(mtl['CORNER_LR_LAT_PRODUCT']))
        lons = (float(mtl['CORNER_UL_LON_PRODUCT']), float(mtl['CORNER_UR_LON_PRODUCT']),
                float(mtl['CORNER_LL_LON_PRODUCT']), float(mtl['CORNER_LR_LON_PRODUCT']))
        lat = (min(lats) + max(lats)) / 2.0
        lon = (min(lons) + max(lons)) / 2.0
        dt = datetime.strptime(mtl['DATE_ACQUIRED'] + ' ' + mtl['SCENE_CENTER_TIME'][:-2], '%Y-%m-%d %H:%M:%S.%f')
        clouds = 0.0
        with utils.error_handler('Error reading CLOUD_COVER metadata', continuable=True):
            # CLOUD_COVER isn't trusted for unknown reasons; previously errors were silenced, but
            # now maybe explicit error reports will reveal something.
            clouds = float(mtl['CLOUD_COVER'])

        filenames = []
        gain = []
        offset = []
        dynrange = []
        for i, b in enumerate(smeta['bands']):
            minval = int(float(mtl['QUANTIZE_CAL_MIN_BAND_' + b]))
            maxval = int(float(mtl['QUANTIZE_CAL_MAX_BAND_' + b]))
            minrad = float(mtl['RADIANCE_MINIMUM_BAND_' + b])
            maxrad = float(mtl['RADIANCE_MAXIMUM_BAND_' + b])
            gain.append((maxrad - minrad) / (maxval - minval))
            offset.append(minrad)
            dynrange.append((minval, maxval))
            filenames.append(mtl['FILE_NAME_BAND_' + b].strip('\"'))

        _geometry = {
            'solarzenith': (90.0 - float(mtl['SUN_ELEVATION'])),
            'solarazimuth': float(mtl['SUN_AZIMUTH']),
            'zenith': 0.0,
            'azimuth': 180.0,
            'lat': lat,
            'lon': lon,
        }

        self.metadata = {
            'filenames': filenames,
            'gain': gain,
            'offset': offset,
            'dynrange': dynrange,
            'geometry': _geometry,
            'datetime': dt,
            'clouds': clouds,
            'qafilename': next((f for f in datafiles if '_BQA.TIF' in f), None) # defaults to None
        }
        #self.metadata.update(smeta)

    @classmethod
    def meta_dict(cls):
        meta = super(landsatData, cls).meta_dict()
        meta['GIPS-landsat Version'] = cls.version
        return meta

    def _readqa(self):
        """Returns a numpy array of the first landsat asset in self.assets."""
        asset = self.assets.keys()[0]

        # make sure metadata is loaded
        if not hasattr(self, 'metadata'):
            self.meta()
        if settings().REPOS[self.Repository.name.lower()]['extract']:
            # Extract files
            qadatafile = self.assets[asset].extract([self.metadata['qafilename']])
        else:
            # Use tar.gz directly using GDAL's virtual filesystem
            qadatafile = os.path.join('/vsitar/' + self.assets[asset].filename,
                                      self.metadata['qafilename'])
        # read() does automatic conversion to float64; read_raw() doesn't
        npqa = gippy.GeoImage(qadatafile)[0].read_raw()
        return npqa

    def _readraw(self):
        """ Read in Landsat bands using original tar.gz file """
        start = datetime.now()
        asset = self.assets.keys()[0]

        # make sure metadata is loaded
        if not hasattr(self, 'metadata'):
            self.meta()

        if settings().REPOS[self.Repository.name.lower()]['extract']:
            # Extract all files
            datafiles = self.assets[asset].extract(self.metadata['filenames'])
        else:
            # Use tar.gz directly using GDAL's virtual filesystem
            datafiles = [os.path.join('/vsitar/' + self.assets[asset].filename, f)
                    for f in self.metadata['filenames']]

        image = gippy.GeoImage(datafiles)
        image.set_nodata(0)

        # TODO - set appropriate metadata
        #for key,val in meta.iteritems():
        #    image.SetMeta(key,str(val))

        # Geometry used for calculating incident irradiance
        # colors = self.assets['DN']._sensors[self.sensor_set[0]]['colors']

        sensor = self.assets[asset].sensor
        colors = self.assets[asset]._sensors[sensor]['colors']

        for bi in range(0, len(self.metadata['filenames'])):
            image.set_bandname(colors[bi], bi + 1)
            # need to do this or can we index correctly?
            band = image[bi]
            gain = self.metadata['gain'][bi]
            band.set_gain(gain)
            band.set_offset(self.metadata['offset'][bi])
            dynrange = self.metadata['dynrange'][bi]
            # #band.SetDynamicRange(dynrange[0], dynrange[1])
            # dynrange[0] was used internally to for conversion to radiance
            # from DN in GeoRaster.Read:
            #   img = Gain() * (img-_minDC) + Offset();  # (1)
            # and with the removal of _minDC and _maxDC it is now:
            #   img = Gain() * img + Offset();           # (2)
            # And 1 can be re-written as:
            #   img = Gain() * img - Gain() *
            #                       _minDC + Offset();   # (3)
            #       = Gain() * img + Offset
            #                      - _min * Gain() ;     # (4)
            # So, since the gippy now has line (2), we can add
            # the final term of (4) [as below] to keep that functionality.
            image[bi] = band - dynrange[0] * gain
            # I verified this by example.  With old gippy.GeoRaster:
            #     In [8]: a.min()
            #     Out[8]: -64.927711
            # with new version.
            #     In [20]: ascale.min() - 1*0.01298554277169103
            #     Out[20]: -64.927711800095906


        verbose_out('%s: read in %s' % (image.basename(), datetime.now() - start), 2)
        return image
