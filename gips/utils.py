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

import imp
import sys
import os
import re
import errno
from contextlib import contextmanager
import tempfile
import subprocess
import shutil
import traceback
import datetime
import time
import json
import logging

import numpy as np
import requests

import gippy
from gippy import GeoVector
from .exceptions import GipsException


class Colors():
    _c = '\033['
    OFF     = _c + '0m'
    # Font styles
    BOLD    = _c + '1m'
    UNDER   = _c + '4m'
    REV     = _c + '7m'
    # Text colors
    BLACK   = _c + '30m'
    RED     = _c + '31m'
    GREEN   = _c + '32m'
    YELLOW  = _c + '33m'
    BLUE    = _c + '34m'
    PURPLE  = _c + '35m'
    CYAN    = _c + '36m'
    WHITE   = _c + '37m'
    # Background colors
    _BLACK  = _c + '40m'
    _RED    = _c + '41m'
    _GREEN  = _c + '42m'
    _YELLOW = _c + '43m'
    _BLUE   = _c + '44m'
    _PURPLE = _c + '45m'
    _CYAN   = _c + '46m'
    _WHITE  = _c + '47m'


def verbosity_to_log_level(v):
    """Converts verbosity values (`-v 3`) to python log levels.

    Verbosity levels don't map to log levels:  Log levels describe
    severity, but verbosity describes level of detail or noisiness on
    the console.  Most of gips CLI output is probably INFO or DEBUG,
    whereas the WARNING, ERROR, and CRITICAL stuff is all (or had better
    be) at -v1, and will be in the context of error handling anyway.
    """
    # gips.parsers says verbosity 0 means "quiet" mode, while the default for -v is 1.
    if v < 1:
        return logging.WARNING
    if v == 1:
        return logging.INFO
    if v > 1:
        return logging.DEBUG


def verbose_out(obj, level=1, stream=sys.stdout):
    """print() or log() the object, conditional on _lib_mode.

    If _lib_mode, python's logging is used and `stream` is ignored.
    Otherwise, print the object to the stream, but only if the user's
    chosen verbosity level warrants it. Finally if the obj is a list or
    tuple, print each contained object consecutively on separate lines.
    """
    #TODO: Add real documentation of rules regarding levels used within
    #      GIPS. Levels 1-4 are used frequently.  Setting `-v5` is
    #      "let me see everything" level.
    is_listy = isinstance(obj, (list, tuple))
    if _lib_mode:
        logger = logging.getLogger(_named_logger) # believed quick enough to run every time
        log_level = verbosity_to_log_level(level)
        if is_listy:
            [logger.log(log_level, o) for o in obj]
        else:
            logger.log(log_level, obj)
    elif verbosity() >= level:
        if is_listy:
            [print(o, file=stream) for o in obj]
        else:
            print(obj, file=stream)


VerboseOut = verbose_out # VerboseOut name is deprecated


def vprint(*args, sep=' ', end='\n', level=1, file=sys.stdout):
    """As verbose_out but accept arguments similarly to print().

    Pass in 'level=n' to print at that verbosity (default is 1). Other kwargs,
    such as 'sep', are passed on to print(), but 'file' may be ignored when
    printing to a log as python logging has no notion of stdout vs stderr.
    """
    if _lib_mode:
        logging.getLogger(_named_logger).log(verbosity_to_log_level(level), sep.join(args))
    elif verbosity() >= level:
        print(*args, sep=sep, end=end, file=file)


def verbosity(new=None):
    """Returns after optionally setting the gips verbosity level.
    Currently slaved to gippy's verbosity level."""
    if new is not None:
        gippy.Options.set_verbose(new)
    return gippy.Options.verbose()


##############################################################################
# Filesystem functions
##############################################################################

def json_dump(object, file_path):
    """Write the object as json to the given file path."""
    with open(file_path, 'w') as tfo:
        json.dump(object, tfo)

def File2List(filename):
    """Return contents of file as a list of lines, sans newlines."""
    f = open(filename)
    txt = f.readlines()
    txt2 = []
    for t in txt:
        txt2.append(t.rstrip('\n'))
    return txt2


def List2File(lst, filename):
    """Overwrite the given file with the contents of the list.

    Each item in the list is given a trailing newline.
    """
    f = open(filename, 'w')
    f.write('\n'.join(lst) + '\n')
    f.close()


