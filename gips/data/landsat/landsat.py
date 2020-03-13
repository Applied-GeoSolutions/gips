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

from contextlib import contextmanager
import sys
import os
import re
from datetime import datetime, date, timedelta
import shutil
import glob
import traceback
from copy import deepcopy
import subprocess
import tempfile
import tarfile
import json
from xml.etree import ElementTree

from backports.functools_lru_cache import lru_cache
import numpy
# TODO: now that gippy==1.0, switch to GeoRaster.erode
from scipy.ndimage import binary_dilation

import osr
import gippy
from gippy import algorithms
from gips import __version__ as __gips_version__
from gips.exceptions import GipsException
from gips.core import SpatialExtent, TemporalExtent
from gips.data.core import Repository, Data
import gips.data.core
from gips.atmosphere import SIXS, MODTRAN
import gips.atmosphere
from gips.inventory import DataInventory
from gips.utils import RemoveFiles, basename, settings, verbose_out
from gips import utils

import geojson
import fiona
from fiona.crs import from_epsg
from shapely.geometry import Polygon
from shapely.wkt import loads as wkt_loads
import requests
import homura


requirements = ['Py6S>=1.5.0']

_default_coreg_mag_thresh = 75

def path_row(tile_id):
    """Converts the given landsat tile string into (path, row)."""
    return (tile_id[:3], tile_id[3:])

def binmask(arr, bit):
    """ Return boolean array indicating which elements as binary have a 1 in
        a specified bit position. Input is Numpy array.
    """
    return arr & (1 << (bit - 1)) == (1 << (bit - 1))


class NoBasemapError(Exception):
    pass

class CantAlignError(GipsException):
    # TODO: to make the gips exit status informative about various exception
    # types, there should be a base GipsException class which handles
    # registration of exception types, to prevent conflicts.  For now, this is
    # the only class providing this feature.
    COREG_FAIL, INSUFFICIENT_CP, EXCESSIVE_SHIFT = range(13,16)
    code_map = dict(zip(
        range(13,16),
        ['COREG_FAIL', 'INSUFFICIENT_CP', 'EXCESSIVE_SHIFT']
    ))
    def __init__(self, message, exc_code=None):
        super(CantAlignError, self).__init__(message, exc_code)
        if exc_code not in self.code_map:
            message += ' [orig exc_code was {}]'.format(exc_code)
            exc_code = 1
        self.exc_code = exc_code

class CoregTimeout(GipsException):
    exc_code = 124  # c.f. coreutils timeout command


class landsatRepository(Repository):
    """ Singleton (all class methods) to be overridden by child data classes """
    name = 'Landsat'
    description = 'Landsat 5 (TM), 7 (ETM+), 8 (OLI)'
    _tile_attribute = 'PR'

    default_settings = {
        'source': 'usgs',
        'asset-preference': ('C1', 'C1S3', 'C1GS', 'DN'),
    }

    @classmethod
    def feature2tile(cls, feature):
        tile = super(landsatRepository, cls).feature2tile(feature)
        return tile.zfill(6)


