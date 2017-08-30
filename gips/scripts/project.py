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
from gips import __version__
from gips.parsers import GIPSParser
from gips.core import SpatialExtent, TemporalExtent
from gips.utils import Colors, VerboseOut, import_data_class
from gips import utils
from gips.inventory import DataInventory, ProjectInventory
from gips.inventory import orm


def main():
    title = Colors.BOLD + 'GIPS Data Project (v%s)' % __version__ + Colors.OFF

    # argument parsing
    parser0 = GIPSParser(description=title)
    parser0.add_inventory_parser(site_required=True)
    parser0.add_process_parser()
    parser0.add_project_parser()
    parser0.add_warp_parser()
    args = parser0.parse_args()
    if args.alltouch:
        raise NotImplementedError("--alltouch not supported due to gippy 1.0 incompatibility")

    cls = utils.gips_script_setup(args.command, args.stop_on_error)
    print title

    with utils.error_handler():
        extents = SpatialExtent.factory(
            cls, args.site, args.key, args.where, args.tiles, args.pcov,
            args.ptile
        )

        # create tld: SITENAME--KEY_DATATYPE_SUFFIX
        if args.notld:
            tld = args.outdir
        else:
            key = '' if args.key == '' else '--' + args.key
            suffix = '' if args.suffix == '' else '_' + args.suffix
            res = '' if args.res is None else '_%sx%s' % (args.res[0], args.res[1])
            bname = (
                extents[0].site.layer_name() +
                key + res + '_' + args.command + suffix
            )
            tld = os.path.join(args.outdir, bname)

        for extent in extents:
            t_extent = TemporalExtent(args.dates, args.days)
            inv = DataInventory(cls, extent, t_extent, **vars(args))
            datadir = os.path.join(tld, extent.site.value())
            if inv.numfiles > 0:
                inv.mosaic(
                    datadir=datadir, tree=args.tree, overwrite=args.overwrite,
                    res=args.res, interpolation=args.interpolation,
                    crop=args.crop, alltouch=args.alltouch,
                )
                inv = ProjectInventory(datadir)
                inv.pprint()
            else:
                VerboseOut(
                    'No data found for {} within temporal extent {}'
                    .format(str(t_extent), str(t_extent)),
                    2,
                )

    utils.gips_exit() # produce a summary error report then quit with a proper exit status


if __name__ == "__main__":
    main()
