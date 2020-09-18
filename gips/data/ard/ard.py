#!/usr/bin/env python
################################################################################
#    GIPS ARD data module
#
#    AUTHOR: Rick Emery
#    EMAIL:  remery@ags.io
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

import os
from datetime import datetime, date
import re
import requests
from xml.etree import ElementTree
from backports.functools_lru_cache import lru_cache
import tarfile

from gips.data.core import Repository, Data, CloudCoverData
import gips.data.core

from gips.utils import settings
from gips import utils
import homura

__author__ = "Rick Emery <remery@ags.io>"
__version__ = '0.1.0'

def path_row(tile_id):
    """Converts the given ARD tile string into (path, row)."""
    return (tile_id[:3], tile_id[3:])

class ardRepository(Repository):
    name = 'ARD'
    description = 'Landsat Analysis Ready Data'
    _datedir = '%Y%m%d'
    _tile_attribute = 'PR'

    @classmethod
    def feature2tile(cls, feature):
        """ Get tile designation from a geospatial feature (i.e. a row) """
        fldindex = feature.GetFieldIndex(cls._tile_attribute)
        return str(feature.GetField(fldindex)).zfill(6)

class ardAsset(gips.data.core.CloudCoverAsset):
    Repository = ardRepository
    _lt5_startdate = date(1984, 3, 1)
    _le7_startdate = date(1999, 4, 15)
    _lc8_startdate = date(2013, 4, 1)
    _sensors = {
        'LT5': {
            'code': 'LT05',
            'description': 'Landsat 5',
            'startdate': _lt5_startdate,
            'enddate': date(2013, 1, 1),
        },
        'LE7': {
            'code': 'LE07',
            'description': 'Landsat 7',
            'startdate': _le7_startdate,
        },
        'LC8': {
            'code': 'LC08',
            'description': 'Landsat 8',
            'startdate': _lc8_startdate,
        }
    }

    _base_pattern = (
        r'^L(?P<sensor>\w)(?P<satellite>\d{2})_CU_(?P<pathrow>\d{6})'
        r'_(?P<acq_date>\d{8})_(?P<processing_date>\d{8})'
        r'_(?P<coll_num>C\d{2})_(?P<version>V\d{2})_'
    )

    _latency = 0
    _assets = {
        'ST': {
            'sensors': ['LT5', 'LE7', 'LC8'],
            'pattern': _base_pattern + r'ST\.tar$',
            'latency': _latency,
        },
    }

    _ee_datasets = None

    # Set the startdate to the min date of the asset's sensors
    for asset, asset_info in _assets.items():

        # TODO: there was some weird scope thing going on in the
        # list comprehension that was here
        startdates = []
        for sensor in asset_info['sensors']:
            startdates.append(_sensors[sensor]['startdate'])
        asset_info['startdate'] = min(startdates)

    def __init__(self, filename):
        """ Inspect a single file and get some metadata """
        super(ardAsset, self).__init__(filename)

        fname = os.path.basename(filename)

        utils.verbose_out("Attempting to load " + fname, 2)

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

       
        self.sensor = "L{}{}".format(match.group('sensor'),
                                     int(match.group('satellite')))
        self.date = datetime.strptime(match.group('acq_date'), "%Y%m%d")
        processing_date = datetime.strptime(match.group('processing_date'),
                                            '%Y%m%d')

        self.tile = match.group('pathrow')
        self.collection_number = match.group('coll_num')
        self.version = match.group('version')
        smeta = self._sensors[self.sensor]
        self.meta = {}
        self.meta['bands'] = {}

        if self.sensor not in self._sensors.keys():
            raise Exception("Sensor %s not supported: %s" % (self.sensor, filename))
        self._version = self.version

    @classmethod
    def ee_login(cls):
        if not hasattr(cls, '_ee_key'):
            username = settings().REPOS['ard']['username']
            password = settings().REPOS['ard']['password']
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
            'ARD_TILE': {
                r['name']: r['fieldId']
                for r in api.dataset_fields('ARD_TILE', 'EE', api_key)['data']
                if r['name'] in ["Tile Grid Horizontal", "Tile Grid Vertical"]
            }
        }

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
       
        # perform the query, but on a_type-source mismatch, do nothing
        horiz, vert = path_row(tile)
        fdate = date.strftime('%Y-%m-%d')
        cls.load_ee_search_keys()
        api_key = cls.ee_login()
        from usgs import api
        response = api.search(
            'ARD_TILE', 'EE',
            start_date=fdate, end_date=fdate,
            where={
                cls._ee_datasets['ARD_TILE']['Tile Grid Horizontal']: horiz,
                cls._ee_datasets['ARD_TILE']['Tile Grid Vertical']: vert,
            },
            api_key=api_key
        )['data']

        for result in response['results']:
            metadata = requests.get(result['metadataUrl']).text
            xml = ElementTree.fromstring(metadata)
            # Indexing an Element instance returns it's children
            scene_cloud_cover = xml.find(
                ".//{http://earthexplorer.usgs.gov/eemetadata.xsd}metadataField[@name='Cloud Cover']"
            )[0].text

            if float(scene_cloud_cover) < pclouds:
                return {
                    # actually used
                    'scene_id': result['entityId'],
                    'dataset': 'ARD_TILE',
                    'a_type': asset,
                    # ignored but required
                    'basename': result['displayId'] + '_{}.tar'.format(asset),
                    # ignored
                    #'scene_cloud_cover': float(scene_cloud_cover),
                    #'land_cloud_cover': float(land_cloud_cover),
                }
        return None

    @classmethod
    def download(cls, a_type, download_fp, scene_id, dataset, **ignored):
        """Fetches the ARD asset defined by the arguments."""
        stage_dir = cls.Repository.path('stage')
        api_key = cls.ee_login()
        from usgs import api
        url = api.download(
            dataset, 'EE', [str(scene_id)], a_type, api_key)['data'][0]['url']
        with utils.make_temp_dir(prefix='dwnld', dir=stage_dir) as dldir:
            homura.download(url, dldir)
            granules = os.listdir(dldir)
            if len(granules) == 0:
                raise Exception("Download didn't seem to"
                                " produce a file:  {}".format(str(granules)))
            os.rename(os.path.join(dldir, granules[0]), download_fp)
        return True

    def version_text(self):
        return '{v}-{s}'.format(v=self.version, s=self.stability)

