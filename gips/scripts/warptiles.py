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
from gips import __version__ as gipsversion
from gips.parsers import GIPSParser
from gips.data.core import data_class
from gips.utils import Colors, VerboseOut, mkdir, open_vector


def main():
    title = Colors.BOLD + 'GIPS Warp Tiles Utility v%s' % gipsversion + Colors.OFF

    # argument parsing
    parser0 = GIPSParser(description=title)
    parser0.add_inventory_parser()
    parser0.add_process_parser()
    parser0.add_project_parser()
    parser0.add_warp_parser()
    args = parser0.parse_args()

    try:
        print title
        cls = data_class(args.command)

        # create output directory: DATATYPE_tiles_RESOLUTION
        suffix = '' if args.suffix is None else '_' + args.suffix
        datadir = args.command + '_tiles'
        if args.res is None:
            args.res = cls.Asset._defaultresolution
        if args.res[0] == args.res[1]:
            resstr = str(args.res[0])
        else:
            resstr = '%sx%s' % (args.res[0], args.res[1])
        datadir = os.path.join(args.outdir, '%s_%s%s' % (datadir, resstr, suffix))
        mkdir(datadir)

        for feature in open_vector(args.site, args.key, args.where):
            inv = cls.inventory(feature=feature, **vars(args))
            for date in inv.dates:
                for tid in inv[date].tiles:
                    # make sure back-end tiles are processed
                    inv[date].tiles[tid].process(args.products, overwrite=False)
                    # warp the tiles
                    inv[date].tiles[tid].copy(datadir, args.products, inv.spatial.site,
                                              args.res, args.interpolation, args.crop, args.overwrite, args.tree)

    except Exception, e:
        import traceback
        VerboseOut(traceback.format_exc(), 4)
        print 'Warp Tiles error: %s' % e


if __name__ == "__main__":
    main()