def remove_files(filenames, extensions=()):
    """Remove the given files and all permutations with the given extensions.

    So remove_files(['a.hdf', 'b.hdf'], ['.index', '.aux.xml']) attempts to
    these files:  a.hdf, b.hdf, a.hdf.index, a.hdf.aux.xml, b.hdf,
    b.hdf.index, and b.hdf.aux.xml.  Doesn't raise an error if any file doesn't exist.
    """
    for f in (list(filenames) + [f + e for f in filenames for e in extensions]):
        with error_handler(continuable=True, msg_prefix="Error removing '{}'".format(f)):
            if os.path.isfile(f):
                verbose_out('Removing ' + f, 5)
                os.remove(f)

RemoveFiles = remove_files # RemoveFiles name is deprecated

def basename(str):
    """Return the input string, stripped of directories and extensions.

    So, basename('/home/al-haytham/book-of-optics.pdf') returns
    'book-of-optics'.
    """
    return os.path.splitext(os.path.basename(str))[0]


def mkdir(dname):
    """Create a directory, if it doesn't exist."""
    try:
        os.makedirs(dname)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise
    return dname


def link(src, dst, hard=False):
    """ Create link in this directory """
    if os.path.lexists(dst):
        os.remove(dst)
    # link path path relative to dst
    if hard:
        os.link(src, os.path.abspath(dst))
    else:
        os.symlink(os.path.relpath(src, os.path.dirname(dst)), os.path.abspath(dst))
    return dst

@contextmanager
def make_temp_dir(suffix='', prefix='tmp', dir=None):
    """Context manager to create then delete a temporary directory.

    Arguments are the same as tempfile.mkdtemp, which it calls.  Yields
    the absolute pathname to the new directory.  Deletes the directory
    at the exit of the context, regardless of exceptions raised in the
    context.
    """
    absolute_pathname = tempfile.mkdtemp(suffix, prefix, dir)
    try:
        yield absolute_pathname
    finally:
        if 'GIPS_DEBUG' not in os.environ:
            rm_num_tries = max(1, os.environ.get('GIPS_RMTREE_TRIES', 4))
            rm_delay = max(0.1, os.environ.get('GIPS_RMTREE_DELAY', .5))
            for tries in range(1, rm_num_tries + 1):
                try:
                    shutil.rmtree(absolute_pathname)
                except Exception as e: # TODO don't conceal the original exception; it may matter
                    ### This whole block is ugly, but somehow the directory is
                    ### not emptying out immediately, but it is emptying out eventually.
                    if tries > rm_num_tries:
                        print('Open files: ')
                        os.system('/bin/ls -l /proc/{}/fd'.format(os.getpid()))
                        print('^^^^^^^^^^^^^^^^^^^^^^^^^')
                        raise e
                    # it can occur that it has now been deleted, so break
                    if not os.path.exists(absolute_pathname):
                        verbose_out('tempdir: infintesimal delay on deletion', 5)
                        break
                    verbose_out('GIPS_RMTREE_DELAY: delaying {} sec'.format(rm_delay), 5)
                    time.sleep(rm_delay)
                    # though less likely, post-delay it could have been deleted, so break
                    if not os.path.exists(absolute_pathname):
                        verbose_out('tempdir: {} sec delay on deletion'.format(rm_delay), 5)
                        break
                    verbose_out('GIPS_RMTREE_TRIES: Trying again (try {} of {}): {}'.format(
                            tries, rm_num_tries, absolute_pathname), 1)
        else:
            verbose_out('GIPS_DEBUG: Orphaning {}'.format(absolute_pathname), 1)

def find_files(regex, path='.'):
    """Find filenames in the given directory that match the regex.

    Returns a list of matching filenames; each includes the given path.
    Only regular files and symbolic links to regular files are returned.
    """
    compiled_re = re.compile(regex)
    ret = []
    for f in os.listdir(path):
        fpath = os.path.join(path, f)
        if os.path.isfile(fpath) and compiled_re.match(f):
            ret.append(fpath)
    return ret


##############################################################################
# Settings functions
##############################################################################


def settings():
    """ Retrieve GIPS settings - first from user, then from system """
    settings_path = os.path.expanduser('~/.gips/settings.py')
    if os.path.isfile(settings_path):
        with error_handler("Error loading '{}'".format(settings_path)):
            # import user settings first
            src = imp.load_source('settings', settings_path)
            return src
    with error_handler("gips.settings not found; consider running gips_config"):
        import gips.settings
        return gips.settings


