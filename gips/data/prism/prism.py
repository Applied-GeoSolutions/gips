#!/usr/bin/env python
################################################################################
#    GIPS PRISM data module
#
#    AUTHOR: Ian Cooke
#    EMAIL:  ircwaves@gmail.com
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
import tempfile
from gips.core import SpatialExtent, TemporalExtent

from gips.data.core import Repository, Asset, Data

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
    _defaultresolution = [4000.0, 4000.0]
    _tile_attribute = 'id'


class prismAsset(Asset):
    Repository = prismRepository
    _sensors = {
        'prism': {'description': 'Daily Gridded Climate Data'}
    }
    _startdate = date(1981, 1, 1)
    # LATENCY (approximate)
    # 6 months for stable
    # 1 month for early
    # 1 week for provisional
    _assets = {
        '_ppt': {
            'pattern': r'PRISM_ppt_.+?\.zip$',
            'url': 'ftp://prism.nacse.org/daily/ppt/',
            'startdate': _startdate,
            'latency': -7
        },
        '_tmin': {
            'pattern': r'PRISM_tmin_.+?\.zip$',
            'url': 'ftp://prism.nacse.org/daily/tmin/',
            'startdate': _startdate,
            'latency': -7
        },
        '_tmax': {
            'pattern': r'PRISM_tmax_.+?\.zip$',
            'url': 'ftp://prism.nacse.org/daily/tmax/',
            'startdate': _startdate,
            'latency': -7
        },
    }
    _stab_score = {
        'stable': 3,
        'early': 2,
        'provisional': 1,
    }

    @classmethod
    def fetch_ftp(cls, asset, tile, date):
        """ Fetch via FTP """
        url = cls._assets[asset].get('url', '')
        if url == '':
            raise Exception("%s: URL not defined for asset %s" % (cls.__name__, asset))
        utils.verbose_out('%s: fetch tile %s for %s' % (asset, tile, date), 3)
        if url.startswith('ftp://'):
            url = url[6:]  # drop ftp:// if given
        ftpurl = url.split('/')[0]
        ftpdir = url[len(ftpurl):]
        try:
            ftp = ftplib.FTP(ftpurl)
            ftp.login('anonymous', settings().EMAIL)
            pth = os.path.join(ftpdir, date.strftime('%Y'))
            ftp.set_pasv(True)
            ftp.cwd(pth)

            filenames = []
            ftp.retrlines('LIST', filenames.append)
            filenames = map(lambda x: x.split(' ')[-1], filenames)
            filenames = filter(
                lambda x: date.strftime('%Y%m%d') in x,
                filenames
            )
            if len(filenames) > 1:
                filenames = sorted(filenames, key=lambda x: prismAsset(x).ver_stab, reverse=True)
            filename = filenames[0]
            stagedir = tempfile.mkdtemp(
                prefix='prismDownloader',
                dir=cls.Repository.path('stage')
            )
            ofilename = os.path.join(stagedir, filename)
            utils.verbose_out("Downloading %s" % filename, 2)
            with open(ofilename, "wb") as ofile:
                ftp.retrbinary('RETR %s' % filename, ofile.write)
            ftp.close()
        except Exception, e:
            # TODO error-handling-fix: with handler BUT mind the else
            raise Exception("Error downloading: %s" % e)
        else:
            assets = cls.archive(stagedir)
        try:
            os.remove(ofilename)
        except OSError as ose:
            # TODO error-handling-fix: change to 'raise'
            if ose.errno != 2:
                raise ose
        os.rmdir(stagedir)

    @classmethod
    def fetch(cls, asset, tile, date):
        """ Get this asset for this tile and date (via FTP) """
        cls.fetch_ftp(asset, tile, date)

    def __init__(self, filename):
        """ Inspect a PRISM file """
        super(prismAsset, self).__init__(filename)
        bname = os.path.basename(filename)
        # 'PRISM_<var>_<stability>_<scale&version>_<time period>_bil.zip'
        _, variable, stability, scalever, date, bilzip = bname.split('_')
        assert bilzip == 'bil.zip', "didn't tokenize properly."
        scale = re.sub(r'(.+)D[0-9]+', r'\1', scalever)
        version = re.sub(r'.+(D[0-9]+)', r'\1', scalever)
        self.date = datetime.strptime(date, '%Y%m%d')
        self.asset = '_' + variable
        self.sensor = 'prism'
        self.scale = scale
        self.version = version
        self.stability = stability
        self.ver_stab = self._stab_score[self.stability] * .01 + int(self.version[1:])
        # only one tile
        self.tile = 'CONUS'

    def updated(self, newasset):
        '''
        Compare the version for this to that of newasset.
        Return true if newasset version is greater.
        '''
        return (self.sensor == newasset.sensor and
                self.tile == newasset.tile and
                self.date == newasset.date and
                self.asset == self.asset and
                self.ver_stab < newasset.ver_stab)

    def datafiles(self):
        datafiles = super(prismAsset, self).datafiles()
        datafiles = filter(lambda x: x.lower().endswith('.bil'), datafiles)
        if len(datafiles) > 0:
            indexfile = self.filename + '.index'
            utils.verbose_out('indexfile: {}'.format(indexfile), 3)
            List2File(datafiles, indexfile)
            return datafiles


