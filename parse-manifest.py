#!/usr/bin/env python3

from xml.etree import ElementTree

_gs_object_url_base = 'http://storage.googleapis.com/{}/' # taken from gips
gs_bucket_name = 'gcp-public-data-sentinel-2'
path_head = 'tiles/56/C/MB/S2B_MSIL1C_20181202T213359_N0207_R057_T56CMB_20181202T222246.SAFE'

# glue relative paths found below onto this:
url_base = _gs_object_url_base.format(gs_bucket_name) + path_head


manifest_path = './tiles_56_C_MB_S2B_MSIL1C_20181202T213359_N0207_R057_T56CMB_20181202T222246.SAFE_manifest.safe'
with open(manifest_path, 'r') as fo:
    content = fo.read()

manifest_root = ElementTree.fromstring(content) # returns Element

# should be only one dataObject with a given ID
band_1_id = 'IMG_DATA_Band_60m_1_Tile1_Data'

# the fileLocationElement's href attrib has the relative path (it lies and claims to be a URL):
file_loc_elem, = manifest_root.findall(
    "./dataObjectSection/dataObject[@ID='{}']/byteStream/fileLocation".format(band_1_id))
rel_path = file_loc_elem.attrib['href'] # starts with './'

url = url_base + rel_path.lstrip('.')

print("GOT PATH:", rel_path)
print("GOT URL:", url)
