#!/usr/bin/env python
################################################################################
#    SMAP: Soil Moisture Active Passive
#
#    AUTHOR: Subit Chakrabarti
#    EMAIL:  chakrabarti.subit@gmail.com
################################################################################

import os
import sys
import re
import datetime

import urllib

import math
import numpy as np
import requests

import gippy
from gips.data.core import Repository, Asset, Data
from gips.utils import VerboseOut, settings
from gips import utils


class smapRepository(Repository):
    name = 'SMAP'
    description = 'Soil Moisture Active Passive (SMAP)'

    # NASA assets require special authentication
    _manager_url = "https://urs.earthdata.nasa.gov"
    _tile_attribute = 'tileid'

class smapAsset(Asset):
    Repository = smapRepository
    _sensors = {'RAD': {'description': 'Soil Moisture Active Passive Radiometer'}}
    _assets = {
        'SM_P_E': {
            'url': 'https://n5eil01u.ecs.nsidc.org/SMAP/SPL3SMP_E.003',
            'pattern': r'^SMAP\_.{2}\_SM\_P\_E\_.{8}\_.{6}\_.{3}\.h5$',
            'description': 'Passive Enhanced Radiometer Based SM at 9KM',
            'startdate': datetime.date(2015, 3, 31),
            'latency': 1,
        },
        'SM_P': {
            'url': 'https://n5eil01u.ecs.nsidc.org/SMAP/SPL3SMP.006',
            'pattern': r'^SMAP\_.{2}\_SM\_P\_.{8}\_.{6}\_.{3}\.h5$',
            'description': 'Passive Original Radiometer Based SM at 36KM',
            'startdate': datetime.date(2015, 3, 31),
            'latency': 1,
        },
    }

    def __init__(self, filename):
        """ Inspect a single file and get some metadata """
        super(smapAsset, self).__init__(filename)

        bname = os.path.basename(filename)
        self.asset = (re.search(r'(?<=SMAP_L3_)\w*(?=_[0-9]{8})', bname)).group(0)
        date_here = (re.search(r'[0-9]{8}', bname)).group(0)
        self.date = datetime.datetime.strptime(date_here, "%Y%m%d").date()
        self._version = (re.search(r'R[0-9]*', bname)).group(0)
        self.tile = 'h01v01'

    @classmethod
    def query_provider(cls, asset, tile, date):
        """Query the SMAP servers for assets for the given tile & date.

        Returns (base-filename, url).
        """
        mainurl = "%s/%s" % (cls._assets[asset]['url'], str(date.strftime('%Y.%m.%d')))
        pattern = r'SMAP\_.{2}\_%s\_%s\_.{6}\_.{3}\.h5' % (asset, str(date.strftime('%Y%m%d')))
        with utils.error_handler("Error downloading: " + mainurl):
            basename = cls.Repository.find_pattern_in_url(mainurl, pattern, verbosity=2)
        if basename == None:
            return None, None
        return basename, '/'.join([mainurl, basename])

    @classmethod
    def fetch(cls, asset, tile, date):
        qs_rv = cls.query_service(asset, tile, date)
        if qs_rv is None:
            return []
        basename, url = qs_rv['basename'], qs_rv['url']
        with utils.error_handler(
                "Asset fetch error ({})".format(url), continuable=True):
            response = cls.Repository.managed_request(url)
            if response is None:
                return []
            outpath = os.path.join(cls.Repository.path('stage'), basename)
            with open(outpath, 'wb') as fd:
                fd.write(response.read())
            utils.verbose_out('Retrieved ' + basename, 2)
            return [outpath]
        return []

