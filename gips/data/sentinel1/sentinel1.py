#!/usr/bin/env python
################################################################################
#    GIPS: Geospatial Image Processing System
#
#    Copyright (C) 2017 Applied Geosolutions
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
import shutil
import datetime
import shlex
import re
import subprocess
import glob
from functools import lru_cache

#import geopandas as gpd  # MOVED TO LOCAL IMPORT

import gippy

from gips.data.core import Repository, Asset, Data
from gips import utils
from gips.data.sentinel1.tiles import write_feature, make_tilegrid, make_rectangular_tilegrid
import sentinel_api as api


_asset_types = ('L1',)


def command(cmd):
    # this is dumb but gets reused a lot
    args = shlex.split(cmd)
    p = subprocess.Popen(args)
    p.communicate()
    if p.returncode != 0:
        raise IOError("Expected exit status 0, got {}".format(p.returncode))


class sentinel1Repository(Repository):
    #if not os.path.exists('/usr/bin/gpt'):
    #    raise Exception('SNAP GPT not installed')

    name = 'Sentinel1'
    description = 'Data from the Sentinel 1 satellite(s) from the ESA'

    _tile_attribute = 'Name'

    default_settings = {
        'source': 'esa',
        'extract': False,
    }

    # the default tile ID
    _tile_attribute = "tileid"
    _tilefile_pattern = "tile_{}.shp"
    _tilefile_name = None

    @classmethod
    def validate_setting(cls, key, value):
        if key == 'source' and value not in ('esa', 'gs'):
            raise ValueError("Sentinel-1's 'source' setting is '{}',"
                    " but valid values are 'esa' or 'gs'".format(value))
        return value


    @classmethod
    def vector2tiles(cls, vector, *args, **kwargs):
        """
        make a tilegrid on the fly and get the list of tiles
        tilefile is called /archive/sentinel1/stage/tile_{}_{}.shp
        """
        outdir = cls.path("stage")
        tileid_pattern = "{}-{}"
        outname = "tiles.shp"
        featurepath = os.path.join(outdir, 'feature.shp')
        write_feature(vector, featurepath)

        if cls._tilefile_name is not None:
            tilelist = make_tilegrid(featurepath, outdir, outname, tileid_pattern, cls._tile_attribute,
                                     append=True)
        else:
            tilelist = make_tilegrid(featurepath, outdir, outname, tileid_pattern, cls._tile_attribute)

        # TODO: use temp file
        for file in glob.glob(os.path.splitext(featurepath)[0] + '.*'):
            os.remove(file)

        cls._tilefile_name = os.path.join(outdir, outname)
        print('cls._tilefile_name', cls._tilefile_name)
        return {k: (1,1) for k in tilelist}


