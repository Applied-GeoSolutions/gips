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

"""Read, maintain, or add to the GIPS internal inventory.

Download available assets for the given constraints with --fetch:

    gips_inventory modis -s NHseacoast.shp -d 2012-12-01,2012-12-03 --fetch

If GIPS is configured to use a database to track its inventory, rebuild
the inventory to match the current state of the archive with --rectify.
This must be repeated for each asset type for which rectification is
desired, eg:

    gips_inventory modis --rectify
    gips_inventory prism --rectify
"""

from functools import partial
import json

from gips import __version__ as gipsversion
from gips.parsers import GIPSParser
from gips.core import SpatialExtent, TemporalExtent
from gips.utils import Colors, open_vector
from gips import utils
from gips.inventory import DataInventory
from gips.inventory import dbinv, orm

import pyproj
import shapely
import shapely.ops


def main():
    title = Colors.BOLD + 'GIPS Data Inventory (v%s)' % gipsversion + Colors.OFF

    # argument parsing
    parser0 = GIPSParser(description=title)
    parser = parser0.add_inventory_parser()
    group = parser.add_argument_group('additional inventory options')
    group.add_argument('--md', help='Show dates using MM-DD', action='store_true', default=False)
    group.add_argument('--rectify',
                       help='Instead of displaying or fetching inventory, rectify the inventory '
                            'database by comparing it against the present state of the data repos.',
                       action='store_true',
                       default=False)
    args = parser0.parse_args()

    cls = utils.gips_script_setup(args.command, args.stop_on_error)


    with utils.error_handler():
        print(title)

        if args.rectify:
            if not orm.use_orm():
                raise ValueError("--rectify can only be used if"
                                 " GIPS_ORM = True.")
            for k, v in vars(args).items():
                # Let the user know not to expect other options to effect rectify
                if v and k not in ('rectify', 'verbose', 'command'):
                    msg = "INFO: Option '--{}' is has no effect on --rectify."
                    utils.verbose_out(msg.format(k), 1)
            print("Rectifying inventory DB with filesystem archive:")
            print("Rectifying assets:")
            dbinv.rectify_assets(cls.Asset)
            print("Rectifying products:")
            dbinv.rectify_products(cls)
            return

        spatial_extents = SpatialExtent.factory(
            cls, site=args.site, rastermask=args.rastermask,
            key=args.key, where=args.where, tiles=args.tiles,
            pcov=args.pcov, ptile=args.ptile
        )
        for se in spatial_extents:
            inv = DataInventory(cls, se, TemporalExtent(args.dates, args.days), **vars(args))
            inv.pprint(md=args.md, size=args.size)

        if args.dump_geojson_extent:
            tile_geoms = []
            for se in spatial_extents:
                tiles_vector = open_vector(
                    se.repo.get_setting("tiles"),
                    key=se.repo._tile_attribute
                )
                project = partial(
                    pyproj.transform,
                    pyproj.Proj(tiles_vector.srs()),
                    pyproj.Proj('epsg:4326')
                )
                for tile in se.tiles:
                    tile_feat = tiles_vector[tile]
                    tile_geom = shapely.wkt.loads(tile_feat.wkt_geometry())
                    tile_geoms.append(shapely.ops.transform(project, tile_geom))
                del tiles_vector
            extent = shapely.ops.unary_union(tile_geoms)
            with open(args.dump_geojson_extent, 'w') as geojson_out:
                json.dump(extent.__geo_interface__, geojson_out)

    utils.gips_exit() # produce a summary error report then quit with a proper exit status

if __name__ == "__main__":
    main()
