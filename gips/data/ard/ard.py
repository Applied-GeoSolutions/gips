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
#
#   PRISM Climate data is copyrighted by the PRISM Climate Group,
#   Oregon State University.  For information acceptable use, see
#   http://prism.oregonstate.edu/documents/PRISM_terms_of_use.pdf.
################################################################################

import os
from datetime import datetime, date, timedelta
from csv import DictReader
import re
import ftplib
import subprocess
import tempfile
import requests
from gips.core import SpatialExtent, TemporalExtent
from xml.etree import ElementTree
from backports.functools_lru_cache import lru_cache

from gips.data.core import Repository, Data
import gips.data.core

from gips.utils import settings, List2File
from gips import utils

from gippy import GeoImage

from numpy import mean
import homura

__author__ = "Rick Emery <remery@ags.io>"
__version__ = '0.1.0'

def path_row(tile_id):
    """Converts the given landsat tile string into (path, row)."""
    return (tile_id[:3], tile_id[3:])

class ardRepository(Repository):
    name = 'ARD'
    description = 'Landsat Analysis Ready Data'
    _datedir = '%Y%m%d'
    _tile_attribute = 'PR'


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

    _c1_base_pattern = (
        r'^L(?P<sensor>\w)(?P<satellite>\d{2})_CU_(?P<pathrow>\d{6})'
        r'_(?P<acq_date>\d{8})_(?P<processing_date>\d{8})_C01_V01_'
    )

    _latency = 0
    _assets = {
        'ST': {
            'sensors': ['LT5', 'LE7', 'LC8'],
            'pattern': _c1_base_pattern + r'ST_\.tar$',
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
        """ Inspect a PRISM file """
        super(ardAsset, self).__init__(filename)
        bname = os.path.basename(filename)
        # 'PRISM_<var>_<stability>_<scale&version>_<time period>_bil.zip'
        _, variable, stability, scalever, date, bilzip = bname.split('_')
        assert bilzip == 'bil.zip', "didn't tokenize properly."
        scale = re.sub(r'(.+)D[0-9]+', r'\1', scalever)
        version = re.sub(r'.+(D[0-9]+)', r'\1', scalever)
        self.date = datetime.strptime(date, '%Y%m%d').date()
        self.asset = '_' + variable
        self.sensor = 'prism'
        self.scale = scale
        self.version = version
        self.stability = stability
        self._version = self._stab_score[self.stability] * .01 + int(self.version[1:])
        # only one tile
        self.tile = 'CONUS'

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
                    'basename': result['displayId'] + '.tar.gz',
                    # ignored
                    #'scene_cloud_cover': float(scene_cloud_cover),
                    #'land_cloud_cover': float(land_cloud_cover),
                }
        return None

    @classmethod
    def download(cls, a_type, download_fp, scene_id, dataset, **ignored):
        """Fetches the C1 asset defined by the arguments."""
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

    def datafiles(self):
        datafiles = super(ardAsset, self).datafiles()
        datafiles = [d for d in datafiles if d.lower().endswith('.bil')]
        if len(datafiles) > 0:
            indexfile = self.filename + '.index'
            utils.verbose_out('indexfile: {}'.format(indexfile), 3)
            List2File(datafiles, indexfile)
            return datafiles

    @classmethod
    def choose_asset(cls, a_type, tile, date, remote_fn_list):
        """Choose the most favorable stability & version (often only one)."""
        return max(
               (fn for fn in remote_fn_list if date.strftime('%Y%m%d') in fn),
               key=(lambda x: ardAsset(x)._version))


class ardData(Data):
    """ A tile (CONUS State) of PRISM """
    name = 'ARD'
    version = __version__
    Asset = ardAsset
    inline_archive = True

    _lt5_startdate = date(1984, 3, 1)
    # Prism official docs at http://www.prism.oregonstate.edu/FAQ/ say:
    # "Dataset values are stored . . . precipitation as millimeters and
    # temperature as degrees Celsius."
    _products = {
        'ST': {
            'description': 'Surface Temperature',
            'assets': ['ST'],
            'bands': [{'name': 'ppt', 'units': 'mm'}],
            'startdate': Asset._lt5_startdate,
            'latency': Asset._latency,
        },
    }

    @classmethod
    def normalize_tile_string(cls, tile_string):
        """'conus' is invalid, but 'CONUS' is valid, so help the user out."""
        return tile_string.upper()

    def process(self, *args, **kwargs):
        """Deduce which products need producing, then produce them."""
        products = super(ardData, self).process(*args, **kwargs)
        if len(products) == 0:
            return
        # overwrite = kwargs.get('overwrite', False)
        # utils.verbose_out('\n\noverwrite = {}\n'.format(overwrite), 2)
        # TODO: overwrite doesn't play well with pptsum -- wonder if it would
        #       if it was made into a composite product (which it is)
        assert len(ardAsset._sensors) == 1  # sanity check to force this code to stay current
        sensor = list(ardAsset._sensors.keys())[0]

        def get_bil_vsifile(d, a):
            with utils.error_handler('Error accessing asset {}'
                                     .format(d), continuable=True):
                return os.path.join(
                    '/vsizip/' + d.assets[a].filename,
                    d.assets[a].datafiles()[0])

        for key, val in products.requested.items():
            start = datetime.now()
            # check that we have required assets
            requiredassets = self.products2assets([val[0]])
            # val[0] s.b. key w/o product args
            description = self._products['pptsum']['description']
            missingassets = []
            availassets = []
            vsinames = {}

            for asset in requiredassets:
                bil = get_bil_vsifile(self, asset)
                if bil is None:
                    missingassets.append(asset)
                else:
                    availassets.append(asset)
                    vsinames[asset] = os.path.join(
                        '/vsizip/' + self.assets[asset].filename,
                        bil
                    )

            if not availassets:
                utils.verbose_out(
                    'There are no available assets ({}) on {} for tile {}'
                    .format(str(missingassets), str(self.date), str(self.id)),
                    5,
                )
                continue
            prod_fn = '{}_{}_{}.tif'.format(self.basename, 'prism', key)
            archived_fp = os.path.join(self.path, prod_fn) # final destination
            if val[0] in ['ppt', 'tmin', 'tmax', 'vrtppt']:
                with self.make_temp_proc_dir() as tmp_dir:
                    tmp_fp = os.path.join(tmp_dir, prod_fn)
                    if val[0] == 'vrtppt':
                        subprocess.check_call([
                            'gdalbuildvrt',
                            tmp_fp,
                            vsinames[self._products[key]['assets'][0]],
                        ])
                    else:
                        os.symlink(vsinames[self._products[key]['assets'][0]], tmp_fp)
                    os.rename(tmp_fp, archived_fp)
            elif val[0] == 'pptsum':
                if len(val) < 2:
                    lag = 3 # no argument provided, use default lag of 3 days SB configurable.
                    prod_fn = re.sub(r'\.tif$', '-{}.tif'.format(lag), prod_fn)
                    archived_fp = os.path.join(self.path, prod_fn) # have to regenerate, sigh
                    utils.verbose_out('Using default lag of {} days.'.format(lag), 2)
                else:
                    with utils.error_handler("Error for pptsum lag value '{}').".format(val[1])):
                        lag = int(val[1])

                date_spec = '{},{}'.format(
                    datetime.strftime(
                        self.date - timedelta(days=lag), '%Y-%m-%d',
                    ),
                    datetime.strftime(self.date, '%Y-%m-%d'),
                )
                inv = self.inventory(dates=date_spec, products=['ppt'],)
                inv.process()
                # because DataInventory object doesn't update
                inv = self.inventory(dates=date_spec, products=['ppt'],)
                if len(inv.data) < lag:
                    utils.verbose_out(
                        '{}: requires {} preceding days ppt ({} found).'
                        .format(key, lag, len(inv.data)),
                        3,
                    )
                    continue  # go to next product to process
                imgs = []
                asset_fns = [] # have to grab filenames for multiple days
                for tileobj in inv.data.values():
                    data_obj = next(iter(tileobj.tiles.values()))
                    asset_fns.append(os.path.basename(data_obj.assets['_ppt'].filename))
                    imgs.append(GeoImage(get_bil_vsifile(data_obj, '_ppt')))

                with self.make_temp_proc_dir() as tmp_dir:
                    tmp_fp = os.path.join(tmp_dir, prod_fn)
                    oimg = GeoImage.create_from(imgs[0], tmp_fp)
                    oimg.set_nodata(-9999)
                    oimg.set_bandname(
                        description + '({} day window)'.format(lag), 1
                    )
                    oimg.add_meta(self.prep_meta(sorted(asset_fns)))
                    for chunk in oimg.chunks():
                        oarr = oimg[0].read(chunk) * 0.0 # wat
                        for img in imgs:
                            oarr += img[0].read(chunk)
                        oimg[0].write(oarr, chunk)
                    oimg.save()
                    os.rename(tmp_fp, archived_fp)
                oimg = None  # help swig+gdal with GC
            self.AddFile(sensor, key, archived_fp)  # add product to inventory
        return products
