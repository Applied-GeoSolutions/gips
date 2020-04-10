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

import sys
import os
from datetime import datetime
import traceback
import collections

import gippy
from gippy.algorithms import cookie_cutter
from gips.utils import VerboseOut, Colors, mkdir
from gips import utils


class Tiles(object):
    """ Collection of files for single date and one or more regions (tiles) """

    def __init__(self, dataclass, spatial, date=None, products=None, **kwargs):
        """ Locate data matching vector location (or tiles) and date
        self.coverage      dict of tile id: %coverage with site
        self.tiles         mapping of tile IDs to Data instances, eg for modis:
                           {'h12v04': <modis.modisData object at 0x7fb34ab9e550>}
        """
        self.dataclass = dataclass
        self.spatial = spatial
        self.products = products if products is not None else dataclass.RequestedProducts()
        self.date = date
        # For each tile locate files/products
        self.tiles = {}

    def __len__(self):
        return len(self.tiles)

    def __getitem__(self, key):
        return self.tiles[key]

    @property
    def sensor_set(self):
        """ Return list of sensors used in all tiles """
        s = set()
        for t in self.tiles:
            s.update(self.tiles[t].sensor_set)
        return list(s)

    def which_sensor(self, key):
        """ Get sensor code used for provided asset or product key """
        for t in self.tiles:
            if key in self.tiles[t].sensors:
                return self.tiles[t].sensors[key]

    def process(self, *args, **kwargs):
        """ Calls process for each tile """
        [t.process(*args, products=self.products.products, **kwargs) for t in list(self.tiles.values())]

    def mosaic(self, datadir, res=None, interpolation=0, crop=False,
               overwrite=False, alltouch=False, vrt=False):
        """For each product, combine its tiles into a single mosaic.

        Warp if res provided."""
        if self.spatial.site is None:
            raise Exception('Site required for creating mosaics')
        start = datetime.now()
        bname = self.date.strftime('%Y%j')

        # look in each Data() and dig out its (sensor, product_type) pairs
        sp_pile = [(s, p) for d in self.tiles.values() for (s, p) in d.filenames
                        if p in self.products.products]
        # work on each product in turn, gathering up filenames as needed
        for (sensor, product) in sp_pile:
            # create data directory when it is needed
            mkdir(datadir)
            # TODO - this is assuming a tif file.  Use gippy FileExtension function when it is exposed
            extension = 'vrt' if vrt else 'tif'
            fn = '{}_{}_{}.{}'.format(bname, sensor, product, extension)
            final_fp = os.path.join(datadir, fn)
            if not os.path.exists(final_fp) or overwrite:
                err_msg = ("Error mosaicking " + final_fp + ". Did you forget"
                           " to specify a resolution (`--res x x`)?")

                with utils.error_handler(err_msg, continuable=True):

                    with utils.make_temp_dir(dir=datadir, prefix='mosaic') as tmp_dir:

                        tmp_fp = os.path.join(tmp_dir, fn) # for safety

                        filenames = [self.tiles[t].filenames[(sensor, product)]
                                     for t in self.tiles
                                     if (sensor, product) in self.tiles[t].filenames
                        ]

                        images = [gippy.GeoImage(f) for f in filenames]

                        if vrt:
                            spatial_kwarg = {}
                            if self.spatial.rastermask:
                                spatial_kwarg['rastermask'] = self.spatial.rastermask
                            else:
                                spatial_kwarg['site'] = self.spatial.site
                            utils.vrt_mosaic(filenames, tmp_fp, interpolation, res, **spatial_kwarg)
                        elif self.spatial.rastermask is not None:
                            utils.gridded_mosaic(images, tmp_fp, self.spatial.rastermask,
                                                 interpolation)
                        elif res is not None:
                            cookie_cutter(
                                images, tmp_fp, self.spatial.site, crop,
                                "", res[0], res[1], interpolation,
                            )
                        else:
                            utils.mosaic(images, tmp_fp, self.spatial.site)
                        os.rename(tmp_fp, final_fp)
        t = datetime.now() - start
        VerboseOut('%s: created project files for %s tiles in %s' % (self.date, len(self.tiles), t), 2)

    def asset_coverage(self):
        """ Calculates % coverage of site for each asset """
        asset_coverage = {}
        for a in self.dataclass.Asset._assets:
            cov = 0.0
            norm = float(len(self.spatial.coverage)) if self.spatial.site is None else 1.0
            for t in self.tiles:
                if a in self.tiles[t].assets:
                    cov = cov + (self.spatial.coverage[t][0] / norm)
            asset_coverage[a] = cov * 100
        return asset_coverage

    def product_coverage(self):
        """ Calculated % coverage of site for each product """
        raise NotImplementedError(
            "Deprecated and incorrect for products that depend on any of two or more assets.")
        coverage = {}
        for p in self.dataclass._products.keys():
            assets = self.dataclass.products2assets([p])
            norm = float(len(self.spatial.coverage)) if self.spatial.site is None else 1.0
            cov = 0.0
            for t in self.tiles:
                allassets = True
                for a in assets:
                    if a not in self.tiles[t].assets:
                        allassets = False
                if allassets:
                    cov = cov + (self.spatial.coverage[t][0] / norm)
            coverage[p] = cov * 100
        return coverage

    def pprint_asset_header(self):
        """ Print asset header """
        self.dataclass.pprint_asset_header()

    def _colorize_product(self, prod, colors=None):
        color = ['', '']
        if colors is not None:
            s = self.which_sensor(prod)
            if s is not None:
                color = [colors[s], Colors.OFF]
        return color[0] + prod + color[1]

    def pprint(self, dformat='%j', colors=None):
        """Print each scene's asset coverage & products.

        dformat is to format the date;
        colors is a mapping from sensors to ptypes
        """
        # print DOY on the left
        sys.stdout.write('{:^12}'.format(self.date.strftime(dformat)))

        # print coverage percentages for each asset
        asset_coverage = self.asset_coverage()
        for a in sorted(asset_coverage):
            cov = asset_coverage[a]
            if cov > 0:
                text = self._colorize_product(
                        '  {:>4.1f}%  '.format(cov), colors)
            else:
                text = ' ' * 10
            sys.stdout.write(text)

        # print product types, colored by sensor, but only if there's a product
        # in each of the tiles
        s_pt = collections.defaultdict(list)
        for s, pt in list(self.tiles.values())[0].filenames:
            if all((s, pt) in d.filenames for d in self.tiles.values()):
                s_pt[s].append(pt)
        for s in sorted(s_pt):
            sys.stdout.write(' ')
            p_type_str = ' '.join(sorted(s_pt[s]))
            try:
                sys.stdout.write(colors[s] + p_type_str + Colors.OFF)
            except (TypeError, KeyError):
                sys.stdout.write(p_type_str)
        sys.stdout.write('\n')
