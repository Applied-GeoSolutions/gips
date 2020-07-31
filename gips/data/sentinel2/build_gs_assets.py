#!/usr/bin/env python3

from pprint import pprint
from xml.etree import ElementTree

from gips.data.sentinel2 import sentinel2Asset

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
    'tile-md': "S2_Level-1C_Tile1_Metadata",
    'asset-md': "S2_Level-1C_Product_Metadata",
}

_raster_object_id_pile = (
    # respects raster order of 1 through 8, then 8A, then the rest
    # (I have no idea what this naming scheme is meant to represent):
    'IMG_DATA_Band_60m_1_Tile1_Data',
    'IMG_DATA_Band_10m_1_Tile1_Data',
    'IMG_DATA_Band_10m_2_Tile1_Data',
    'IMG_DATA_Band_10m_3_Tile1_Data',
    'IMG_DATA_Band_20m_1_Tile1_Data',
    'IMG_DATA_Band_20m_2_Tile1_Data',
    'IMG_DATA_Band_20m_3_Tile1_Data',
    'IMG_DATA_Band_10m_4_Tile1_Data',
    'IMG_DATA_Band_20m_4_Tile1_Data', # band 8A, the LUNATIC BAND
    'IMG_DATA_Band_60m_2_Tile1_Data',
    'IMG_DATA_Band_60m_3_Tile1_Data',
    'IMG_DATA_Band_20m_5_Tile1_Data',
    'IMG_DATA_Band_20m_6_Tile1_Data',
)

_raster_suffixes = ( # for validation
    'B01.jp2', 'B02.jp2', 'B03.jp2', 'B04.jp2', 'B05.jp2', 'B06.jp2', 'B07.jp2',
    'B08.jp2', 'B8A.jp2', 'B09.jp2', 'B10.jp2', 'B11.jp2', 'B12.jp2',
)


def get_url_for_object_id(path_prefix, manifest_root, data_object_id):
    """Locates the given dataObject ID and returns the relative file path for it.

    manifest_root should be the root xml Element object of the sentinel-2
    manifest xml file stored with each sentinel-2 asset. The path returned is
    the relative path to the file identified by the given dataObject ID.
    """
    file_loc_elem, = manifest_root.findall(
        "./dataObjectSection/dataObject[@ID='{}']/byteStream/fileLocation".format(data_object_id))
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


def find_asset_keys(manifest_content, path_prefix, cloud_cover_pct):
    """Locates the needed asset keys in the content of the manifest.safe file.

    This file is included in sentinel-2 assets and can be found on google storage.
    Output is suitable for passing to sentinel2Asset.download_gs to save in a file.
    """
    manifest_root = ElementTree.fromstring(manifest_content) # returns Element
    bands = [get_url_for_object_id(path_prefix, manifest_root, roid)
             for roid in _raster_object_id_pile]
    validate_raster_url_pile(bands)
    keys = {'spectral-bands': bands,
            'cloud-cover': cloud_cover_pct}
    # add in metadata urls eg 'asset-md'
    for key, object_id in _metadata_object_id_pile.items():
        keys[key] = get_url_for_object_id(path_prefix, manifest_root, object_id)
    return keys

def save_asset_json(destination_path, proto_asset):
    """Take the output from find_asset_keys and finalize it, saving to a json file."""
    sentinel2Asset.download_gs(destination_path, proto_asset)


if __name__ == '__main__':
    """This is a test execution and needs a manifest.safe file:"""
    # sample fn inputs
    local_asset_path = 'S2B_MSIL1C_20181202T213359_N0207_R057_T56CMB_20181202T222246.SAFE_gs.json'
    path_prefix = 'tiles/56/C/MB/S2B_MSIL1C_20181202T213359_N0207_R057_T56CMB_20181202T222246.SAFE'
    manifest_path = './tiles_56_C_MB_S2B_MSIL1C_20181202T213359_N0207_R057_T56CMB_20181202T222246.SAFE_manifest.safe'

    with open(manifest_path, 'r') as fo:
        content = fo.read()

    proto_asset = find_asset_keys(content, path_prefix, 35.3) # made-up cloud cover
    save_asset_json(local_asset_path, proto_asset)

    print("GOT URLS:")
    pprint(proto_asset)