def create_environment_settings(repos_path, email=''):
    """ Create settings file and data directory """
    from gips.settings_template import __file__ as src
    cfgpath = os.path.dirname(__file__)
    cfgfile = os.path.join(cfgpath, 'settings.py')
    if src[-1] == 'c':
        src = src[:-1]
    if os.path.exists(cfgfile):
        return False, cfgfile
    with open(cfgfile, 'w') as fout:
        with open(src, 'r') as fin:
            for line in fin:
                fout.write(line.replace('$TLD', repos_path).replace('$EMAIL', email))
    return True, cfgfile


def create_user_settings(email=''):
    """ Create a settings file using the included template and the provided top level directory """
    from gips.user_settings_template import __file__ as src
    if src[-1] == 'c':
        src = src[:-1]
    cfgpath = os.path.expanduser('~/.gips')
    if not os.path.exists(cfgpath):
        os.mkdir(cfgpath)
    cfgfile = os.path.join(cfgpath, 'settings.py')
    if os.path.exists(cfgfile):
        return False, cfgfile
    with open(cfgfile, 'w') as fout:
        with open(src, 'r') as fin:
            for line in fin:
                fout.write(line)
    return True, cfgfile


def create_repos():
    """ Create any necessary repository directories """
    repos = settings().REPOS
    for key in repos.keys():
        repo = import_repository_class(key)
        for d in repo._subdirs:
            mkdir(os.path.join(repos[key]['repository'], d))

def data_sources():
    """ Get enabled data sources (and verify) from settings """
    sources = {}
    repos = settings().REPOS
    for key in sorted(repos.keys()):
        if not os.path.isdir(repos[key]['repository']):
            raise Exception('ERROR: archive %s is not a directory or is not available' % key)
        repo = import_repository_class(key)
        sources[key] = repo.description
    return sources


def import_data_module(clsname):
    """ Import a data driver by name and return as module """
    import imp
    path = settings().REPOS[clsname].get('driver', '')
    if path == '':
        path = os.path.join( os.path.dirname(__file__), 'data', clsname)
    with error_handler('Error loading driver ' + clsname):
        fmtup = imp.find_module(clsname, [path])
        mod = imp.load_module(clsname, *fmtup)
        return mod


def import_repository_class(clsname):
    """ Get clsnameRepository class object """
    mod = import_data_module(clsname)
    repo = eval('mod.%sRepository' % clsname)
    return repo


def import_data_class(clsname):
    """ Get clsnameData class object """
    mod = import_data_module(clsname)
    repo = eval('mod.%sData' % clsname)
    # prevent use of database inventory for certain incompatible drivers
    from gips.inventory import orm
    orm.driver_for_dbinv_feature_toggle = repo.name.lower()
    return repo


##############################################################################
# Geospatial functions
##############################################################################

def open_vector(fname, key="", where=''):
    """Open vector or feature, returned as a gippy GeoVector or GeoFeature."""
    parts = fname.split(':')
    if len(parts) == 1:
        vector = GeoVector(fname)
        vector.set_primary_key(key)
    else:
        # or it is a database
        if parts[0] not in settings().DATABASES.keys():
            raise Exception("%s is not a valid database" % parts[0])
        db = settings().DATABASES[parts[0]]
        filename = ("PG:dbname=%s host=%s port=%s user=%s password=%s" %
                    (db['NAME'], db['HOST'], db['PORT'], db['USER'], db['PASSWORD']))
        vector = GeoVector(filename, parts[1])
        vector.set_primary_key(key)
    if where != '':
        # return array of features
        return vector.where(where)
    else:
        return vector

from shapely.wkt import loads as wktloads
from osr import SpatialReference, CoordinateTransformation
from ogr import CreateGeometryFromWkt


def transform_shape(shape, ssrs, tsrs):
    """ Transform shape from ssrs to tsrs (all wkt) and return as wkt """
    ogrgeom = CreateGeometryFromWkt(shape)
    trans = CoordinateTransformation(SpatialReference(ssrs), SpatialReference(tsrs))
    ogrgeom.Transform(trans)
    wkt = ogrgeom.ExportToWkt()
    ogrgeom = None
    return wkt


