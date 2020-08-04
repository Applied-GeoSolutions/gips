#!/usr/bin/env python3

import os
from pprint import pprint
from xml.etree import ElementTree
from urllib.parse import urlparse

import boto3
import requests

from gips.data.sentinel2 import sentinel2Asset, sentinel2Data



# TODO, some of this, atm:
"""Builds sentinel2 google storage assets (asset type L1CGS).

To avoid doing auth, it searches for known assets in a file that must be downloaded separately, index.cs.gz.
It then gets a metadata file from the cloud and builds the asset json file that
the sentinel2 driver expects.

See https://cloud.google.com/storage/docs/public-datasets/sentinel-2.
"""


# each dataObject with a given ID should be unique and singular
_metadata_object_id_pile = { # mapping from asset's keys to manifest XML IDs
    'datastrip-md': "S2_Level-1C_Datastrip1_Metadata",
    # 'tile-md': "S2_Level-1C_Tile1_Metadata",
    'asset-md': "S2_Level-1C_Product_Metadata",
}

_raster_object_id_pile = (
    # respects raster order of 1 through 8, then 8A, then the rest
    # (I have no idea what this naming scheme is meant to represent):
    'IMG_DATA_Band_60m_1_Tile*_Data',
    'IMG_DATA_Band_10m_1_Tile*_Data',
    'IMG_DATA_Band_10m_2_Tile*_Data',
    'IMG_DATA_Band_10m_3_Tile*_Data',
    'IMG_DATA_Band_20m_1_Tile*_Data',
    'IMG_DATA_Band_20m_2_Tile*_Data',
    'IMG_DATA_Band_20m_3_Tile*_Data',
    'IMG_DATA_Band_10m_4_Tile*_Data',
    'IMG_DATA_Band_20m_4_Tile*_Data', # band 8A, the LUNATIC BAND
    'IMG_DATA_Band_60m_2_Tile*_Data',
    'IMG_DATA_Band_60m_3_Tile*_Data',
    'IMG_DATA_Band_20m_5_Tile*_Data',
    'IMG_DATA_Band_20m_6_Tile*_Data',
)

_raster_suffixes = ( # for validation
    'B01.jp2', 'B02.jp2', 'B03.jp2', 'B04.jp2', 'B05.jp2', 'B06.jp2', 'B07.jp2',
    'B08.jp2', 'B8A.jp2', 'B09.jp2', 'B10.jp2', 'B11.jp2', 'B12.jp2',
)


def get_url_for_object_id(path_prefix, manifest_root, data_object_id, tile=None):
    """Locates the given dataObject ID and returns the relative file path for it.

    manifest_root should be the root xml Element object of the sentinel-2
    manifest xml file stored with each sentinel-2 asset. The path returned is
    the relative path to the file identified by the given dataObject ID.
    """
    file_loc_elems = manifest_root.findall(
        "./dataObjectSection/dataObject[@ID='{}']/byteStream/fileLocation".format(data_object_id))
    if tile:
        for elem in file_loc_elems:
            if tile in elem.attrib['href']:
                file_loc_elem = elem
                break
    else:
        file_loc_elem = file_loc_elems[0]
    # the fileLocationElement's href attrib has the relative path (it lies and claims to be a URL):
    relative_path = file_loc_elem.attrib['href'].lstrip('./') # starts with './'
    # to do http urls in the asset:
    # _url_base = sentinel2Asset._gs_object_url_base.format(sentinel2Asset.gs_bucket_name)
    # return _url_base + path_prefix + '/' + relative_path
    return path_prefix + '/' + relative_path


def validate_raster_url_pile(pile):
    broken = [(suffix, url)
              for (suffix, url) in zip(_raster_suffixes, pile) if not url.endswith(suffix)]
    if broken:
        raise ValueError("These URLs didn't match these suffixes:", broken)