class sentinel1Asset(Asset):
    Repository = sentinel1Repository
    _sensors = {
        'S1': {
            'description': 'Sentinel-1, Satellite',
            'band-strings':
                ['01', '02'],
            'polarization':
                ('VV', 'VH'),
            # band location in GHz
            'bandlocs':
                ['5.405', '5.405'],
            'spatial-resolutions':
                [20, 20],
        },
    }

    _asset_pat_base = 'S1_IW_GRDH_(?P<year>\d{4})(?P<mon>\d{2})(?P<day>\d{2})_(?P<tile>\w{3}-\w{3})\.tif'

    _start_date = datetime.date(2015, 1, 1)

    _assets = {
        'L1': {
            'source': 'esa',
            # 'pattern' is used for searching the repository of locally-managed assets
            'pattern': _asset_pat_base,
            'startdate': _start_date,
            'latency': 3,
        },
    }

    # default resultant resolution for resampling during to Data().copy()

    def __init__(self, filename):
        """Inspect a single file and set some metadata.
        """
        super(sentinel1Asset, self).__init__(filename)

        self.basename = os.path.basename(filename)
        match = re.match(self._asset_pat_base, self.basename)

        self.asset = "L1"
        self.sensor = "S1"

        self.tile = match.group('tile')
        self.date = datetime.date(*[int(i) for i in match.group('year', 'mon', 'day')])
        self._version = int(''.join(
            match.group('year', 'mon', 'day')
        ))
        self.meta = {} # for caching asset metadata values
        self.tile_meta = None # tile metadata; dict was not good for this


    @classmethod
    def query_gs(cls, tile, date):
        raise Exception('query_gs not implemented')

    @classmethod
    def query_esa(cls, tile, date):

        # use username and password for ESA DATA Hub authentication
        username = cls.get_setting('username')
        password = cls.get_setting('password')

        # All historic Sentinel-1 scenes: https://scihub.copernicus.eu/dhus/
        downloader = api.SentinelDownloader(username, password,
            api_url='https://scihub.copernicus.eu/apihub/')

        # get the scene name and use it for caching
        # load geometries from shapefile

        # this will be the shapefile containing a single tile boundary
        outfile = cls.Repository._tilefile_pattern.format(tile)
        outdir = os.path.join(cls.Repository.path(), 'stage')
        outpath = os.path.join(outdir, outfile)

        if cls.Repository._tilefile_name is not None:
            # when -s option is used
            import geopandas as gpd
            gdf = gpd.read_file(cls.Repository._tilefile_name)
            gdf = gdf[gdf['tileid'] == tile]
            # IMPORTANT: outfile is the name of the single tile boundaru
            gdf.to_file(outpath)
        else:
            rectfile = make_rectangular_tilegrid(outdir, tile, 1, 1, 'tileid', filename=outfile)
            assert rectfile == outpath

        print('loading file outpath!', outpath)
        downloader.load_sites(outpath)
        datestr = date.date().isoformat()

        # search for scenes with some restrictions (e.g., minimum overlap 1%)
        downloader.search('S1A*', min_overlap=0.01, start_date=datestr, end_date=datestr,
                  date_type='beginPosition', productType='GRD', sensoroperationalmode='IW')

        # # add another search query (e.g., for Sentinel-1B); both search results will be merged
        downloader.search('S1B*', min_overlap=0.01, start_date=datestr, end_date=datestr,
                  date_type='beginPosition', productType='GRD', sensoroperationalmode='IW')

        print('len(downloader.get_scenes())', len(downloader.get_scenes()))

        if len(downloader.get_scenes()) == 0:
            print('returning None')
            return None
        else:
            basename = 'S1_IW_GRDH_{}_{}.tif'.format(date.date().strftime('%Y%m%d'), tile)
            print('returning', basename)
            return {'basename': basename, 'downloader': downloader, 'url': ''}

    @classmethod
    @lru_cache(maxsize=100) # cache size chosen arbitrarily
    def query_service(cls, asset, tile, date, pclouds=100, **ignored):
        """as superclass, but bifurcate between google and ESA sources."""
        if not cls.available(asset, date):
            return None
        source = cls.get_setting('source')
        if cls._assets[asset]['source'] != source:
            return None
        rv = {'esa': cls.query_esa,
              'gs':  cls.query_gs, }[source](tile, date)
        utils.verbose_out(
            'queried ATD {} {} {}, found '.format(asset, tile, date)
            + ('nothing' if rv is None else rv['basename']), 5)
        if rv is None:
            return None
        rv['a_type'] = asset
        return rv


    @classmethod
    def download(cls, a_type, download_fp, downloader, **kwargs):
        """Download from the configured source for the asset type."""
        import gdal
        gdal.UseExceptions()

        # cache the processed downloaded tif
        # the downloaded data is not the asset file

        from shapely.wkt import loads

        graph_xml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Basic2Preprocess.xml")
        stagedir = cls.Repository.path("stage")

        # downloaddir is a temp dir created by gips core
        downloaddir, assetfile = os.path.split(download_fp)
        downloader.set_download_dir(downloaddir)
        print(downloaddir)

        # prefix names for all the scenes
        scenes = [s['identifier'] for s in downloader.get_scenes()]

        # these are the tif files that are staged
        downloadfiles = [os.path.join(stagedir, s + '.zip') for s in scenes]

        if not all([os.path.exists(p) for p in downloadfiles]):
            print('not all paths exist')
            if any([os.path.exists(p) for p in downloadfiles]):
                print('but some paths exist')

                # if the download already exists, then remove it from the request
                downloader._SentinelDownloader__scenes = [
                    s for s in downloader._SentinelDownloader__scenes \
                    if not os.path.exists(os.path.join(stagedir, s['identifier'] + '.zip'))
                ]

                # reset important variables - this is pretty bad, can I just do this one time?
                scenes = [s['identifier'] for s in downloader.get_scenes()]
                downloadfiles = [os.path.join(stagedir, s + '.zip') for s in scenes]

            print('about to download', downloadfiles)
            result = downloader.download_all()
            print(result)
            if not len(result['success']) == len(scenes):
                print(
                    'Warning: number of successfully downloaded files: {}'.format(
                        len(result['success'])
                    )
                )

            # TODO: check they are complete before moving them
            for scene in scenes:
                print('downloaded', scene)
                if os.path.isfile(os.path.join(downloaddir, scene + '.zip')):
                    shutil.move(os.path.join(downloaddir, scene + '.zip'),
                                os.path.join(stagedir, scene + '.zip'))

        # all the downloaded zip scenes are present
        print('all the downloaded zip scenes are present')

        scenefiles = []
        for scene in scenes:

            scenefile = os.path.join(stagedir, scene + '.tif')
            scenefiles.append(scenefile)

            if not os.path.exists(scenefile):

                sourcefile = os.path.join(stagedir, scene + '.zip')
                targetfile = os.path.join(downloaddir, scene + '.tif')
                print('processing', sourcefile, targetfile)

                cmd = "/usr/bin/gpt {} -c 48G -J-Xmx32G -J-Xms12G -q 8 -e -SsourceProduct={} -PtargetProduct={} " \
                      "-Dsnap.dataio.bigtiff.compression.type=LZW " \
                      "-Dsnap.parallelism=1".format(graph_xml_path, sourcefile, targetfile)
                print(cmd)
                command(cmd)

                print('moving', targetfile, scenefile)
                shutil.move(targetfile, scenefile)

        # all the downloaded zips have been processed and are present
        print('all the downloaded zips have been processed and are present')

        # TODO: why is this the only way I can get the current tile ID?
        tileid = os.path.splitext(download_fp)[0][-7:]
        shpfile = os.path.join(stagedir, 'tile_{}.shp'.format(tileid))

        outfiles = []
        for i,scenefile in enumerate(scenefiles):
            print('warping', scenefile)

            layername = os.path.splitext(os.path.split(shpfile)[1])[0]

            outfile = os.path.splitext(download_fp)[0] + '_{}.tif'.format(i)

            print('gdalwarp', outfile, scenefile)

            ds = gdal.Warp(outfile, scenefile, format='GTiff', cutlineDSName=shpfile, \
                cutlineLayer=layername,options=['COMPRESS=LZW'], cropToCutline=True, \
                dstAlpha=False, xRes=0.0001, yRes=0.0001)

            outfiles.append(outfile)

        if len(outfiles) > 1:
            # merge the results and save as an asset
            cmd = 'gdal_merge.py -n 0 -a_nodata 0 -init 0 -o {} {}'.format(download_fp, ' '.join(outfiles))
            args = shlex.split(cmd)
            p = subprocess.Popen(args)
            p.communicate()
            if p.returncode != 0:
                raise IOError("Expected exit status 0, got {}".format(p.returncode))
        else:
            # no need to merge
            shutil.move(outfiles[0], download_fp)

        # TODO: use temp file
        # this just removes the shapefile
        for file in glob.glob(os.path.splitext(shpfile)[0] + '.*'):
           os.remove(file)

        return True

    @classmethod
    def fetch(cls, *args, **kwargs):
        fetched = super(sentinel1Asset, cls).fetch(*args, **kwargs)
        # clear out the staging area
        # TODO: just use temp files everywhere
        # or more ideally, provide an option for the user to keep the raw files
        return fetched