def transform(filename, srs):
    """ Transform vector file to another SRS """
    # TODO - move functionality into GIPPY
    bname = os.path.splitext(os.path.basename(filename))[0]
    td = tempfile.mkdtemp()
    fout = os.path.join(td, bname + '_warped.shp')
    prjfile = os.path.join(td, bname + '.prj')
    f = open(prjfile, 'w')
    f.write(srs)
    f.close()
    cmd = 'ogr2ogr %s %s -t_srs %s' % (fout, filename, prjfile)
    result = subprocess.getstatusoutput(cmd)
    return fout


def crop2vector(img, vector):
    """ Crop a GeoImage down to a vector - only used by mosaic """
    # transform vector to srs of image
    vecname = transform(vector.filename(), img.srs())
    warped_vec = open_vector(vecname)
    # rasterize the vector
    td = tempfile.mkdtemp()
    mask = gippy.GeoImage.create_from(img, os.path.join(td, vector.layer_name()), 1, 'uint8')
    maskname = mask.filename()
    mask = None
    cmd = 'gdal_rasterize -at -burn 1 -l %s %s %s' % (warped_vec.layer_name(), vecname, maskname)
    result = subprocess.getstatusoutput(cmd)
    VerboseOut('%s: %s' % (cmd, result), 4)
    mask = gippy.GeoImage(maskname)
    img.add_mask(mask[0]).save(img.filename()).clear_masks()
    mask = None
    shutil.rmtree(os.path.dirname(maskname))
    shutil.rmtree(os.path.dirname(vecname))
    # VerboseOut('Cropped to vector in %s' % (datetime.now() - start), 3)
    return img


def vectorize(img, vector, oformat=None):
    """
    Create vector from img using gdal_polygonize.

    oformat -- defaults to (due to ogr2ogr) "ESRI Shapefile"
    """
    conn_opt = '-8' # avoid islands as much as possible
    fmt = ''
    if oformat:
        fmt = '-f "{}"'.format(oformat)

    def gso_run(cmd, emsg):
        '''simple shell command wrapper'''
        with error_handler(emsg):
            verbose_out('Running: {}'.format(cmd), 4)
            status, output = subprocess.getstatusoutput(cmd)
            if status != 0:
                verbose_out(
                    '++\n Ran command:\n {}\n\n++++\n Console output:\n {}\n++\n'
                    .format(cmd, output),
                    1
                )
                raise RuntimeError(emsg)

    # Grab projection because gml doesn't carry it around by default
    wkt = gippy.GeoImage(img).srs()
    # rasterize the vector
    with make_temp_dir(prefix='vectorize') as td:
        tvec = os.path.join(td, os.path.basename(vector)[:-4] + '.gml')
        polygonize = (
            'gdal_polygonize.py -f GML {CONNECTEDNESS} {IMAGE} {VECTOR}'
            .format(CONNECTEDNESS=conn_opt, IMAGE=img, VECTOR=tvec)
        )
        emsg = 'Error vectorizing raster {} to {}'.format(img, tvec)
        gso_run(polygonize, emsg)

        if gippy.GeoVector(tvec).nfeatures() != 1:
            ivec = tvec
            tvec = tvec[:-4] + '_dissolve.gml'
            dissolve = (
                'ogr2ogr -f GML {OVEC} {IVEC} -dialect sqlite '
                '-sql "SELECT DN as DN, ST_Union(geometryProperty) as '
                'geometry FROM out GROUP BY DN"'
                .format(OVEC=tvec, IVEC=ivec)
            )
            emsg = 'Error dissolving {} to {}'.format(ivec, tvec)
            gso_run(dissolve, emsg)

        make_final_prod = (
            "ogr2ogr {FMT} -a_srs '{WKT}' '{OVEC}' '{IVEC}'"
            .format(FMT=fmt, WKT=wkt, OVEC=vector, IVEC=tvec)
        )
        emsg = 'Error writing final output from {} to {}'.format(tvec, vector)
        gso_run(make_final_prod, emsg)

    return vector


