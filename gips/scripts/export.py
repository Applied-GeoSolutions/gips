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
from gips import __version__
from gips.parsers import GIPSParser
from gips.core import SpatialExtent, TemporalExtent
from gips.utils import Colors, import_data_class
from gips import utils
from gips.utils import vprint
from gips.inventory import DataInventory, ProjectInventory
from gips.inventory import orm

import tempfile
import boto3
import zipfile
import shutil


def get_s3_shppath(s3path, tmpdir):
    vprint('s3path', s3path)
    S3 = boto3.resource('s3')
    s3path = s3path.lstrip('s3://')
    assert s3path.endswith('.zip'), "unzipped shapefiles not supported yet"
    filename = s3path.split('/')[-1]
    s3_bucket = s3path.split('/')[0]
    s3_key = "/".join(s3path.split('/')[1:])
    zippath = os.path.join(tmpdir, filename)
    S3.Bucket(s3_bucket).download_file(s3_key, zippath)
    zipped = zipfile.ZipFile(zippath)
    for f in zipped.filelist:
        ext = os.path.splitext(f.filename)[1]
        f.filename = 'shapefile{}'.format(ext)
        zipped.extract(f, path=tmpdir)
    shppath = os.path.join(os.path.split(zippath)[0], 'shapefile.shp')
    return shppath


def run_export(args):

    cls = utils.gips_script_setup(args.command, args.stop_on_error)

    with utils.error_handler():
        with tempfile.TemporaryDirectory() as tmpdir:

            if args.site is not None and args.site.startswith('s3://'):
                shppath = get_s3_shppath(args.site, tmpdir)
                args.site = shppath
            else:
                shppath = None

            if args.outdir.startswith('s3://'):
                S3 = boto3.resource('s3')
                s3path = args.outdir.lstrip('s3://')
                dirname = s3path.split('/')[-1]
                s3_bucket = s3path.split('/')[0]
                s3_key = "/".join(s3path.split('/')[1:])
                s3outdir = args.outdir
                args.outdir = os.path.join(tmpdir, dirname)
                vprint('temp outdir', args.outdir)
            else:
                s3outdir = None

            extents = SpatialExtent.factory(
                cls, site=args.site, rastermask=args.rastermask,
                key=args.key, where=args.where, tiles=args.tiles,
                pcov=args.pcov, ptile=args.ptile
            )

            # How does export set the name of the TLD for the export?
            #   sitename = layer name of the first feature in the --site, if it has one
            #   key    = primary search key of the site, specified by user
            #   res    = <X-resolution><Y-resolution> (I guess?  Might be Y-X)
            #   driver = just the normal driver string (named 'args.command' naturally)
            #   suffix = custom string specified by user for their optional convenience
            # so the TLD name ends up being:
            #   [<sitename>][--<key>][_<res>]_<driver>[_suffix]
            if args.notld:
                tld = args.outdir
            else:
                key    = '' if args.key == ''    else '--' + args.key
                res    = '' if args.res is None  else '_%sx%s' % (args.res[0], args.res[1])
                suffix = '' if args.suffix == '' else '_' + args.suffix
                bname  = (
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
                        process=(not args.dont_process), vrt=args.vrt
                    )
                    inv = ProjectInventory(datadir)
                    inv.pprint()
                else:
                    vprint('No data found for', t_extent, level=2)

            if s3outdir is not None and os.path.exists(args.outdir):
                outpath = args.outdir
                zippath = outpath + ".zip"
                shutil.make_archive(outpath, 'zip', args.outdir)
                zipname = os.path.split(zippath)[-1]

                S3 = boto3.resource('s3')
                s3path = s3outdir.lstrip('s3://')
                s3_bucket = s3path.split('/')[0]
                s3_key = "/".join(s3path.split('/')[1:]) + ".zip"

                vprint('uploading', zippath, s3_bucket, s3_key)
                S3.meta.client.upload_file(zippath, s3_bucket, s3_key)


def main():
    title = Colors.BOLD + 'GIPS Data Export (v%s)' % __version__ + Colors.OFF
    vprint(title)

    # argument parsing
    parser0 = GIPSParser(description=title)
    parser0.add_inventory_parser(site_required=True)
    parser0.add_process_parser()
    parser0.add_project_parser()
    parser0.add_warp_parser()
    args = parser0.parse_args()

    run_export(args)

    utils.gips_exit() # produce a summary error report then quit with a proper exit status


if __name__ == "__main__":
    main()
