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

import gippy
from gips.parsers import GIPSParser
from gips.inventory import ProjectInventory
from gips.utils import Colors, verbose_out, basename
from gips import utils

__version__ = '0.1.0'

def main():
    title = Colors.BOLD + 'GIPS Project Masking (v%s)' % __version__ + Colors.OFF

    parser = GIPSParser(datasources=False, description=title)
    parser.add_projdir_parser()
    group = parser.add_argument_group('masking options')
    group.add_argument('--filemask', help='Mask all files with this static mask', default=None)
    group.add_argument('--pmask', help='Mask files with this corresponding product', nargs='*', default=[])
    h = 'Write mask to original image instead of creating new image'
    group.add_argument('--original', help=h, default=False, action='store_true')
    h = 'Overwrite existing files when creating new'
    group.add_argument('--overwrite', help=h, default=False, action='store_true')
    h = 'Suffix to apply to masked file (not compatible with --original)'
    group.add_argument('--suffix', help=h, default='-masked')
    args = parser.parse_args()

    # TODO - check that at least 1 of filemask or pmask is supplied

    utils.gips_script_setup(None, args.stop_on_error)

    with utils.error_handler('Masking error'):
        verbose_out(title, 1)
        if not args.projdir:
            verbose_out('no project directories specified; doing nothing.', 2)
        for projdir in args.projdir:

            if args.filemask is not None:
                mask_file = gippy.GeoImage(args.filemask)

            inv = ProjectInventory(projdir, args.products)
            for date in inv.dates:
                verbose_out('Masking files from %s' % date)
                if args.filemask is None and args.pmask == []:
                    available_masks = inv[date].masks()
                else:
                    available_masks = inv[date].masks(args.pmask)
                if not available_masks:
                    verbose_out('no masks found for {}'.format(date), 2)
                for p in inv.products(date):
                    # don't mask any masks
                    if p in available_masks:
                        continue
                    meta = ''
                    # TODO gippy 1.0:  confirm this works from here down
                    img = inv[date].open(p, update=args.original)
                    if args.filemask is not None:
                        img.add_mask(mask_file[0]) # TODO hmm
                        meta = basename(args.filemask) + ' '
                    for mask in available_masks:
                        img.add_mask(inv[date].open(mask)[0]) # TODO hmm
                        meta = meta + basename(inv[date][mask]) + ' '
                    if meta != '':
                        if args.original:
                            verbose_out('  %s' % (img.basename()), 2)
                            img.save()
                            img.add_meta('MASKS', meta)
                        else:
                            fout = os.path.splitext(img.filename())[0] + args.suffix + '.tif'
                            if not os.path.exists(fout) or args.overwrite:
                                verbose_out('  %s -> %s' % (img.basename(), basename(fout)), 2)
                                imgout = img.save(fout)
                                imgout.add_meta('MASKS', meta)
                                imgout = None
                            else:
                                msg = "Can't write to {}, file exists"
                                verbose_out(msg.format(fout), 1, 'stderr')
                    img = None
            mask_file = None

    utils.gips_exit()


if __name__ == "__main__":
    main()