def mosaic(images, outfile, vector):
    """Mosaic multiple files together without warping."""
    # TODO confirm they all have the same nodata?
    nd = images[0][0].nodata()
    filenames = [i.filename() for i in images]

    # check they all have same projection
    srs_set = {i.srs() for i in images}
    if len(srs_set) > 1:
        raise ValueError("Input files have non-matching projections and must be warped")

    # transform vector to image projection
    extent = wktloads(transform_shape(vector.wkt_geometry(), vector.srs(), srs_set.pop())).bounds
    ullr = "%f %f %f %f" % (extent[0], extent[3], extent[2], extent[1])

    # run merge command
    nodatastr = '-n %s -a_nodata %s -init %s' % (nd, nd, nd)
    cmd = 'gdal_merge.py -o %s -ul_lr %s %s %s' % (outfile, ullr, nodatastr, " ".join(filenames))
    result = subprocess.getstatusoutput(cmd)
    VerboseOut('%s: %s' % (cmd, result), 4)
    imgout = gippy.GeoImage(outfile, True)
    imgout.add_meta(
        'GIPS_MOSAIC_SOURCES',
        ';'.join([os.path.basename(f) for f in filenames])
    )
    for b in range(0, images[0].nbands()):
        imgout[b].add_meta(images[0][b].meta())

    #NOTE: CopyColorTable is not supported
    #imgout.CopyColorTable(images[0])
    return crop2vector(imgout, vector)


def gridded_mosaic(images, outfile, rastermask, interpolation=0):
    """ Mosaic multiple files to grid and mask specified in rastermask """
    nd = images[0][0].nodata()
    mask_img = gippy.GeoImage(rastermask)
    srs = mask_img.srs()
    filenames = [images[0].filename()]
    for f in range(1, len(images)):
        filenames.append(images[f].filename())

    imgout = gippy.GeoImage.create_from(mask_img, outfile,
                                        len(images[0]), images[0].type().string())

    imgout.set_nodata(nd)
    nddata = np.empty((len(images[0]),
                       mask_img.ysize(), mask_img.xsize()))
    nddata[:] = nd
    imgout.write(nddata)
    imgout = None

    # run warp command
    resampler = ['near', 'bilinear', 'cubic']
    cmd = "gdalwarp -t_srs '{}' -r {} {} {}".format(
        srs,
        resampler[interpolation],
        " ".join(filenames),
        outfile
    )
    status, output = subprocess.getstatusoutput(cmd)
    verbose_out(' COMMAND: {}\n exit_status: {}\n output: {}'
                .format(cmd, status, output ), 4)

    imgout = gippy.GeoImage(outfile, True)
    imgout.add_meta(
        'GIPS_GRIDDED_MOSAIC_SOURCES',
        ';'.join([os.path.basename(f) for f in filenames])
    )
    for b in range(0, images[0].nbands()):
        imgout[b].add_meta(images[0][b].meta())
    imgout.add_mask(mask_img[0])
    imgout.save()


def julian_date(date_and_time, variant=None):
    """Returns the julian date for the given datetime object.

    If no variant is chosen, the original julian date is given (days
    since noon, Jan 1, 4713 BC, fractions included).  If a variant is
    chosen, that julian date is returned instead.  Supported variants:
    'modified' (JD - 2400000.5) and 'cnes' (JD - 2433282.5).  See
    https://en.wikipedia.org/wiki/Julian_day for more details.
    """
    mjd_td = date_and_time - datetime.datetime(1858, 11, 17)
    # note day-length isn't constant under UTC due to leap seconds; hopefully this is close enough
    mjd = mjd_td.days + mjd_td.seconds / 86400.0

    offsets = {
        None:       2400000.5,
        'modified': 0.0,
        'cnes':     -33282.0,
    }

    return mjd + offsets[variant]


##############################################################################
# Error handling and script setup & teardown
##############################################################################
_traceback_verbosity = 3    # only print a traceback if the user selects this verbosity or higher
_accumulated_errors = []    # used for tracking success/failure & doing final error reporting when
                            # GIPS is running as a command-line application
_stop_on_error = False      # should GIPS try to recover from errors?  Set by gips_script_setup
# should gips operate "as a library?" Controls whether gips communicates with
# logging or else print(); probably in lockstep with error handler config:
_lib_mode = True
_named_logger = 'gips'      # used by all of gips (instead of one logger per module)


def set_error_handler(handler):
    """Set the active error handler (generally for entire life of process)."""
    global error_handler
    error_handler = handler


