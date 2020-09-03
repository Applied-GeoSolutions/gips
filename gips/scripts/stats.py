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

import os
import csv

import gippy
from gips.parsers import GIPSParser
from gips.inventory import ProjectInventory
from gips.utils import Colors, VerboseOut, basename
from gips import utils

__version__ = '0.1.0'

def main():
    title = Colors.BOLD + 'GIPS Image Statistics (v%s)' % __version__ + Colors.OFF

    parser0 = GIPSParser(datasources=False, description=title)
    parser0.add_projdir_parser()
    group = parser0.add_argument_group('masking options')
    args = parser0.parse_args()

    utils.gips_script_setup(stop_on_error=args.stop_on_error)
    print(title)

    with utils.error_handler():
        for projdir in args.projdir:
            VerboseOut('Stats for Project directory: %s' % projdir, 1)
            inv = ProjectInventory(projdir, args.products)
            inv.write_stats()

    utils.gips_exit() # produce a summary error report then quit with a proper exit status


if __name__ == "__main__":
    main()