def find_asset_keys(manifest_content, path_prefix, tile, cloud_cover_pct):
    """Locates the needed asset keys in the content of the manifest.safe file.

    This file is included in sentinel-2 assets and can be found on google storage.
    Output is suitable for passing to sentinel2Asset.download_gs to save in a file.
    """
    manifest_root = ElementTree.fromstring(manifest_content) # returns Element
    bands = [get_url_for_object_id(path_prefix, manifest_root, roid, tile)
             for roid in _raster_object_id_pile]
    validate_raster_url_pile(bands)
    keys = {'spectral-bands': bands,
            'cloud-cover': cloud_cover_pct}
    # add in metadata urls eg 'asset-md'
    for key, object_id in _metadata_object_id_pile.items():
        keys[key] = get_url_for_object_id(path_prefix, manifest_root, object_id)

    keys['tile-md'] = get_url_for_object_id(path_prefix, manifest_root, 'S2_Level-1C_Tile*_Metadata')
    return keys


def save_asset_json(destination_path, proto_asset):
    """Take the output from find_asset_keys and finalize it, saving to a json file."""
    sentinel2Asset.download_gs(destination_path, proto_asset)


def get_manifest_content(base_url):
    """Returns the manifest.safe file's content for the given base url.

    BASE_URL comes from inde.csv.gz and looks like this:
    gs://gcp-public-data-sentinel-2/tiles/56/C/MB/
            S2B_MSIL1C_20181202T213359_N0207_R057_T56CMB_20181202T222246.SAFE
    """
    http_url_base = sentinel2Asset._gs_object_url_base.format(sentinel2Asset.gs_bucket_name)
    url = http_url_base + os.path.join(urlparse(base_url).path, 'manifest.safe').lstrip('/')
    r = requests.get(url)
    r.raise_for_status()
    return r.text


def fetch_assets_to_s3(tiles, dates, pcloud, csv_path, bucket):
    from .query_csv import make_assets_from_query

    s2_repo = sentinel2Asset.get_setting('repository')
    s2_stage = os.path.join(s2_repo, 'stage')
    bucket = boto3.resource('s3').Bucket(bucket)

    make_assets_from_query(tiles, *dates, pcloud, csv_path, s2_stage)

    sentinel2Data.archive_assets(os.path.join(s2_repo, 'stage'))

    for root, _, files in os.walk(os.path.join(s2_repo, 'tiles')):
        for f in files:
            full_path = os.path.join(root, f)
            if os.path.isfile(full_path):
                prefix = full_path.replace(
                    s2_repo.replace('sentinel2', ''),
                    ''
                ).lstrip("/")
                bucket.upload_file(full_path, prefix)


def build_asset_from_base_url(base_url, cloud_cover_pct, destination_path):
    """Build a sentinel-2 L1CGS asset json file and save it to the given path.

    The base_url identifies a specific asset; its manifest.safe is read from
    the cloud to fetch needed content for the asset file. cloud_cover_pct is
    likewise stored in the file.
    """
    content = get_manifest_content(base_url)
    path_prefix = urlparse(base_url).path.lstrip('/')
    # Appologies for this icky way of extracting the tile name from the url.
    tile = os.path.dirname(path_prefix.lstrip("tiles/")).replace('/', '')
    proto_asset = find_asset_keys(content, path_prefix, tile, cloud_cover_pct)
    save_asset_json(destination_path, proto_asset)
    return proto_asset


def test_execution():
    """Uses a hardcoded asset choice to create an asset and save it locally."""
    # sample fn inputs
    local_asset_path = 'S2B_MSIL1C_20181202T213359_N0207_R057_T56CMB_20181202T222246.SAFE_gs.json'
    # path_prefix = 'tiles/56/C/MB/S2B_MSIL1C_20181202T213359_N0207_R057_T56CMB_20181202T222246.SAFE'
    base_url = ('gs://gcp-public-data-sentinel-2/tiles/56/C/MB/'
                'S2B_MSIL1C_20181202T213359_N0207_R057_T56CMB_20181202T222246.SAFE')
    # made up cloud cover:
    proto_asset = build_asset_from_base_url(base_url, 35.3, local_asset_path)
    print("GOT URLS:")
    pprint(proto_asset)


if __name__ == '__main__':
    test_execution()