def report_error(error, msg_prefix, show_tb=True):
    """Print an error report on stderr, possibly including a traceback.

    Caller can suppress the traceback with show_tb.  The user can suppress
    it via the GIPS global verbosity setting."""
    if show_tb and gippy.Options.verbose() >= _traceback_verbosity:
        verbose_out(msg_prefix + ':', 1, stream=sys.stderr)
        error_text = getattr(error, 'tb_text', 'Error text not found.')
        verbose_out(error_text, 1, stream=sys.stderr)
    else:
        verbose_out(msg_prefix + ': ' + str(error), 1, stream=sys.stderr)


@contextmanager
def lib_error_handler(msg_prefix='Error', continuable=False):
    """Handle errors appropriately for GIPS running as a library:

    Log exceptions in any case, but only re-raise if the error is not
    continuable or current configuration calls for stopping on all errors.
    """
    try:
        yield
    except Exception as e:
        logging.getLogger(_named_logger).exception(msg_prefix) # automatically gets exc_info
        if _stop_on_error or not continuable:
            raise


error_handler = lib_error_handler # set this so gips code can use the right error handler


def errors_exit_status(errors):
    """Determine an apropos exit status given the set of errors."""
    statii = set([e.exc_code if isinstance(e, GipsException) else 1
                  for e in errors])
    return 2 if len(statii) > 1 else list(statii)[0]


def gips_exit():
    """Deliver an error report if needed, then exit."""
    if len(_accumulated_errors) == 0:
        sys.exit(0)
    verbose_out("Fatal: {} error(s) occurred:".format(len(_accumulated_errors)), 1, sys.stderr)
    [report_error(error, error.msg_prefix) for error in _accumulated_errors]
    sys.exit(errors_exit_status(_accumulated_errors))


@contextmanager
def cli_error_handler(msg_prefix='Error', continuable=False):
    """Context manager for uniform error handling for command-line users.

    Exceptions are caught and reported to stderr; _gips_exit() is called
    if halt is indicated.
    """
    try:
        yield
    except Exception as e:
        e.msg_prefix = msg_prefix # for use by gips_exit
        e.tb_text = traceback.format_exc()
        _accumulated_errors.append(e)
        if continuable and not _stop_on_error:
            report_error(e, msg_prefix)
        else:
            gips_exit()


def gips_script_setup(driver_string=None, stop_on_error=False, setup_orm=True):
    """Run this at the beginning of a GIPS CLI program.

    Returns the data class corresponding `driver_string`, or else None.
    `stop_on_error` causes the error handler to ignore continuable flags
    and stop on the first uncaught exception.  If `setup_orm`, configure
    the ORM & its inventory database. Also sets error handling to CLI
    mode and sets gips generally to non-lib-mode.
    """
    global _stop_on_error
    _stop_on_error = stop_on_error
    global _lib_mode
    _lib_mode = False
    set_error_handler(cli_error_handler)
    from gips.inventory import orm # avoids a circular import
    with error_handler():
        # must run before orm.setup
        data_class = None if driver_string is None else import_data_class(driver_string)
        if setup_orm:
            orm.setup()
        return data_class

##############################################################################
# misc
##############################################################################
def configure_logging():
    """Configure the python logging module with gips setting `LOGGING`.

    Use this when you want to use gips as a library but want the convenience
    of configuring logging using a gips setting.
    """
    logging.config.dictConfig(settings().LOGGING)


def prune_unhashable(d):
    """Returns a new dict containing only the hashable values from d.

    Note that an object's hashability can't be determined without attempting
    the hash computation.
    """
    rv = {}
    for k, v in d.items():
        try:
            hash(v)
        except TypeError: # unshashable things raise a TypeError
            continue
        rv[k] = v
    return rv

def stringify_meta_dict(md):
    """Mostly return {str(k): str(v)...}, except for non-dict iterables."""
    def stringify(o):
        if isinstance(o, (str, dict)):
            return str(o)
        try:
            return ','.join(str(i) for i in o)
        except TypeError: # emitted when iter(o) fails
            return str(o)

    return {str(k): stringify(v) for (k, v) in md.items()}

def http_download(url, full_path, chunk_size=512 * 1024):
    """Download a file via http GET, saving to the given file path."""
    r = requests.get(url, stream=True)
    r.raise_for_status()
    with open(full_path, 'wb') as fo:
        # 'if c' filters out keep-alive new chunks
        [fo.write(c) for c in r.iter_content(chunk_size=chunk_size) if c]