class ardData(CloudCoverData):
    name = 'ARD'
    version = __version__
    Asset = ardAsset
    inline_archive = True

    _lt5_startdate = date(1984, 3, 1)
    _products = {
        'st': {
            'description': 'Surface Temperature',
            'assets': ['ST'],
            'startdate': Asset._lt5_startdate,
            'latency': Asset._latency,
        },
    }

    @Data.proc_temp_dir_manager
    def process(self, products=None, *args, **kwargs):
        """ Make sure all products have been processed """
        products = super(ardData, self).process(products, *args, **kwargs)
        if len(products) == 0:
            utils.verbose_out("Skipping processing; no products requested.", 5)
            return
        if len(self.assets) == 0:
            utils.verbose_out("Skipping processing; no assets found.", 5)
            return

        for pr in products.products:
            # ARD is a product/asset pair, so always use the first (only) asset
            asset = self.assets[self._products[pr]['assets'][0].upper()]
            product_name = os.path.basename(
                asset.filename
            ).split('.')[0] + ".tif"

            fname = self.temp_product_filename(asset.sensor, 'st')
            temp_dir = os.path.dirname(fname)
            out_name = os.path.basename(fname)
            tarfile.open(asset.filename).extractall(path=temp_dir)
            os.rename(
                os.path.join(temp_dir, product_name),
                os.path.join(temp_dir, out_name)
            )
            self.archive_temp_path(fname)