class prismData(Data):
    """ A tile (CONUS State) of PRISM """
    name = 'PRISM'
    version = __version__
    Asset = prismAsset
    _products = {
        'ppt': {
            'description': 'Precipitate',
            'assets': ['_ppt'],
        },
        'pptsum': {
            'description': 'Cumulative Precipitate',
            'assets': ['_ppt'],
            'arguments': [
                'days: temporal window width (default: 3 days) .',
            ]
        },
        'tmin': {
            'description': 'Daily Minimum Temperature',
            'assets': ['_tmin']
        },
        'tmax': {
            'description': 'Daily Maximum Temperature',
            'assets': ['_tmax']
        },
    }

    def process(self, *args, **kwargs):
        """Deduce which products need producing, then produce them."""
        products = super(prismData, self).process(*args, **kwargs)
        if len(products) == 0:
            return
        # overwrite = kwargs.get('overwrite', False)
        # utils.verbose_out('\n\noverwrite = {}\n'.format(overwrite), 2)
        # TODO: overwrite doesn't play well with pptsum -- wonder if it would
        #       if it was made into a composite product (which it is)
        bname = os.path.join(self.path, self.basename)
        assert len(prismAsset._sensors) == 1  # sanity check to force this code to stay current
        sensor = prismAsset._sensors.keys()[0]

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
            fname = '{}_{}_{}.tif'.format(bname, 'prism', key)
            if val[0] in ['ppt', 'tmin', 'tmax']:
                if os.path.lexists(fname):
                    os.remove(fname)
                os.symlink(vsinames[self._products[key]['assets'][0]], fname)
            elif val[0] == 'pptsum':
                try:
                    lag = int(val[1])
                except ValueError, TypeError:
                    # TODO error-handling-fix:
                    #   refactor IndexError to be a conditional
                    #   use with handler for other types
                    raise Exception(
                        'pptsum argument format error (given: {}).'
                    )
                except IndexError:
                    # no argument provided, use
                    # default lag of 3 days SB configurable.
                    lag = 3
                    fname = re.sub(r'\.tif$', '-{}.tif'.format(lag), fname)
                    utils.verbose_out('Using default lag of {} days.'
                                      .format(lag), 2)

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
                for tileobj in inv.data.values():
                    datobj = tileobj.tiles.values()[0]
                    imgs.append(GeoImage(get_bil_vsifile(datobj, '_ppt')))

                if os.path.exists(fname):
                    os.remove(fname)

                oimg = GeoImage(fname, imgs[0])
                for chunk in oimg.Chunks():
                    oarr = oimg[0].Read(chunk) * 0.0
                    for img in imgs:
                        oarr += img[0].Read(chunk)
                    oimg[0].Write(oarr, chunk)
                oimg.Process()
                oimg = None  # help swig+gdal with GC
                products.requested.pop(key)
            self.AddFile(sensor, key, fname)  # add product to inventory
        return products
