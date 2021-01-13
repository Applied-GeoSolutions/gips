
import datetime
import ftplib
import tempfile
import shutil
import os
import glob

import pytest
import sh

from . import util

nh_shp = util.NH_SHP_PATH

STD_ARGS = {
    'modis': ('modis', '-s', nh_shp, '-d', '2012-337', '-v4'),
    'modisndti': ('modis', '-s', nh_shp, '-d', '2012-336', '-v', '4', '-p', 'ndti'),
    'merra': ('merra', '-s', nh_shp, '-d', '2015-135', '-v', '4'),
    'prism': ('prism', '-s', nh_shp, '-d', '1982-12-01,1982-12-03', '-v4'),
    'cdl': ('cdl', '-s', nh_shp, '-d', '2015', '--days', '1,1', '-t', 'NH', '-v4'),
    'landsat': ('landsat', '-s', nh_shp, '-d', '2017-08-01', '-v4'),
    'ard': ('ard', '-s', nh_shp, '-d', '2020-09-01,2020-9-02', '-v4'),
    # Here down, not NH shapefile:
    'aod': ('aod', '-s', util.NE_SHP_PATH, '-d', '2017-004', '-v4'),
    # --overwrite prevents re-use of extant product files to help stabilize
    # test outcomes; see https://gitlab.com/appliedgeosolutions/gips/issues/522
    # 'sentinel1': ('sentinel1', '-s', util.SENTINEL1_TILE_PATH, '-d', '2020-006', '-v4'),
    'sentinel2': ('sentinel2', '-s', util.DURHAM_SHP_PATH, '-d2017-183', '-v4', '--overwrite'),
    'sar': ('sar', '-t', 'N07E099', 'N19E100', 'N00E099', '-d2009,2015', '-v4'),
    'daymet' : ('daymet', '-d', '1993-1-18', '-s', util.DURHAM_SHP_PATH),
    'hls': tuple(('hls -v4 -d2016-156 -s ' + util.DURHAM_SHP_PATH).split()),
}

setup_attempted = []

def setup_repo_data(driver):
    """Use gips_inventory to ensure assets are present."""
    if (driver in setup_attempted or
            not pytest._config_saved_by_gips.getoption('setup_repo')):
        return

    as_path = pytest._config_saved_by_gips.getini('artifact-store-path')

    das_path = os.path.join(as_path, driver) # technically should be der_path

    '''ftp method, not currently in use
    username, password, host, path = [pytest.config.getini(ini) for ini in (
        'artifact-store-user', 'artifact-store-password',
        'artifact-store-host', 'artifact-store-path')]
    url_template = 'ftp://{}:{}@{}/{}/{}/'
    url_head = url_template.format(username, password, host, path, driver)
    sanitized_uh = url_template.format(
        username, '<password>', host, path, driver)

    # first check to see if assets exist already -- if they're in the gips
    # data store, they're probably already cataloged by the ORM
    ftps = ftplib.FTP_TLS(host, username, password)
    ftps.prot_p()
    ftps.cwd(path + '/' + driver)
    remote_files = ftps.nlst()
    '''

    remote_files = os.listdir(das_path)

    local_files = [os.path.basename(fp) for fp in
        glob.glob(os.path.join(
            pytest._config_saved_by_gips.getini('data-repo'),
            driver, 'tiles', '*/*/*'))]

    if set(remote_files).issubset(set(local_files)):
        print(driver, 'asset files already present; no setup needed')
        return

    print('Installing', driver, 'assets from', das_path)
    try:
        temp_dir = tempfile.mkdtemp()
        with sh.pushd(temp_dir):
            #sh.wget('--recursive', '--no-directories', url_head)
            for fn in remote_files:
                shutil.copy(os.path.join(das_path, fn), temp_dir)
            sh.gips_archive(driver, '-v99',
                            _err='/dev/stderr', _out='/dev/stdout')
    finally:
        shutil.rmtree(temp_dir)
    print(driver, "data installation complete.")
