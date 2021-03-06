#!/usr/bin/env python
################################################################################
#    GIPS PRISM data module
#
#    AUTHOR: Ian Cooke
#    EMAIL:  ircwaves@gmail.com
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
from gips.core import SpatialExtent, TemporalExtent

from gips.data.core import Repository, Data
import gips.data.core

from gips.utils import settings, List2File
from gips import utils

from gippy import GeoImage

from numpy import mean

__author__ = "Ian Cooke <icooke@ags.io>"
__version__ = '0.1.1'


class prismRepository(Repository):
    name = 'PRISM'
    description = 'PRISM Gridded Climate Data'
    _datedir = '%Y%m%d'
    _tile_attribute = 'id'


class prismAsset(gips.data.core.FtpAsset):
    Repository = prismRepository
    _sensors = {
        'prism': {'description': 'Daily Gridded Climate Data'}
    }
    _defaultresolution = [4000.0, 4000.0]
    _startdate = date(1981, 1, 1)
    _latency = -7
    # LATENCY (approximate)
    # 6 months for stable
    # 1 month for early
    # 1 week for provisional
    _host = 'prism.nacse.org'
    _assets = {
        '_ppt': {
            'pattern': r'^PRISM_ppt_.+?\.zip$',
            'ftp-basedir': '/daily/ppt',
            'startdate': _startdate,
            'latency': _latency,
        },
        '_tmin': {
            'pattern': r'^PRISM_tmin_.+?\.zip$',
            'ftp-basedir': '/daily/tmin',
            'startdate': _startdate,
            'latency': _latency,
        },
        '_tmax': {
            'pattern': r'^PRISM_tmax_.+?\.zip$',
            'ftp-basedir': '/daily/tmax',
            'startdate': _startdate,
            'latency': _latency,
        },
    }
    _stab_score = {
        'stable': 3,
        'provisional': 2,
        'early': 1,
    }

    def __init__(self, filename):
        """ Inspect a PRISM file """
        super(prismAsset, self).__init__(filename)
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

    def version_text(self):
        return '{v}-{s}'.format(v=self.version, s=self.stability)

    def datafiles(self):
        datafiles = super(prismAsset, self).datafiles()
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
               key=(lambda x: prismAsset(x)._version))


class prismData(Data):
    """ A tile (CONUS State) of PRISM """
    name = 'PRISM'
    version = __version__
    Asset = prismAsset
    inline_archive = True
    # Prism official docs at http://www.prism.oregonstate.edu/FAQ/ say:
    # "Dataset values are stored . . . precipitation as millimeters and
    # temperature as degrees Celsius."
    _products = {
        'ppt': {
            'description': 'Precipitate',
            'assets': ['_ppt'],
            'bands': [{'name': 'ppt', 'units': 'mm'}],
            'startdate': Asset._startdate,
            'latency': Asset._latency,
        },
        'vrtppt': {
            'description': 'Precipitate (vrt)',
            'assets': ['_ppt'],
            'bands': [{'name': 'ppt', 'units': 'mm'}],
            'startdate': Asset._startdate,
            'latency': Asset._latency,
        },
        'pptsum': {
            'description': 'Cumulative Precipitate',
            'assets': ['_ppt'],
            'bands': [{'name': 'pptsum', 'units': 'mm'}],
            'arguments': ['days: temporal window width (default: 3 days)'],
            'startdate': Asset._startdate,
            'latency': Asset._latency,
        },
        'tmin': {
            'description': 'Daily Minimum Temperature',
            'assets': ['_tmin'],
            'bands': [{'name': 'tmin', 'units': 'degree Celcius'}],
            'startdate': Asset._startdate,
            'latency': Asset._latency,
        },
        'tmax': {
            'description': 'Daily Maximum Temperature',
            'assets': ['_tmax'],
            'bands': [{'name': 'tmin', 'units': 'degree Celcius'}],
            'startdate': Asset._startdate,
            'latency': Asset._latency,
        },
    }

    @classmethod
    def normalize_tile_string(cls, tile_string):
        """'conus' is invalid, but 'CONUS' is valid, so help the user out."""
        return tile_string.upper()

    def process(self, *args, **kwargs):
        """Deduce which products need producing, then produce them."""
        products = super(prismData, self).process(*args, **kwargs)
        if len(products) == 0:
            return
        # overwrite = kwargs.get('overwrite', False)
        # utils.verbose_out('\n\noverwrite = {}\n'.format(overwrite), 2)
        # TODO: overwrite doesn't play well with pptsum -- wonder if it would
        #       if it was made into a composite product (which it is)
        assert len(prismAsset._sensors) == 1  # sanity check to force this code to stay current
        sensor = list(prismAsset._sensors.keys())[0]

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