class smapData(Data):
    """ A tile of data (all assets and products) """
    name = 'SMAP'
    version = '1.0.0'
    Asset = smapAsset

    _projection = 'PROJCS["unnamed",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],TOWGS84[0,0,0,0,0,0,0],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9108"]],AUTHORITY["EPSG","4326"]],PROJECTION["Cylindrical_Equal_Area"],PARAMETER["standard_parallel_1",30],PARAMETER["central_meridian",0],PARAMETER["false_easting",0],PARAMETER["false_northing",0],UNIT["Meter",1],AUTHORITY["epsg","6933"]]'
    _products = {
        'smp': {
            'description': 'SMAP SM AM Acquisiton posted on native grid ',
            # the list of asset types associated with this product
            'assets': ['SM_P'],  # , 'MYD08'],
            'startdate': datetime.date(2015, 3, 31),
            'sensor': 'RAD',
            'latency': 1,
            '_geotransform': (-17367530.44516138, 36032.220850622405123, 0, 7314540.79258289, 0, -36032.217290640393912),
        },
        'smpe': {
            'description': 'SMAP SM AM Acquisiton posted on enhanced 9km grid',
            # the list of asset types associated with this product
            'assets': ['SM_P_E'],  # , 'MYD08'],
            'startdate': datetime.date(2015, 3, 31),
            'sensor': 'RAD',
            'latency': 1,
            '_geotransform': (-17367530.44516138, 9000.0, 0, 7314540.79258289, 0, -9000.0),
        }
    }

    def asset_check(self, prod_type):
        """Is an asset available for the current scene and product?

        Returns the last found asset, or else None, its version, the
        complete lists of missing and available assets, and lastly, an array
        of pseudo-filepath strings suitable for consumption by gdal/gippy.
        """
        # return values
        asset = None
        missingassets = []
        availassets = []
        allsds = []

        for asset in self._products[prod_type]['assets']:
            # many asset types won't be found for the current scene
            if asset not in self.assets:
                missingassets.append(asset)
                continue
            try:
                sds = self.assets[asset].datafiles()
            except Exception as e:
                utils.report_error(e, 'Error reading datafiles for ' + asset)
                missingassets.append(asset)
            else:
                availassets.append(asset)
                allsds.extend(sds)

        return asset, missingassets, availassets, allsds

    @Data.proc_temp_dir_manager
    def process(self, *args, **kwargs):
        """Produce requested products."""
        products = super(smapData, self).process(*args, **kwargs)
        if len(products) == 0:
            return
        # example products.requested:
        # {'temp8tn': ['temp8tn'], 'clouds': ['clouds'], . . . }
        # key is only used once far below, and val is only used for val[0].
        for key, val in products.requested.items():
            start = datetime.datetime.now()
            prod_type = val[0]
            asset, missingassets, availassets, allsds = \
                self.asset_check(prod_type)

            if not availassets:
                # some products aren't available for every day but this is trying every day
                VerboseOut('There are no available assets (%s) on %s for tile %s'
                           % (str(missingassets), str(self.date), str(self.id),), 5)
                continue

            sensor = self._products[prod_type]['sensor']
            fname = self.temp_product_filename(sensor, prod_type)  # moved to archive at end of loop

            if val[0] == 'smp':
                img = gippy.GeoImage(allsds[15])
            elif val[0] == 'smpe':
                img = gippy.GeoImage(allsds[13])

            # TODO: This is broken - GeoImage.create() apparently doesn't support datatypes
            imgdata = img.read()
            imgout = gippy.GeoImage.create(fname, img.xsize(), img.ysize(), 1, 'float32')
            del img
            imgout.set_nodata(-9999.0)
            imgout.set_offset(0.0)
            imgout.set_gain(1.0)
            imgout.set_bandname('Soil Moisture', 1)
            imgout.set_srs(self._projection)
            imgout.set_affine(np.array(self._products[prod_type]['_geotransform']))
            imgout[0].write(imgdata)
            # add product to inventory
            archive_fp = self.archive_temp_path(fname)
            self.AddFile(sensor, key, archive_fp)
            del imgout  # to cover for GDAL's internal problems
            utils.verbose_out(' -> {}: processed in {}'.format(
                os.path.basename(fname), datetime.datetime.now() - start), level=1)