class sentinel1Data(Data):
    name = 'Sentinel1'
    version = '0.0.1'
    Asset = sentinel1Asset
    inline_archive = True

    # TODO: is this the correct order?
    _productgroups = {'sigma0': ['sigma0']}

    _products = {
        'sigma0': {
            'description': 'Backscatter',
            'assets': _asset_types,
            'bands': ['vv', 'vh'],
            'sensor': 'S1'
        },
        'indices': {
            'description': 'Backscatter indices',
            'assets': _asset_types,
            'bands': ['mean', 'difference', 'ratio'],
            'sensor': 'S1'
        },
    }

    @Data.proc_temp_dir_manager
    def process(self, *args, **kwargs):
        """Produce data products and save them to files."""
        start = datetime.datetime.now()
        products = super(sentinel1Data, self).process(*args, **kwargs)
        if len(products) == 0:
            return

        bname = os.path.join(self.path, self.basename)

        asset = list(self.assets.keys())[0]
        assetfname = self.assets[asset].datafiles()[0]

        # key is only used once far below, and val is only used for val[0].
        for key, val in products.requested.items():

            prod_type = val[0]
            sensor = self._products[prod_type]['sensor']
            fname = self.temp_product_filename(sensor, prod_type)

            if val[0] == "sigma0":
                # this product is just the asset but it has to have the right name
                os.link(assetfname, fname)

            if val[0] == "indices":
                img = gippy.GeoImage(assetfname)
                data = img.Read()
                raise Exception('indices not supported yet')

            # add product to inventory
            archive_fp = self.archive_temp_path(fname)
            self.AddFile(sensor, key, archive_fp)
            utils.verbose_out(' -> {}: processed in {}'.format(
                os.path.basename(fname), datetime.datetime.now() - start), level=1)