class landsatAsset(gips.data.core.CloudCoverAsset,
                   gips.data.core.GoogleStorageMixin,
                   gips.data.core.S3Mixin):
    """ Landsat asset (original raw tar file) """
    Repository = landsatRepository

    gs_bucket_name = 'gcp-public-data-landsat'

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
            'code': 'LT05',
            'description': 'Landsat 5',
            'ee_dataset': 'LANDSAT_TM_C1',
            'startdate': date(1984, 3, 1),
            'enddate': date(2013, 1, 1),
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
            'code': 'LE07',
            'description': 'Landsat 7',
            'ee_dataset': 'LANDSAT_EMT_C1',
            'startdate': date(1999, 4, 15),
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
            'code': 'LC08',
            'description': 'Landsat 8',
            'ee_dataset': 'LANDSAT_8_C1',
            'startdate': date(2013, 4, 1),
            # as normal for Landsat 8 but with panchromatic band left out, CF:
            # https://landsat.usgs.gov/what-are-band-designations-landsat-satellites
            'bands': ['1', '2', '3', '4', '5', '6', '7', '9', '10', '11'],
            'oldbands': ['1', '2', '3', '4', '5', '6', '7', '9', '10', '11'],
            'colors': ("COASTAL", "BLUE", "GREEN", "RED", "NIR",
                       "SWIR1", "SWIR2", "CIRRUS", "LWIR", "LWIR2"),
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
            'startdate': date(2013, 4, 1),
        }
    }

    # filename minus extension so that C1 & C1S3 both use the same pattern
    # example:  LC08_L1TP_013030_20151225_20170224_01_T1
    _c1_base_pattern = (
        r'^L(?P<sensor>\w)(?P<satellite>\d{2})_'
        r'(?P<correction_level>.{4})_(?P<pathrow>\d{6})_(?P<acq_date>\d{8})_'
        r'(?P<processing_date>\d{8})_'
        r'(?P<coll_num>\d{2})_(?P<coll_cat>.{2})')

    cloud_storage_a_types = ('C1S3', 'C1GS') # in order of current preference
    _assets = {
        # DN & SR assets are no longer fetchable
        'DN': {
            'fetchable': False,
            'sensors': ['LT5', 'LE7', 'LC8'],
            'enddate': date(2017, 4, 30),
            'pattern': (
                r'^L(?P<sensor>[A-Z])(?P<satellite>\d)'
                r'(?P<pathrow>\d{6})(?P<acq_date>\d{7})'
                r'(?P<gsi>[A-Z]{3})(?P<version>\d{2})\.tar\.gz$'
            ),
        },
        'SR': {
            'fetchable': False,
            'sensors': ['LC8SR'],
            'enddate': date(2017, 4, 30),
            'pattern': r'^L.*?-SC.*?\.tar\.gz$',
        },

        # landsat setting 'source' decides what is downloaded according to 'source' here:
        'C1': {
            'sensors': ['LT5', 'LE7', 'LC8'],
            'pattern': _c1_base_pattern + r'\.tar\.gz$',
            'latency': 0,
            'source': 'usgs',
        },
        'C1S3': {
            'sensors': ['LC8'],
            'pattern': _c1_base_pattern + r'_S3\.json$',
            'latency': 0,
            'source': 's3',
        },
        'C1GS': {
            'sensors': ['LT5', 'LE7', 'LC8'],
            'pattern': _c1_base_pattern + r'_gs\.json$',
            'latency': 12,
            'source': 'gs',
        },
    }

    # Field ids are retrieved with `api.dataset_fields()` call
    _ee_datasets = None

    # Set the startdate to the min date of the asset's sensors
    for asset, asset_info in _assets.items():

        # TODO: there was some weird scope thing going on in the
        # list comprehension that was here
        startdates = []
        for sensor in asset_info['sensors']:
            startdates.append(_sensors[sensor]['startdate'])
        asset_info['startdate'] = min(startdates)

    _defaultresolution = [30.0, 30.0]

    def __init__(self, filename):
        """ Inspect a single file and get some metadata """
        super(landsatAsset, self).__init__(filename)

        fname = os.path.basename(filename)

        verbose_out("Attempting to load " + fname, 2)

        # determine asset type
        match = None
        for at, ad in self._assets.items():
            match = re.match(ad['pattern'], fname)
            if match:
                break
        if match is None:
            raise RuntimeError(
                "No valid landsat asset type for '{}'".format(fname), filename)
        self.asset = at

        # set attribs according to asset type
        if at == 'SR':
            self.sensor = 'LC8SR'
            self.tile = fname[3:9]
            self.date = datetime.strptime(fname[9:16], "%Y%j")
            self.version = int(fname[20:22])
        elif at == 'DN':
            self.sensor = fname[0:3]
            self.date = datetime.strptime(match.group('acq_date'), "%Y%j")
            self.version = int(fname[19:21])
        else: # C1 flavors
            self.sensor = "L{}{}".format(match.group('sensor'),
                                         int(match.group('satellite')))
            self.date = datetime.strptime(match.group('acq_date'), "%Y%m%d")
            self.collection_number = match.group('coll_num')
            self.collection_category = match.group('coll_cat')
            processing_date = datetime.strptime(match.group('processing_date'),
                                                '%Y%m%d')
            self.version = 1e6 * int(self.collection_number) + \
                    (processing_date - datetime(2017, 1, 1)).days + \
                    {'RT': 0, 'T2': 0.5, 'T1': 0.9}[self.collection_category]

        if self.asset != 'SR':
            self.tile = match.group('pathrow')
            smeta = self._sensors[self.sensor]
            self.meta = {}
            self.meta['bands'] = {}
            for i, band in enumerate(smeta['colors']):
                wvlen = smeta['bandlocs'][i]
                self.meta['bands'][band] = {
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
        self._version = self.version

    def band_paths(self):
        if not self.in_cloud_storage():
            raise NotImplementedError(
                'porting local files to this method is a TODO')
        return self.load_c1_json()[{'C1S3': '30m-bands', 'C1GS': 'spectral-bands'}[self.asset]]

    @classmethod
    def cloud_cover_from_mtl_text(cls, text):
        """Reads the text and returns the cloud cover percentage."""
        cc_pattern = r".*CLOUD_COVER = (\d+.?\d*)"
        cloud_cover = re.match(cc_pattern, text, flags=re.DOTALL)
        if not cloud_cover:
            raise ValueError("No match for '{}' found in MTL text".format(
                cc_pattern))
        return float(cloud_cover.group(1))

    def cloud_cover(self):
        """Returns the cloud cover for the current asset.

        Caches and returns the value found in self.meta['cloud-cover']."""
        if 'cloud-cover' in self.meta:
            return self.meta['cloud-cover']
        # first attempt to find or download an MTL file and get the CC value
        text = None
        if self.in_cloud_storage():
            if os.path.exists(self.filename):
                c1json_content = self.load_c1_json()
                utils.verbose_out('requesting ' + c1json_content['mtl'], 4)
                text = self.gs_backoff_get(c1json_content['mtl']).text
            else:
                query_results = self.query_gs(self.tile, self.date)
                if query_results is None:
                    raise IOError('Could not locate metadata for'
                                  ' ({}, {})'.format(self.tile, self.date))
                url = self.gs_object_url_base() + query_results['keys']['mtl']
                utils.verbose_out('requesting ' + url, 4)
                text = self.gs_backoff_get(url).text
        elif os.path.exists(self.filename):
            mtlfilename = self.extract(
                [f for f in self.datafiles() if f.endswith('MTL.txt')]
            )[0]
            err_msg = 'Error reading metadata file ' + mtlfilename
            with utils.error_handler(err_msg):
                with open(mtlfilename, 'r') as mtlfile:
                    text = mtlfile.read()

        if text is not None:
            self.meta['cloud-cover'] = self.cloud_cover_from_mtl_text(text)
            return self.meta['cloud-cover']

        # the MTL file didn't work out; attempt USGS API search instead
        api_key = self.ee_login()
        self.load_ee_search_keys()
        dataset_name = self._sensors[self.sensor]['ee_dataset']
        path_field   = self._ee_datasets[dataset_name]['WRS Path']
        row_field    = self._ee_datasets[dataset_name]['WRS Row']
        date_string = datetime.strftime(self.date, "%Y-%m-%d")
        from usgs import api
        response = api.search(
                dataset_name, 'EE',
                where={path_field: self.tile[0:3], row_field: self.tile[3:]},
                start_date=date_string, end_date=date_string, api_key=api_key)
        metadata = requests.get(
                response['data']['results'][0]['metadataUrl']).text
        xml = ElementTree.fromstring(metadata)
        xml_magic_string = (".//{http://earthexplorer.usgs.gov/eemetadata.xsd}"
                            "metadataField[@name='Scene Cloud Cover']")
        # Indexing an Element instance returns its children
        self.meta['cloud-cover'] = float(xml.find(xml_magic_string)[0].text)
        return self.meta['cloud-cover']

    def load_c1_json(self):
        """Load the content from a C1 json asset and return it."""
        if not self.in_cloud_storage():
            return None
        with open(self.filename) as aof:
            return json.load(aof)

    @classmethod
    def ee_login(cls):
        if not hasattr(cls, '_ee_key'):
            username = settings().REPOS['landsat']['username']
            password = settings().REPOS['landsat']['password']
            from usgs import api
            cls._ee_key = api.login(username, password)['data']
        return cls._ee_key

    @classmethod
    def load_ee_search_keys(cls):
        if cls._ee_datasets:
            return
        api_key = cls.ee_login()
        from usgs import api
        cls._ee_datasets = {
            ds: {
                r['name']: r['fieldId']
                for r in api.dataset_fields(ds, 'EE', api_key)['data']
                if r['name'] in [u'WRS Path', u'WRS Row']
            }
            for ds in ['LANDSAT_8_C1', 'LANDSAT_ETM_C1', 'LANDSAT_TM_C1']
        }

    _s3_bucket_name = 'landsat-pds'
    _s3_url = 'https://landsat-pds.s3.amazonaws.com/'

    @classmethod
    def query_s3(cls, tile, date, pclouds=100):
        """Handles AWS S3 queries for landsat data.

        Returns a filename suitable for naming the constructed asset,
        and a list of S3 keys.  Returns None if no asset found for the
        given scene.  Filters by the given cloud percentage.
        """

        import boto3

        # for finding assets matching the tile
        key_prefix = 'c1/L8/{}/{}/'.format(*path_row(tile))
        # match something like:  'LC08_L1TP_013030_20170402_20170414_01_T1'
        # filters for date and also tier
        # TODO all things not just T1 ----------------vv
        fname_fragment = r'L..._...._{}_{}_\d{{8}}_.._T1'.format(
                tile, date.strftime('%Y%m%d'))
        re_string = key_prefix + fname_fragment
        filter_re = re.compile(re_string)

        keys = cls.s3_prefix_search(key_prefix)

        _30m_tifs = []
        _15m_tif = mtl_txt = qa_tif = None
        for key in keys:
            if not filter_re.match(key):
                continue
            if key.endswith('B8.TIF'):
                _15m_tif = key
            elif key.endswith('MTL.txt'):
                mtl_txt = key
            elif key.endswith('BQA.TIF'):
                qa_tif = key
            elif key.endswith('.TIF'):
                _30m_tifs.append(key)

        if len(_30m_tifs) != 10 or None in (_15m_tif, mtl_txt, qa_tif):
            verbose_out('Found no complete S3 asset for'
                        ' (C1S3, {}, {})'.format(tile, date), 4)
            return None

        if pclouds < 100:
            mtl_content = requests.get(cls._s3_url + mtl_txt).text
            cc = cls.cloud_cover_from_mtl_text(mtl_content)
            if cc > pclouds:
                cc_msg = ('C1S3 asset found for ({}, {}), but cloud cover'
                          ' percentage ({} %) fails to meet threshold ({} %)')
                verbose_out(cc_msg.format(tile, date, cc, pclouds), 3)
                return None
            else:
                cc_msg = ('C1S3 asset found for ({}, {}); cloud cover'
                          ' percentage ({} %) meets threshold ({} %)')
                verbose_out(cc_msg.format(tile, date, cc, pclouds), 3)
        else:
            verbose_out('Found complete C1S3 asset for'
                        ' ({}, {})'.format(tile, date), 3)

        # have to custom sort thanks to 'B1.TIF' instead of 'B01.TIF':
        def sort_key_f(key):
            match = re.search(r'B(\d+).TIF$', key)
            # sort by band number; anything weird goes last
            return int(match.group(1)) if match else 99
        _30m_tifs.sort(key=sort_key_f)

        filename = re.search(fname_fragment, _15m_tif).group(0) + '_S3.json'
        verbose_out("Constructed S3 asset filename:  " + filename, 5)
        return {'basename': filename,
                '_30m_tifs': _30m_tifs, '_15m_tif': _15m_tif,
                'qa_tif': qa_tif, 'mtl_txt': mtl_txt}

    @classmethod
    def gs_prefix_search(cls, tile, acq_date):
        """Locates the best prefix for the given arguments.

        Docs:  https://cloud.google.com/storage/docs/json_api/v1/objects/list
        """
        # we identify a sensor as eg 'LC8' but in the filename it's 'LC08';
        # prefer the latest sensor that has data for the scene
        sensors = reversed([s for s in cls._assets['C1GS']['sensors']])
        ads = acq_date.strftime('%Y%m%d')
        path, row = path_row(tile)

        # sample full key (highly redundant, unfortunately):
        # we're searching up to here ---------------v
        # ('LC08/01/044/034/LC08_L1GT_044034_20130330_20170310_01_T2/
        #                       'LC08_L1GT_044034_20130330_20170310_01_T2_MTL.txt')
        p_template = '{{}}/01/{}/{}/{{}}_{{}}_{}_{}_'.format(path, row, tile, ads)

        for s in sensors:
            c = cls._sensors[s]['code']
            # find best correction level in desc order of preference
            for cl in ('L1TP', 'L1GT', 'L1GS'):
                search_prefix = p_template.format(c, c, cl)
                full_prefixes = cls.gs_api_search(search_prefix).get('prefixes', [])
                for t in ('T1', 'T2', 'RT'):  # get best C1 tier available
                    for p in full_prefixes:
                        if p.endswith(t + '/'):
                            return s, p
        return None, None

    @classmethod
    def query_gs(cls, tile, date, pclouds=100):
        """Query for assets in google cloud storage.

        Returns {'basename': '...', 'urls': [...]}, else None.
        """
        sensor, prefix = cls.gs_prefix_search(tile, date)
        if prefix is None:
            return None
        raw_keys = [i['name'] for i in cls.gs_api_search(prefix)['items']]

        # sort and organize the URLs, and check for missing ones
        keys = {'spectral-bands': []}
        missing_suffixes = []
        band_suffixes = ['B{}.TIF'.format(b)
                         for b in cls._sensors[sensor]['bands']]
        for bs in band_suffixes:
            try:
                keys['spectral-bands'].append(
                    next(u for u in raw_keys if u.endswith(bs)))
            except StopIteration:
                missing_suffixes.append(bs)
        for k, s in [('mtl', 'MTL.txt'), ('qa-band', 'BQA.TIF')]:
            try:
                keys[k] = next(u for u in raw_keys if u.endswith(s))
            except StopIteration:
                missing_suffixes.append(s)

        # sanity check that we have all the band keys & metatadata key
        if missing_suffixes:
            err_msg = ("Found GS asset wasn't complete for (C1GS, {}, {});"
                       " missing files with these suffixes: {}")
            verbose_out(err_msg.format(tile, date, missing_suffixes), 2)
            return None

        # handle pclouds
        if pclouds < 100:
            r = cls.gs_backoff_get(cls.gs_object_url_base() + keys['mtl'])
            cc = cls.cloud_cover_from_mtl_text(r.text)
            if cc > pclouds:
                cc_msg = ('C1GS asset found for ({}, {}), but cloud cover'
                          ' percentage ({}%) fails to meet threshold ({}%)')
                verbose_out(cc_msg.format(tile, date, cc, pclouds), 3)
                return None

        verbose_out('Found complete C1GS asset for'
                    ' ({}, {})'.format(tile, date), 3)
        return dict(basename=(prefix.split('/')[-2] + '_gs.json'), keys=keys)

    @classmethod
    def query_c1(cls, tile, date, pcover):
        """Query for C1 assets by incquiring of the USGS API"""
        path, row = path_row(tile)
        fdate = date.strftime('%Y-%m-%d')
        cls.load_ee_search_keys()
        api_key = cls.ee_login()
        from usgs import api
        for dataset in cls._ee_datasets.keys():
            response = api.search(
                dataset, 'EE',
                start_date=fdate, end_date=fdate,
                where={
                    cls._ee_datasets[dataset]['WRS Path']: path,
                    cls._ee_datasets[dataset]['WRS Row']: row,
                },
                api_key=api_key
            )['data']

            for result in response['results']:
                metadata = requests.get(result['metadataUrl']).text
                xml = ElementTree.fromstring(metadata)
                # Indexing an Element instance returns it's children
                scene_cloud_cover = xml.find(
                    ".//{http://earthexplorer.usgs.gov/eemetadata.xsd}metadataField[@name='Scene Cloud Cover']"
                )[0].text
                land_cloud_cover = xml.find(
                    ".//{http://earthexplorer.usgs.gov/eemetadata.xsd}metadataField[@name='Land Cloud Cover']"
                )[0].text

                if float(scene_cloud_cover) < pcover:
                    return {
                        # actually used
                        'scene_id': result['entityId'],
                        'dataset': dataset,
                        # ignored but required
                        'basename': result['displayId'] + '.tar.gz',
                        # ignored
                        #'scene_cloud_cover': float(scene_cloud_cover),
                        #'land_cloud_cover': float(land_cloud_cover),
                    }
        return None

    @classmethod
    @lru_cache(maxsize=100) # cache size chosen arbitrarily
    def query_service(cls, asset, tile, date, pclouds=90.0, **ignored):
        """As superclass with optional argument:

        Finds assets matching the arguments, where pcover is maximum
        permitted cloud cover %.
        """
        # start with pre-query checks
        if not cls.available(asset, date):
            return None
        if asset in ['DN', 'SR']:
            verbose_out('Landsat "{}" assets are no longer fetchable'.format(
                    asset), 6)
            return None
        data_src = cls.get_setting('source')

        c1_sources = ('s3', 'usgs', 'gs')
        if data_src not in c1_sources:
            raise ValueError("Invalid data source '{}'; valid sources:"
                             " {}".format(data_src, c1_sources))
        # perform the query, but on a_type-source mismatch, do nothing
        rv = {
            ('C1', 'usgs'): cls.query_c1,
            ('C1S3', 's3'): cls.query_s3,
            ('C1GS', 'gs'): cls.query_gs,
        }.get((asset, data_src), lambda *_: None)(tile, date, pclouds)
        if rv is not None:
            rv['a_type'] = asset
        return rv

    @classmethod
    def download(cls, a_type, download_fp, **kwargs):
        """Downloads the asset defined by the kwargs to the full path."""
        methods = {'C1': cls.download_c1,
                   'C1S3': cls.download_s3,
                   'C1GS': cls.download_gs,
                   }
        if a_type not in methods:
            raise ValueError('Unfetchable asset type: {}'.format(asset))
        return methods[a_type](download_fp, **kwargs)

    @classmethod
    def download_c1(cls, download_fp, scene_id, dataset, **ignored):
        """Fetches the C1 asset defined by the arguments."""
        stage_dir = cls.Repository.path('stage')
        api_key = cls.ee_login()
        from usgs import api
        url = api.download(
            dataset, 'EE', [str(scene_id)], 'STANDARD', api_key)['data'][0]['url']
        with utils.make_temp_dir(prefix='dwnld', dir=stage_dir) as dldir:
            homura.download(url, dldir)
            granules = os.listdir(dldir)
            if len(granules) == 0:
                raise Exception("Download didn't seem to"
                                " produce a file:  {}".format(str(granules)))
            os.rename(os.path.join(dldir, granules[0]), download_fp)
        return True

    @classmethod
    def download_s3(cls, download_fp, _30m_tifs, _15m_tif, qa_tif, mtl_txt,
                    **ignored):
        """Fetches AWS S3 assets; currently only 'C1S3' assets.

        Doesn't fetch much; instead it constructs VRT-based json.
        """
        # construct VSI paths; sample (split into lines):
        # /vsis3_streaming/landsat-pds/c1/L8/013/030
        #   /LC08_L1TP_013030_20171128_20171207_01_T1
        #   /LC08_L1TP_013030_20171128_20171207_01_T1_B10.TIF
        # see also:  http://www.gdal.org/gdal_virtual_file_systems.html
        asset_content = {
            # can/should add metadata/versioning info here
            '30m-bands': [cls.s3_vsi_prefix(t) for t in _30m_tifs],
            '15m-band': cls.s3_vsi_prefix(_15m_tif),
            'qa-band': cls.s3_vsi_prefix(qa_tif),
            'mtl': cls._s3_url + mtl_txt,
        }
        utils.json_dump(asset_content, download_fp)
        return True

    @classmethod
    def download_gs(cls, download_fp, keys, **ignored):
        """Assembles C1 assets that link into Google Cloud Storage.

        Constructs a json file containing /vsicurl_streaming/ paths,
        similarly to S3 assets.
        """
        content = {
            'mtl':     cls.gs_object_url_base() + keys['mtl'],
            'qa-band': cls.gs_vsi_prefix() + keys['qa-band'],
            'spectral-bands': [cls.gs_vsi_prefix() + u
                               for u in keys['spectral-bands']],
        }
        utils.json_dump(content, download_fp)
        return True


def unitless_bands(*bands):
    return [{'name': b, 'units': Data._unitless} for b in bands]


class landsatData(gips.data.core.CloudCoverData):
    name = 'Landsat'
    version = '1.0.1'
    inline_archive = True

    Asset = landsatAsset

    _lt5_startdate = date(1984, 3, 1)
    _lc8_startdate = date(2013, 5, 30)

    # Group products belong to ('Standard' if not specified)
    _productgroups = {
        'Index': ['bi', 'evi', 'lswi', 'msavi2', 'ndsi', 'ndvi', 'ndwi',
                  'satvi', 'vari'],
        'Tillage': ['ndti', 'crc', 'sti', 'isti'],
        'LC8SR': ['ndvi8sr'],
        # 'rhoam',  # Dropped for the moment due to issues in ACOLITE
        'ACOLITE': ['rhow', 'oc2chl', 'oc3chl', 'fai',
                    'spm', 'spm2016', 'turbidity', 'acoflags'],
    }
    __toastring = 'toa: use top of the atmosphere reflectance'
    __visible_bands_union = [color for color in Asset._sensors['LC8']['colors'] if 'LWIR' not in color]

    # note C1 products can be made with multiple asset types; see below
    # TODO don't use manual tables of repeated information in the first place
    _products = {
        #'Standard':
        'rad': {
            'assets': ['DN', 'C1'],
            'description': 'Surface-leaving radiance',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 0,
            # units given by https://landsat.usgs.gov/landsat-8-l8-data-users-handbook-section-5
            'bands': [{'name': n, 'units': 'W/m^2/sr/um'} for n in __visible_bands_union],
        },
        'ref': {
            'assets': ['DN', 'C1'],
            'description': 'Surface reflectance',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands(*__visible_bands_union)
        },
        'temp': {
            'assets': ['DN', 'C1'],
            'description': 'Brightness (apparent) temperature',
            'toa': True,
            'startdate': _lt5_startdate,
            'latency': 0,
            # units given by https://landsat.usgs.gov/landsat-8-l8-data-users-handbook-section-5
            'bands': [{'name': n, 'units': 'degree Kelvin'} for n in ['LWIR', 'LWIR2']],
        },
        'fmask': {
            'assets': ['DN', 'C1'],
            'description': 'Fmask cloud cover',
            'nargs': '*',
            'toa': True,
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands('finalmask', 'cloudmask',
                                    'PCP', 'clearskywater', 'clearskyland'),
        },
        'cloudmask': {
            'assets': ['C1'],
            'description': ('Cloud (and shadow) mask product based on cloud '
                            'bits of the quality band'),
            'toa': True,
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands('cloudmask'),
        },
        'tcap': {
            'assets': ['DN', 'C1'],
            'description': 'Tassled cap transformation',
            'toa': True,
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands('Brightness', 'Greenness', 'Wetness', 'TCT4', 'TCT5', 'TCT6'),
        },
        'dn': {
            'assets': ['DN', 'C1'],
            'description': 'Raw digital numbers',
            'toa': True,
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': [{'name': n, 'units': 'W/m^2/sr/um'} for n in __visible_bands_union],
        },
        'volref': {
            'assets': ['DN', 'C1'],
            'description': 'Volumetric water reflectance - valid for water only',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 0,
            # reflectance is unitless therefore volref should be unitless
            'bands': unitless_bands(*__visible_bands_union),
        },
        'wtemp': {
            'assets': ['DN', 'C1'],
            'description': 'Water temperature (atmospherically correct) - valid for water only',
            # It's not really TOA, but the product code will take care of atm correction itself
            'toa': True,
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': [{'name': n, 'units': 'degree Kelvin'} for n in ['LWIR', 'LWIR2']],
        },
        #'Indices': {
        'bi': {
            'assets': ['DN', 'C1'],
            'description': 'Brightness Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands('bi'),
        },
        'evi': {
            'assets': ['DN', 'C1'],
            'description': 'Enhanced Vegetation Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands('evi'),
        },
        'lswi': {
            'assets': ['DN', 'C1'],
            'description': 'Land Surface Water Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands('lswi'),
        },
        'msavi2': {
            'assets': ['DN', 'C1'],
            'description': 'Modified Soil-Adjusted Vegetation Index (revised)',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands('msavi2'),
        },
        'ndsi': {
            'assets': ['DN', 'C1'],
            'description': 'Normalized Difference Snow Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands('ndsi'),
        },
        'ndvi': {
            'assets': ['DN', 'C1'],
            'description': 'Normalized Difference Vegetation Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands('ndvi'),
        },
        'ndwi': {
            'assets': ['DN', 'C1'],
            'description': 'Normalized Difference Water Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands('ndwi'),
        },
        'satvi': {
            'assets': ['DN', 'C1'],
            'description': 'Soil-Adjusted Total Vegetation Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands('satvi'),
        },
        'vari': {
            'assets': ['DN', 'C1'],
            'description': 'Visible Atmospherically Resistant Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands('vari'),
        },
        #'Tillage Indices': {
        'ndti': {
            'assets': ['DN', 'C1'],
            'description': 'Normalized Difference Tillage Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands('ndti'),
        },
        'crc': {
            'assets': ['DN', 'C1'],
            'description': 'Crop Residue Cover',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands('crc'),
        },
        'sti': {
            'assets': ['DN', 'C1'],
            'description': 'Standard Tillage Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands('sti'),
        },
        'isti': {
            'assets': ['DN', 'C1'],
            'description': 'Inverse Standard Tillage Index',
            'arguments': [__toastring],
            'startdate': _lt5_startdate,
            'latency': 0,
            'bands': unitless_bands('isti'),
        },
        'ndvi8sr': {
            'assets': ['SR'],
            'description': 'Normalized Difference Vegetation from LC8SR',
            'startdate': _lc8_startdate,
            'latency': 0,
            'bands': unitless_bands('ndvi8sr'),
        },
        'landmask': {
            'assets': ['SR'],
            'description': 'Land mask from LC8SR',
            'startdate': _lc8_startdate,
            'latency': 0,
            'bands': unitless_bands('landmask'),
        },
    }

    gips.atmosphere.add_acolite_product_dicts(_products, 'DN', 'C1')

    for pname, pdict in _products.items():
        if 'C1' in pdict['assets']:
            pdict['assets'] += ['C1S3', 'C1GS']

    for product, product_info in _products.items():
        product_info['startdate'] = min(
            [landsatAsset._assets[asset]['startdate']
                for asset in product_info['assets']]
        )

        if 'C1' in product_info['assets']:
            product_info['latency'] = landsatAsset._assets['C1']['latency']
        else:
            product_info['latency'] = float("inf")

    def _process_indices(self, image, asset_fn, metadata, sensor, indices,
                         coreg_shift=None):
        """Process the given indices and add their files to the inventory.

        Image is a GeoImage suitable for generating the indices.
        Metadata is passed in to the gippy Indices() call.  Sensor is
        used to generate index filenames and saving info about the
        product to self. Indices is a dict of desired keys; keys and
        values are the same as requested products in process(). Coreg_shift
        is a dict with keys `x` and `y` used to make affine
        transformation for `-coreg` products.
        """
        verbose_out("Starting on {} indices: {}".format(len(indices), indices.keys()), 2)
        for prod_and_args, split_p_and_a in indices.items():
            verbose_out("Starting on {}".format(prod_and_args), 3)
            temp_fp = self.temp_product_filename(sensor, prod_and_args)
            # indices() assumes many indices per file; we just want one
            imgout = algorithms.indices(image, [split_p_and_a[0]], temp_fp)
            imgout.add_meta(self.prep_meta(asset_fn, metadata))
            if coreg_shift:
                self._time_report("coregistering index")
                xcoreg = coreg_shift.get('x', 0.0)
                ycoreg = coreg_shift.get('y', 0.0)

                self._time_report("coreg (x, y) = ({:.3f}, {:.3f})"
                                  .format(xcoreg, ycoreg))

                coreg_mag = (xcoreg ** 2 + ycoreg ** 2) ** 0.5
                insane =  coreg_mag > _default_coreg_mag_thresh  # TODO: actual fix

                imgout.add_meta("COREG_MAGNITUDE", str(coreg_mag))
                imgout.add_meta("COREG_EXCESSIVE_SHIFT", str(insane))
                if not insane:
                    affine = imgout.affine()
                    affine[0] += xcoreg
                    affine[3] += ycoreg
                    imgout.set_affine(affine)
                imgout.save()
                imgout = None

            archived_fp = self.archive_temp_path(temp_fp)
            self.AddFile(sensor, prod_and_args, archived_fp)

    def _download_gcs_bands(self, output_dir):
        if 'C1GS' not in self.assets:
            raise Exception("C1GS asset not found for {} on {}".format(
                self.id, self.date
            ))

        band_files = []

        for path in self.assets['C1GS'].band_paths():
            match = re.match(r'/[\w_]+/(.+)', path)
            url = match.group(1)
            output_path = os.path.join(
                output_dir, os.path.basename(url)
            )
            if not os.path.exists(output_path):
                self.Asset.gs_backoff_downloader(url, output_path)
            band_files.append(output_path)
        return band_files

    @property
    def preferred_asset(self):
        if getattr(self, '_preferred_asset', None):
            return self._preferred_asset

        # figure out which asset should be used for processing
        self._preferred_asset = list(self.assets.keys())[0] # really an asset type string, eg 'SR'
        if len(self.assets) > 1:
            # if there's more than one, have to choose:
            # prefer local over fetching from the cloud, and prefer C1 over DN
            at_pref = self.get_setting('asset-preference')
            try:
                self._preferred_asset = next(at for at in at_pref if at in self.assets)
            except StopIteration:
                verbose_out('No preferred asset types ({}) found in'
                    ' available assets ({})'.format(self.assets, at_pref),
                    2, sys.stderr)
                self._preferred_asset = None
            if 'SR' in self.assets:
                # this method is structured poorly; handle an odd error case:
                p_types = set(v[0] for v in products.requested.values())
                if p_types & {'landmask', 'ndvi8sr'}:
                    raise NotImplementedError(
                        "Can't process SR alongside non-SR")

        return self._preferred_asset


    @Data.proc_temp_dir_manager
    def process(self, products=None, overwrite=False, **kwargs):
        """ Make sure all products have been processed """
        products = super(landsatData, self).process(products, overwrite, **kwargs)
        if len(products) == 0:
            verbose_out("Skipping processing; no products requested.", 5)
            return
        if len(self.assets) == 0:
            verbose_out("Skipping processing; no assets found.", 5)
            return

        start = datetime.now()
        asset = self.preferred_asset

        # TODO: De-hack this to loop over products & handle the SR case --^

        if asset == 'SR':

            datafiles = self.assets['SR'].datafiles()

            imgpaths = dict()

            for datafile in datafiles:

                key = datafile.partition('_')[2].split('.')[0]
                path = os.path.join('/vsitar/' + self.assets['SR'].filename, datafile)

                imgpaths[key] = path

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
                    ndvi[wvalid] = ((nir[wvalid] - red[wvalid]) /
                                    (nir[wvalid] + red[wvalid]))

                    verbose_out("writing " + fname, 2)
                    imgout = gippy.GeoImage.create_from(img, fname, 1, 'float32')
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
                    imgout = gippy.GeoImage.create_from(img, fname, 1, 'uint8')
                    imgout.set_bandname('Land mask', 1)
                    imgout[0].write(cfmask)

                archive_fp = self.archive_temp_path(fname)
                self.AddFile(sensor, key, archive_fp)

        else: # C1 types & DN
            # Add the sensor for this date to the basename
            self.basename = self.basename + '_' + self.sensors[asset]

            md = {}

            product_is_coreg = [(v and 'coreg' in v) for v in products.requested.values()]
            coreg = all(product_is_coreg)
            if not coreg and any(product_is_coreg):
                # Disallow coreg and non-coreg products in same processing
                # call both to avoid having to check each if each product
                # needs to be shifted as well as a hint to users who will
                # likely only do this as an accident anyway.
                raise ValueError("Mixing coreg and non-coreg products is not allowed")


            if coreg:

                ## TODO: re-read and consider deleting this stale comment
                # If possible, use AROP 'ortho' command to co-register this landsat scene
                # against a reference Sentinel2 scene. When AROP is successful it creates
                # a text file with parameters in it that is needed to apply an offset.
                # That text file will get reused if it exists. Otherwise, we will attempt
                # to create a new one. This might fail because it cannot find a S2 scene
                # within a specified window; in this case simply use the Landsat data as
                # it is. This might also fail for mathematical reasons, in which case
                # do still create a product? Note S2 is a new sensor so for most years
                # the expected situation is not finding matching scene.

                # TODO: this should follow normal basename file naming, but for now
                #                 [:-3]
                #       (which is not an emoticon)
                #       for backward compatibility.
                # Read the asset for projection and NIR
                with utils.error_handler('Error reading ' + basename(self.assets[asset].filename)):
                    img = self._readraw(asset)
                self.coreg_args_file = os.path.join(
                    self.path, self.basename[:-3] + "coreg_args.txt")
                self.coreg_run_log = os.path.join(
                    self.path, self.basename[:-3] + "coreg_log.txt")

                if not os.path.exists(self.coreg_args_file):
                    with utils.error_handler('Problem with running AROP'):
                        tmpdir_fp = self.generate_temp_path('arop')
                        utils.mkdir(tmpdir_fp)
                        try:
                            # on error, use the unshifted image
                            mos_source = settings().REPOS['landsat'].get(
                                'coreg_mos_source', 'sentinel2'
                            )
                            sat_key = 'custom_mosaic' if mos_source != 'sentinel2' else 'sentinel2'
                            base_image_fp = None
                            if mos_source is 'sentinel2':
                                base_image_fp = self.sentinel2_coreg_export(tmpdir_fp)
                            else:
                                proj = img.projection()
                                base_image_fp = self.custom_mosaic_coreg_export(
                                        mos_source, proj, tmpdir_fp)
                            nir_band = img['NIR'].filename()
                            self.run_arop(base_image_fp, nir_band, source=sat_key)
                        except NoBasemapError:
                            # TODO: once we have confidence that this error is
                            #       infrequent, then this can go away.
                            with open(self.coreg_args_file, 'w') as cra:
                                cra.write("x: {}\n".format(0.))
                                cra.write("y: {}\n".format(0.))
                                cra.write("total_cp: {}\n".format(None))
                                cra.write("used_cp: {}\n".format(None))
                                cra.write("basemaperror: {}\n".format(
                                    'No basemap found for co-registration {}'
                                    .format(mos_source))
                                )
                        finally:
                            img = None

                with utils.error_handler('parsing ' + self.coreg_args_file):
                    coreg_xshift, coreg_yshift = self.parse_coreg_coefficients()

                md['COREG_STATUS'] = (
                    'AROP'
                    if (coreg_xshift ** 2 + coreg_yshift ** 2) ** 0.5 > 0
                    else 'NO_SHIFT_FALLBACK'
                )

            img = self._readraw(asset)

            # This is landsat, so always just one sensor for a given date
            sensor = self.sensors[asset]

            if asset.startswith('C1'):
                # BQA in C1 defines value 1 as "designated fill", in addition to any
                # no data value defined for a band.  As BQA value 0 is
                # undefined, and has not been seen in any assets thus far -- so
                # also excluding 0 is OK.
                # N.B. the label "designated fill" is mutually exclusive with
                #      all other bqa labels.
                #      See https://landsat.usgs.gov/collectionqualityband
                qaimg = self._readqa(asset)
                img.add_mask(qaimg[0] > 1)
                qaimg = None

            asset_fn = self.assets[asset].filename

            meta = self.assets[asset].meta['bands']
            visbands = self.assets[asset].visbands
            lwbands = self.assets[asset].lwbands

            # running atmosphere if any products require it
            toa = True
            for val in products.requested.values():
                toa = toa and (self._products[val[0]].get('toa', False) or 'toa' in val)
            if not toa:
                start = datetime.now()

                if not settings().REPOS[self.Repository.name.lower()]['6S']:
                    raise ValueError("atmospheric correction requested but"
                        " settings.REPOS['landsat']['6S'] is False.")
                with utils.error_handler('Problem running 6S atmospheric model'):
                    wvlens = [(meta[b]['wvlen1'], meta[b]['wvlen2']) for b in visbands]
                    geo = self.metadata['geometry']
                    atm6s = SIXS(visbands, wvlens, geo, self.metadata['datetime'], sensor=self.sensor_set[0])

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

            # Process standard products (this is in the 'DN' block)
            for key, val in groups['Standard'].items():
                p_type = val[0]
                if asset not in self._products[p_type]['assets']:
                    verbose_out("{} not supported for {} assets".format(p_type, asset), 5)
                    continue
                start = datetime.now()
                # TODO - update if no atmos desired for others
                toa = self._products[val[0]].get('toa', False) or 'toa' in val
                # Create product
                with utils.error_handler(
                        'Error creating product {} for {}'
                        .format(key, basename(self.assets[asset].filename)),
                        continuable=True):
                    fname = self.temp_product_filename(sensor, key)
                    if val[0] == 'fmask':
                        tolerance, dilation = 3, 5
                        if len(val) >= 3:
                            tolerance, dilation = [int(v) for v in val[1:3]]
                        imgout = algorithms.fmask(reflimg, fname, tolerance, dilation)

                    elif val[0] == 'cloudmask':
                        qaimg = self._readqa(asset)
                        npqa = qaimg.read()  # read image file into numpy array
                        qaimg = None
                        # https://landsat.usgs.gov/collectionqualityband
                        # cloudmaskmask = (cloud and
                        #                  (cc_low or cc_med or cc_high)
                        #                 ) or csc_high
                        # cloud iff bit 4
                        # (cc_low or cc_med or cc_high) iff bit 5 or bit 6
                        # (csc_high) iff bit 8 ***
                        #  NOTE: from USGS tables as of 2018-05-22, cloud
                        #  shadow conficence is either high(3) or low(1).
                        #  No pixels get medium (2).  And only no-data pixels
                        #  ever get no (0) confidence.


                        # GIPPY 1.0 note: rewrite this whole product after
                        # adding get_bit method to GeoRaster

                        def get_bit(np_array, i):
                            """Return an array with the ith bit extracted from each cell."""
                            return (np_array >> i) & 0b1

                        np_cloudmask = (
                            get_bit(npqa, 8) # shadow
                            | (get_bit(npqa, 4) & # cloud
                               ( # with at least low(1) confidence
                                   get_bit(npqa, 5) | get_bit(npqa, 6)
                               )
                            )
                        ).astype('uint8')

                        dilation_width = 20
                        elem = numpy.ones((dilation_width,) * 2, dtype='uint8')
                        np_cloudmask_dilated = binary_dilation(
                            np_cloudmask, structure=elem,
                        ).astype('uint8')
                        np_cloudmask_dilated *= (npqa != 1)
                        #

                        imgout = gippy.GeoImage.create_from(img, fname, 1, 'uint8')
                        verbose_out("writing " + fname, 2)
                        imgout.set_bandname(
                            self._products[val[0]]['bands'][0]['name'], 1
                        )
                        md.update(
                            {
                                'GIPS_LANDSAT_VERSION': self.version,
                                'GIPS_C1_DILATED_PIXELS': str(dilation_width),
                                'GIPS_LANDSAT_CLOUDMASK_CLOUD_VALUE': '1',
                                'GIPS_LANDSAT_CLOUDMASK_CLEAR_OR_NODATA_VALUE': '0',
                            }
                        )
                        ####################
                        # GIPPY1.0 note: replace this block with
                        # imgout[0].set_nodata(0.)
                        # imout[0].write_raw(np_cloudmask_dilated)
                        imgout[0].write(
                            np_cloudmask_dilated
                        )
                        imgout = None
                        imgout = gippy.GeoImage(fname, True)
                        imgout[0].set_nodata(0.)
                        ####################
                    elif val[0] == 'rad':
                        imgout = gippy.GeoImage.create_from(img, fname, len(visbands), 'int16')
                        for i in range(0, len(imgout)):
                            imgout.set_bandname(visbands[i], i + 1)
                        imgout.set_nodata(-32768)
                        imgout.set_gain(0.1)
                        if toa:
                            for col in visbands:
                                img[col].save(imgout[col])
                        else:
                            for col in visbands:
                                ((img[col] - atm6s.results[col][1]) / atm6s.results[col][0]
                                        ).save(imgout[col])
                        # Mask out any pixel for which any band is nodata
                        # TODO: why is this commented out?
                        # imgout.apply_mask(img.data_mask())
                    elif val[0] == 'ref':
                        imgout = gippy.GeoImage.create_from(img, fname, len(visbands), 'int16')
                        for i in range(0, len(imgout)):
                            imgout.set_bandname(visbands[i], i + 1)
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
                        # TODO: why is this commented out?
                        #imgout.apply_mask(img.DataMask())
                    elif val[0] == 'tcap':
                        tmpimg = gippy.GeoImage(reflimg)
                        tmpimg.select(['BLUE', 'GREEN', 'RED', 'NIR', 'SWIR1', 'SWIR2'])
                        arr = numpy.array(self.Asset._sensors[self.sensor_set[0]]['tcap']).astype('float32')
                        imgout = algorithms.linear_transform(tmpimg, fname, arr)
                        imgout.add_meta('AREA_OR_POINT', 'Point')
                        outbands = ['Brightness', 'Greenness', 'Wetness', 'TCT4', 'TCT5', 'TCT6']
                        for i in range(0, len(imgout)):
                            imgout.set_bandname(outbands[i], i + 1)
                    elif val[0] == 'temp':
                        imgout = gippy.GeoImage.create_from(img, fname, len(lwbands), 'int16')
                        for i in range(0, len(imgout)):
                            imgout.set_bandname(lwbands[i], i + 1)
                        imgout.set_nodata(-32768)
                        imgout.set_gain(0.1)
                        [reflimg[col].save(imgout[col]) for col in lwbands]
                    elif val[0] == 'dn':
                        rawimg = self._readraw(asset)
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
                        raise NotImplementedError('See https://gitlab.com/appliedgeosolutions/gips/issues/155')
                        imgout = gippy.GeoImage.create_from(img, fname, len(lwbands), 'int16')
                        [imgout.set_bandname(lwbands[i], i + 1) for i in range(0, len(imgout))]
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

                    fname = imgout.filename()
                    imgout.add_meta(self.prep_meta(asset_fn, md))

                    if coreg:
                        coreg_mag = (coreg_xshift ** 2 + coreg_yshift ** 2) ** 0.5
                        insane =  coreg_mag > _default_coreg_mag_thresh  # TODO: actual fix

                        imgout.add_meta("COREG_MAGNITUDE", str(coreg_mag))
                        imgout.add_meta("COREG_EXCESSIVE_SHIFT", str(insane))

                        if True: #not insane:
                            self._time_report("Setting affine of product")
                            affine = imgout.affine()
                            self._time_report("Affine was: {}".format(affine.tolist()))
                            affine[0] += coreg_xshift
                            affine[3] += coreg_yshift
                            self._time_report("Affine set to: {}".format(affine.tolist()))
                            imgout.set_affine(affine)
                    imgout.save()
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

                coreg_shift = {}

                if coreg:
                    coreg_shift['x'] = coreg_xshift
                    coreg_shift['y'] = coreg_yshift

                # Run TOA
                if len(indices_toa) > 0:
                    self._process_indices(reflimg, asset_fn, md, sensor,
                                          indices_toa, coreg_shift)

                # Run atmospherically corrected
                if len(indices) > 0:
                    for col in visbands:
                        img[col] = (img[col] -  atm6s.results[col][1]) \
                        * (1.0 / atm6s.results[col][0]) \
                        * (1.0 / atm6s.results[col][2])

                    self._process_indices(img, asset_fn, md, sensor, indices,
                                          coreg_shift)

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
                aco_dn = self.generate_temp_path('acolite')
                os.mkdir(aco_dn)
                a_obj = self.assets[asset]
                err_msg = 'Error creating ACOLITE products {} for {}'.format(
                    groups['ACOLITE'].keys(), os.path.basename(a_obj.filename))
                with utils.error_handler(err_msg, continuable=True):
                    # TODO use self.temp_product_filename(sensor, prod_type):
                    # then copy to self.path using methods
                    p_spec = {p: os.path.join(self.path, self.basename + '_' + p + '.tif')
                              for p in groups['ACOLITE']}
                    prodout = gips.atmosphere.process_acolite(a_obj, aco_dn,
                        p_spec, self.prep_meta(asset_fn, md.copy()), reflimg)
                    endtime = datetime.now()
                    for k, fn in prodout.items():
                        self.AddFile(sensor, k, fn)
                    verbose_out(' -> {}: processed {} in {}'.format(
                            self.basename, prodout.keys(), endtime - start), 1)
                ## end ACOLITE
            reflimg = None

    def filter(self, pclouds=100, sensors=None, **kwargs):
        """Check if Data object passes filter.

        User can't enter pclouds, but can pass in --sensors.  kwargs
        isn't used.
        """
        if not super(landsatData, self).filter(pclouds, **kwargs):
            return False
        if sensors:
            if type(sensors) is str:
                sensors = [sensors]
            sensors = set(sensors)
            # ideally, the data class would be trimmed by
            if not sensors.intersection(self.sensor_set):
                return False
        return True

    def meta(self, asset_type):
        """Read in Landsat metadata file and return it as a dict.

         Also saves it to self.metadata."""
        # TODO this belongs in landsatAsset
        # test if metadata already read in, if so, return
        if hasattr(self, 'metadata'):
            return self.metadata

        asset_obj = self.assets[asset_type]
        c1_json = asset_obj.load_c1_json()
        if c1_json:
            r = self.Asset.gs_backoff_get(c1_json['mtl'])
            r.raise_for_status()
            text = r.text
            qafn = c1_json['qa-band']
        else:
            datafiles = asset_obj.datafiles()
            # save for later; defaults to None
            qafn = next((f for f in datafiles if '_BQA.TIF' in f), None)
            # locate MTL file and save it to disk if it isn't saved already
            mtlfilename = next(f for f in datafiles if 'MTL.txt' in f)
            if os.path.exists(mtlfilename) and os.stat(mtlfilename).st_size:
                os.remove(mtlfilename)
            if not os.path.exists(mtlfilename):
                mtlfilename = asset_obj.extract([mtlfilename])[0]
            # Read MTL file
            with utils.error_handler(
                            'Error reading metadata file ' + mtlfilename):
                text = open(mtlfilename, 'r').read()
            if len(text) < 10:
                raise IOError('MTL file is too short. {}'.format(mtlfilename))

        sensor = asset_obj.sensor
        smeta = asset_obj._sensors[sensor]

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
        }
        if qafn is not None:
            self.metadata['qafilename'] = qafn
        #self.metadata.update(smeta)
        return self.metadata

    def _readqa(self, asset_type):
        """Returns a gippy GeoImage containing a QA band.

        The QA band belongs to the asset corresponding to the given asset type.
        """
        md = self.meta(asset_type)
        if self.assets[asset_type].in_cloud_storage():
            qafilename = self.Asset._cache_if_vsicurl(
                [md['qafilename']],
                self._temp_proc_dir
            )
            return gippy.GeoImage(qafilename)
        if settings().REPOS[self.Repository.name.lower()]['extract']:
            # Extract files
            qadatafile = self.assets[asset_type].extract([md['qafilename']])
        else:
            # Use tar.gz directly using GDAL's virtual filesystem
            qadatafile = os.path.join(
                    '/vsitar/' + self.assets[asset_type].filename,
                    md['qafilename'])
        qaimg = gippy.GeoImage(qadatafile)
        return qaimg

    def _readraw(self, asset_type):
        """Return a gippy GeoImage containing raster bands.

        The bands are read from the asset corresponding to the given
        asset type.
        """
        # TODO this belongs in landsatAsset
        start = datetime.now()
        asset_obj = self.assets[asset_type]

        md = self.meta(asset_type)

        try:
            self._time_report("Gathering band files")
            if asset_type == 'C1GS':
                paths = self._download_gcs_bands(self._temp_proc_dir)
            else:
                paths = asset_obj.band_paths()
            self._time_report("Finished gathering band files")
        except NotImplementedError:
            # Extract files, use tarball directly via GDAL's virtual filesystem?
            if self.get_setting('extract'):
                paths = self.extract(md['filenames'])
            else:
                paths = [os.path.join('/vsitar/' + asset_obj.filename, f)
                         for f in md['filenames']]
        self._time_report("reading bands")
        image = gippy.GeoImage.open(paths)
        image.set_nodata(0)

        # TODO - set appropriate metadata
        #for key,val in meta.items():
        #    image.add_meta(key,str(val))

        # Geometry used for calculating incident irradiance
        # colors = self.assets['DN']._sensors[self.sensor_set[0]]['colors']

        sensor = asset_obj.sensor
        colors = asset_obj._sensors[sensor]['colors']

        for bi in range(0, len(md['filenames'])):
            image.set_bandname(colors[bi], bi + 1)
            # need to do this or can we index correctly?
            band = image[bi]
            gain = md['gain'][bi]
            band.set_gain(gain)
            band.set_offset(md['offset'][bi])
            dynrange = md['dynrange'][bi]
            # #band.SetDynamicRange(dynrange[0], dynrange[1])
            # dynrange[0] was used internally to for conversion to radiance
            # from DN in GeoRaster.read:
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

        self._time_report("done reading bands")
        verbose_out('%s: read in %s' % (image.basename(), datetime.now() - start), 2)
        return image

    def _s2_tiles_for_coreg(self, inventory, date_found, landsat_footprint):
        if len(inventory) == 0:
            verbose_out("No S2 assets found on {}".format(date_found), 3)
            return None

        raster_vsi_paths = []
        s2_footprint = Polygon()
        tiles = inventory[date_found].tiles.keys()

        for tile in tiles:
            s2ao = inventory[date_found][tile].current_asset()
            if s2ao.tile[:2] != self.utm_zone():
                continue
            band_8 = next(f for f in s2ao.datafiles()
                if f.endswith('B08.jp2') and tile in basename(f))
            vsi_str = (band_8 if s2ao.asset == 'L1CGS' else
                       '/vsizip/' + os.path.join(s2ao.filename, band_8))
            raster_vsi_paths.append(vsi_str)
            verbose_out(':::_s2_tiles_for_coreg: using {}                <<<<<<'
                        .format(tile))
            s2_footprint = s2_footprint.union(wkt_loads(s2ao.footprint()))

        if len(raster_vsi_paths) == 0:
            verbose_out("No S2 assets found in UTM zone {}".format(self.utm_zone()), 3)
            return None

        percent_cover = (
            s2_footprint.intersection(landsat_footprint).area
        ) / landsat_footprint.area * 100
        sufficient_coverage = percent_cover > 20
        verbose_out("S2 assets {}cover enough of Landsat data ({}%)."
                    .format('do not ' if not sufficient_coverage else '',
                            percent_cover),
                    3)
        return raster_vsi_paths if sufficient_coverage else None 

    def custom_mosaic_coreg_export(self, mos_source, proj, tmpdir):
        images = gippy.GeoImages([mos_source])
        feat = self.assets[asset].get_geofeature()
        utm_gjs_feat = geojson.Feature(
            geometry=wkt_loads(
                utils.transform_shape(feat.wkt_geometry(),
                                      feat.srs(),
                                      img.srs()),
            ),
            properties={}
        )
        tmp_feat_fp = os.path.join(tmpdir_fp, 'feat.geojson')
        with fiona.open(
                tmp_feat_fp, 'w', 'GeoJSON',
                crs=from_epsg('326{}'.format(self.utm_zone())),
                schema={
                    'geometry': 'Polygon',
                    'properties': {}
                },
        ) as tvec:
            tvec.write(utm_gjs_feat)
        cutter = gippy.GeoVector(tmp_feat_fp)
        tmp_fp = os.path.join(
            tmpdir_fp, 'custom_mosaic.bin')
        algorithms.cookie_cutter(images, cutter[0], tmp_fp, 30.0, 30.0)
        return tmp_fp


    def sentinel2_coreg_export(self, tmpdir):
        """
        Grabs closest (temporally) sentinel2 tiles and stitches them together
        to match this landsat tile's footprint.

        tmpdir is a directory name
        """
        from gips.data.sentinel2 import sentinel2Asset, sentinel2Data
        landsat_shp = self.get_setting('tiles')
        spatial_extent = SpatialExtent.factory(
            sentinel2Data, site=landsat_shp,
            where="pr = '{}'".format(self.id),
            ptile=20.0)[0]
        fetch = False

        # If there is no available sentinel2 scene on that day, search before and after
        # until one is found.
        delta = timedelta(1)

        if self.date < date(2017, 1, 1):
            date_found = starting_date = date(2017, 1, 1) + (
                self.date - date(self.date.year, 1, 1))
        else:
            date_found = starting_date = self.date

        temporal_extent = TemporalExtent(starting_date.strftime("%Y-%j"))
        self._time_report("querying for most recent sentinel2 images")

        # TODO: DRY the following statement which is repeated 3 times here
        inventory = DataInventory(sentinel2Data, spatial_extent, temporal_extent, fetch=fetch, pclouds=33)

        landsat_footprint = wkt_loads(self.assets[next(iter(self.assets))].get_geometry())
        geo_images = self._s2_tiles_for_coreg(
            inventory, starting_date, landsat_footprint
        )
        if geo_images:
            geo_images = self.Asset._cache_if_vsicurl(geo_images, tmpdir)
            date_found = starting_date

        while not geo_images:
            if delta > timedelta(90):
                raise NoBasemapError(
                    "didn't find s2 images in this utm zone {}, (pathrow={},date={})"
                    .format(self.utm_zone(), self.id, self.date)
                )
            temporal_extent = TemporalExtent((starting_date + delta).strftime("%Y-%j"))
            inventory = DataInventory(
                sentinel2Data, spatial_extent, temporal_extent,
                fetch=fetch, pclouds=33
            )

            geo_images = self._s2_tiles_for_coreg(
                inventory, (starting_date + delta), landsat_footprint
            )

            if geo_images:
                geo_images = self.Asset._cache_if_vsicurl(geo_images, tmpdir)
                date_found = starting_date + delta
                break

            temporal_extent = TemporalExtent((starting_date - delta).strftime("%Y-%j"))
            inventory = DataInventory(
                sentinel2Data, spatial_extent, temporal_extent,
                fetch=fetch, pclouds=33
            )

            geo_images = self._s2_tiles_for_coreg(
                inventory, (starting_date - delta), landsat_footprint
            )
            if geo_images:
                geo_images = self.Asset._cache_if_vsicurl(geo_images, tmpdir)
                date_found = starting_date - delta
                break

            delta += timedelta(1)

        self._time_report("merge sentinel images to bin")
        merge_args = ["gdal_merge.py", "-o", tmpdir + "/sentinel_mosaic.bin",
                      "-of", "ENVI", "-a_nodata", "0"]
        # only use images that are in the same proj as landsat tile
        merge_args.extend(geo_images)
        env = os.environ.copy()
        env["GDAL_NUM_THREADS"] = "1"
        subprocess.call(merge_args, env=env)
        self._time_report("done with s2 export")
        return tmpdir + '/sentinel_mosaic.bin'

    def run_arop(self, base_band_filename, warp_band_filename, source,
                 source_satellite="Landsat8"):
        """
        Runs AROP's `ortho` program.

        base_band_filename is the filename of the mosaic image you want
        to warp to.
        warp_band_filename is the bands out of self that you want to warp.
        source is either 'sentinel2' or 'custom_mosaic'
        source_satellite can be any of 'Landsat{N}' \forall N in [4,5,7,8]
        or 'Sentinel2', formatted per AROP specs.
        """
        warp_tile = self.id
        warp_date = self.date
        asset_type = self.preferred_asset
        asset = self.assets[asset_type]

        ## Selects what order polynomial is used for coregistration...just use
        ## a shift --> 0th order.
        out_poly_order = 0

        with utils.make_temp_dir() as tmpdir:
            nir_band = asset._sensors[asset.sensor]['bands'][
                asset._sensors[asset.sensor]['colors'].index('NIR')
            ]
            if asset_type not in ['C1GS', 'C1S3']:
                warp_band_filename = '/vsitar/' + os.path.join(asset.filename, warp_band_filename)

            # TODO:  I believe this is a singleton, so it should go away
            warp_bands_bin = []

            band_bin = basename(warp_band_filename) + '.bin'
            cmd = ["gdal_translate", "-of", "ENVI",
                   warp_band_filename,
                   os.path.join(tmpdir, band_bin)]
            subprocess.call(args=cmd, cwd=tmpdir)
            warp_bands_bin.append(band_bin)

            # make parameter file
            with open(os.path.join(os.path.dirname(__file__), 'input_file_tmp.inp'), 'r') as input_template:
                template = input_template.read()

            base_band_img = gippy.GeoImage(base_band_filename)
            warp_base_band_filename = [
                f for f in warp_bands_bin
                        if f.endswith("B{}.bin".format(nir_band))
            ][0]
            warp_base_band_img = gippy.GeoImage(os.path.join(tmpdir, warp_base_band_filename))
            base_pixel_size = abs(base_band_img.resolution().x())
            warp_pixel_size = abs(warp_base_band_img.resolution().x())
            base_warp_ul_delta_x = base_band_img.minxy().x() - warp_base_band_img.minxy().x()
            base_warp_ul_delta_y = base_band_img.maxxy().y() - warp_base_band_img.maxxy().y()
            out_pixel_size = max(base_pixel_size, warp_pixel_size)
            lnd_sen_lut = {'LT5': 'Landsat5', 'LE7': 'Landsat7', 'LC8': 'Landsat8'}
            base_params = dict(
                warp_satellite=lnd_sen_lut[asset.sensor],
                warp_nbands=len(warp_bands_bin),
                warp_bands=' '.join([os.path.join(tmpdir, band) for band in warp_bands_bin]),
                warp_base_band=os.path.join(tmpdir, warp_base_band_filename),
                warp_data_type=' '.join(([
                    str(warp_base_band_img.type())
                ] * len(warp_bands_bin))),
                warp_nsample=warp_base_band_img.xsize(),
                warp_nline=warp_base_band_img.ysize(),
                warp_pixel_size=warp_pixel_size,
                warp_upper_left_x=warp_base_band_img.minxy().x(),
                warp_upper_left_y=warp_base_band_img.maxxy().y(),
                warp_utm=self.utm_zone(),
                out_bands=' '.join(
                    [os.path.join(tmpdir, basename(band) + '_warped.bin')
                     for band in warp_bands_bin]
                ),
                out_base_band=os.path.join(
                    tmpdir, basename(warp_base_band_filename)) + '_warped.bin',
                out_pixel_size=out_pixel_size,
                out_poly_order=out_poly_order,
                tmpdir=tmpdir
            )
            mos_sen_lut = {'sentinel2': 'Sentinel2',
                           'custom_mosaic': source_satellite}
            mosaic_params = dict(
                base_satellite=mos_sen_lut[source],
                base_band=base_band_filename,
                base_nsample=base_band_img.xsize(),
                base_nline=base_band_img.ysize(),
                base_pixel_size=base_pixel_size,
                base_upper_left_x=base_band_img.minxy().x(),
                base_upper_left_y=base_band_img.maxxy().y(),
                base_utm=self.utm_zone(),
            )
            all_params = mosaic_params
            all_params.update(base_params)
            parameters = template.format(**all_params)
            parameter_file = os.path.join(tmpdir, 'parameter_file.inp')
            with open(parameter_file, 'w') as param_file:
                param_file.write(parameters)

            shutil.copyfile(
                os.path.join(os.path.dirname(__file__), 'lndortho.cps_par.ini'),
                os.path.join(tmpdir, 'lndortho.cps_par.ini')
            )
            base_band_img = warp_base_band_img = None
            x_shift = y_shift = xcoef = ycoef = total_cp = used_cp = rmse_cp = None
            shift_mag = exc_msg = exc_code = None
            try:
                # subprocess has a timeout option as of python 3.3
                ORTHO_TIMEOUT = 40 * 60
                cmd = ["timeout", str(ORTHO_TIMEOUT),
                       "ortho", "-r", parameter_file]
                with open(self.coreg_run_log, 'w') as coreg_log:
                    subprocess.check_call(
                            args=cmd, cwd=tmpdir,
                            stdout=coreg_log,
                            stderr=coreg_log,
                    )
            except subprocess.CalledProcessError as e:
                exc_msg = 'ortho exit code {} for {} {}'.format(
                    e.returncode, warp_tile, warp_date
                )
                if e.returncode == 124:  # 124 is the return code produced by 'timeout'
                    exc_msg  = (
                        "Coregistration timed out -- {} seconds for {} {} "
                        .format(ORTHO_TIMEOUT, warp_tile, warp_date))
                exc_code = 13
            except Exception as e:
                exc_code = 13
                exc_msg = str(e)
            finally:
                if out_poly_order == 1:
                    with open('{}/cp_log.txt'.format(tmpdir), 'r') as log:
                        xcoef_re = re.compile(r"x' += +(?P<const>[\d\-\.]+)( +\+ +(?P<dx>[\d\-\.]+) +\* +x +\+ +(?P<dy>[\d\-\.]+) +\* y)?")
                        ycoef_re = re.compile(r"y' += +(?P<const>[\d\-\.]+)( +\+ +(?P<dx>[\d\-\.]+) +\* +x +\+ +(?P<dy>[\d\-\.]+) +\* y)?")
                        cp_info_re = re.compile(r".*Total_Control_Points *= *(?P<total>[0-9]+), *"
                                                r"Used_Control_Points *= *(?P<used>[0-9]+), *"
                                                r"RMSE *= *(?P<rmse>[+-]?([0-9]*[.])?[0-9]+).*")
                        for line in log:
                            x_match = xcoef_re.match(line)
                            if x_match:
                                xcoef = float(x_match.group('const'))
                            y_match = ycoef_re.match(line)
                            if y_match:
                                ycoef = float(y_match.group('const'))
                            cp_match = cp_info_re.match(line)
                            if cp_match:
                                total_cp = cp_match.group('total')
                                used_cp = cp_match.group('used')
                                rmse_cp = cp_match.group('rmse')
                    if xcoef and ycoef:
                        x_shift = (() / out_pixel_size - xcoef) * out_pixel_size
                        y_shift = (() / out_pixel_size + ycoef) * out_pixel_size
                elif out_poly_order == 0:
                    orig_coarse_re = re.compile(r".*upper left coordinate has been updated[ \t]*from[ \t]*\((?P<ulx>[0-9\.]+), (?P<uly>[0-9\.]+)\).*")
                    orig_nocoarse_re = re.compile(r".*warp image UL: *\( *(?P<ulx>[0-9\.]+), *(?P<uly>[0-9\.]+)\).*")
                    arop_re = re.compile(r".*warp images may be adjusted with new UL: *\( *(?P<ulx>[0-9\.]+), *(?P<uly>[0-9\.]+)\).*")
                    cp_info_re = re.compile(r".*Num_CP_Candidates:[ \t]*(?P<candidate>[+-]?([0-9]*[.])?[0-9]+)[ \t]*"
                                            r"Num_CP_Selected:[ \t]*(?P<selected>[+-]?([0-9]*[.])?[0-9]+).*")
                    with open(self.coreg_run_log, 'r') as crl:
                        ortho_log = crl.read()

                    ortho_out = ortho_log.replace('\n', '\t')
                    origUL = orig_coarse_re.match(ortho_out)
                    if origUL is None:
                        origUL = orig_nocoarse_re.match(ortho_out)
                    aropUL = arop_re.match(ortho_out)
                    cp_info = cp_info_re.match(ortho_out)

                    if origUL and aropUL:
                        x_shift = float(aropUL.group('ulx')) - float(origUL.group('ulx'))
                        y_shift = float(aropUL.group('uly')) - float(origUL.group('uly'))
                    if cp_info:
                        used_cp = cp_info.group('selected')
                        total_cp = cp_info.group('candidate')

                    used_cp_thresh = settings().REPOS['landsat'].get(
                        'coreg_used_cp_thresh', 5)

                shift_mag_thresh = settings().REPOS['landsat'].get(
                    'coreg_shift_thresh', _default_coreg_mag_thresh)

                if exc_code is None and x_shift is None:
                    exc_msg = ('AROP: no coefs found in cp_log.txt --> {},{}'
                               .format(warp_tile, warp_date))
                    exc_code = CantAlignError.COREG_FAIL
                    x_shift = y_shift = -1e12
                elif exc_code is None:
                    shift_mag = (x_shift ** 2 + y_shift ** 2) ** 0.5
                if exc_code is None and (shift_mag > shift_mag_thresh):
                    exc_msg = ('AROP: shift magnitude of {}, exceeds thresholed of '
                         '{}').format(shift_mag, shift_mag_thresh)
                    exc_code = CantAlignError.EXCESSIVE_SHIFT
                if exc_code is None and (used_cp is None or int(used_cp) < used_cp_thresh):
                    exc_msg = ('AROP: need at least {} Control Points, and '
                           'only found {}').format(used_cp_thresh, used_cp)
                    exc_code = CantAlignError.INSUFFICIENT_CP


                with open(self.coreg_args_file, 'w') as cra:
                    cra.write("x: {}\n".format(x_shift))
                    cra.write("y: {}\n".format(y_shift))
                    cra.write("total_cp: {}\n".format(total_cp))
                    cra.write("used_cp: {}\n".format(used_cp))
                    if exc_code is not None:
                        cra.write("banned: {} ({})\n"
                                  .format(exc_msg, exc_code))

    def utm_zone(self):
        """
        Parse UTM zone out of `gdalinfo` output.
        """
        if getattr(self, 'utm_zone_number', None):
            return self.utm_zone_number
        self.utm_zone_number = None

        asset = self.assets[self.preferred_asset]

        # TODO: stick this somewhere better.  Just hacking to make it work now.
        if asset.asset in ['C1S3', 'C1GS']:
            if os.path.exists(asset.filename):
                c1json_content = asset.load_c1_json()
                utils.verbose_out('requesting ' + c1json_content['mtl'], 4)
                text = self.Asset.gs_backoff_get(c1json_content['mtl']).text
            else:
                query_results = asset.query_gs(asset.tile, asset.date)
                if query_results is None:
                    raise IOError('Could not locate metadata for'
                                  ' ({}, {})'.format(self.tile, self.date))
                url = cls.gs_object_url_base() + query_results['keys']['mtl']
                utils.verbose_out('requesting ' + url, 4)
                text = self.Asset.gs_backoff_get(url).text
        else:
            utils.vprint('asset is "{}"'.format(asset.asset))
            mtl = asset.extract([f for f in asset.datafiles() if f.endswith("MTL.txt")])[0]
            with open(mtl, 'r') as mtl_file:
                text = mtl_file.read()
        match = re.search(r'.*UTM_ZONE = (\d+).*', text)
        if match:
            self.utm_zone_number = match.group(1)
        else:
            raise ValueError('MTL file does not contian UTM_ZONE')
        utils.vprint('utm_zone is ' + str(self.utm_zone_number))
        return self.utm_zone_number

    def parse_coreg_coefficients(self):
        """
        Parse out coregistration coefficients from asset's `*_coreg_args.txt`
        file.
        """
        date = datetime.strftime(self.date, "%Y%j")
        verbose_out('Parsing {}'.format(self.coreg_args_file))
        with open(self.coreg_args_file, 'r') as cra:
            xcoef_re = re.compile(r"^x: (-?\d+\.?\d*)")
            ycoef_re = re.compile(r"^y: (-?\d+\.?\d*)")
            banned_re = re.compile(r"^banned: (?P<reason>[^\(]*)\((?P<exc_code>[^\)]+)\)$")
            # TODO: only for now is basemaperror not a fatal one
            basemap_re = re.compile(r"^basemaperror: (?P<reason>.*)$")

            for line in cra:
                x_match = xcoef_re.match(line)
                if x_match:
                    xcoef = float(x_match.group(1))
                y_match = ycoef_re.match(line)
                if y_match:
                    ycoef = float(y_match.group(1))
                banned = banned_re.match(line)
                if banned:
                    raise CantAlignError(
                        message=banned.group('reason'),
                        exc_code=int(banned.group('exc_code'))
                    )
                basemap = basemap_re.match(line)
                if basemap:
                    verbose_out(line)

        return xcoef, ycoef
