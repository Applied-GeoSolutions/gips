from collections import OrderedDict

expectations = OrderedDict([
 # t_project[sentinel2-cfmask] recording:
 ('cfmask',
  [('0/2017183_S2A_cfmask.tif',
    'raster',
    'gdalinfo-stats',
    ['Driver: GTiff/GeoTIFF',
     'Size is 42, 35',
     'Coordinate System is:',
     'PROJCS["WGS 84 / UTM zone 19N",',
     '    GEOGCS["WGS 84",',
     '        DATUM["WGS_1984",',
     '            SPHEROID["WGS 84",6378137,298.25722356,',
     '                AUTHORITY["EPSG","7030"]],',
     '            AUTHORITY["EPSG","6326"]],',
     '        PRIMEM["Greenwich",0,',
     '            AUTHORITY["EPSG","8901"]],',
     '        UNIT["degree",0.01745329,',
     '            AUTHORITY["EPSG","9122"]],',
     '        AUTHORITY["EPSG","4326"]],',
     '    PROJECTION["Transverse_Mercator"],',
     '    PARAMETER["latitude_of_origin",0],',
     '    PARAMETER["central_meridian",-69],',
     '    PARAMETER["scale_factor",0.9996],',
     '    PARAMETER["false_easting",500000],',
     '    PARAMETER["false_northing",0],',
     '    UNIT["metre",1,',
     '        AUTHORITY["EPSG","9001"]],',
     '    AXIS["Easting",EAST],',
     '    AXIS["Northing",NORTH],',
     '    AUTHORITY["EPSG","32619"]]',
     'Origin = (341557.17135443,4780009.98284440)',
     'Pixel Size = (100.00000000,-100.00000000)',
     'Metadata:',
     '  AREA_OR_POINT=Area',
     '  FMASK_0=nodata',
     '  FMASK_1=valid',
     '  FMASK_2=cloud',
     '  FMASK_3=cloud shadow',
     '  FMASK_4=snow',
     '  FMASK_5=water',
     '  GIPS_Sentinel2_Version=0.1.1',
     '  '
     'GIPS_Source_Assets=S2A_MSIL1C_20170702T154421_N0205_R011_T19TCH_20170702T154703.zip',
     '  GIPS_Version=0.0.0-dev',
     'Image Structure Metadata:',
     '  INTERLEAVE=BAND',
     'Corner Coordinates:',
     'Upper Left  (  341557.171, 4780009.983) ( 70d56\'55.70"W, 43d 9\'22.51"N)',
     'Lower Left  (  341557.171, 4776509.983) ( 70d56\'52.10"W, 43d 7\'29.11"N)',
     'Upper Right (  345757.171, 4780009.983) ( 70d53\'49.83"W, 43d 9\'25.63"N)',
     'Lower Right (  345757.171, 4776509.983) ( 70d53\'46.32"W, 43d 7\'32.23"N)',
     'Center      (  343657.171, 4778259.983) ( 70d55\'20.99"W, 43d 8\'27.38"N)',
     'Band 1 Block=42x35 Type=Byte, ColorInterp=Gray',
     '  Minimum=1.000, Maximum=5.000, Mean=1.424, StdDev=0.758',
     '  NoData Value=0',
     '  Metadata:',
     '    STATISTICS_MAXIMUM=5',
     '    STATISTICS_MEAN=1.42372881',
     '    STATISTICS_MINIMUM=1',
     '    STATISTICS_STDDEV=0.75808388',
     '    STATISTICS_VALID_PERCENT=48.16'])]),

 # t_project[sentinel2-crcm] recording:
 ('crcm',
  [('0/2017183_S2A_crcm.tif',
    'raster',
    'gdalinfo-stats',
    ['Driver: GTiff/GeoTIFF',
     'Size is 42, 35',
     'Coordinate System is:',
     'PROJCS["WGS 84 / UTM zone 19N",',
     '    GEOGCS["WGS 84",',
     '        DATUM["WGS_1984",',
     '            SPHEROID["WGS 84",6378137,298.25722356,',
     '                AUTHORITY["EPSG","7030"]],',
     '            AUTHORITY["EPSG","6326"]],',
     '        PRIMEM["Greenwich",0,',
     '            AUTHORITY["EPSG","8901"]],',
     '        UNIT["degree",0.01745329,',
     '            AUTHORITY["EPSG","9122"]],',
     '        AUTHORITY["EPSG","4326"]],',
     '    PROJECTION["Transverse_Mercator"],',
     '    PARAMETER["latitude_of_origin",0],',
     '    PARAMETER["central_meridian",-69],',
     '    PARAMETER["scale_factor",0.9996],',
     '    PARAMETER["false_easting",500000],',
     '    PARAMETER["false_northing",0],',
     '    UNIT["metre",1,',
     '        AUTHORITY["EPSG","9001"]],',
     '    AXIS["Easting",EAST],',
     '    AXIS["Northing",NORTH],',
     '    AUTHORITY["EPSG","32619"]]',
     'Origin = (341557.17135443,4780009.98284440)',
     'Pixel Size = (100.00000000,-100.00000000)',
     'Metadata:',
     '  AOD Source=MODIS (MOD08_D3) spatial average',
     '  AOD Value=0.05450000',
     '  AREA_OR_POINT=Area',
     '  GIPS_Sentinel2_Version=0.1.1',
     '  '
     'GIPS_Source_Assets=S2A_MSIL1C_20170702T154421_N0205_R011_T19TCH_20170702T154703.zip',
     '  GIPS_Version=0.0.0-dev',
     'Image Structure Metadata:',
     '  INTERLEAVE=BAND',
     'Corner Coordinates:',
     'Upper Left  (  341557.171, 4780009.983) ( 70d56\'55.70"W, 43d 9\'22.51"N)',
     'Lower Left  (  341557.171, 4776509.983) ( 70d56\'52.10"W, 43d 7\'29.11"N)',
     'Upper Right (  345757.171, 4780009.983) ( 70d53\'49.83"W, 43d 9\'25.63"N)',
     'Lower Right (  345757.171, 4776509.983) ( 70d53\'46.32"W, 43d 7\'32.23"N)',
     'Center      (  343657.171, 4778259.983) ( 70d55\'20.99"W, 43d 8\'27.38"N)',
     'Band 1 Block=42x35 Type=Int16, ColorInterp=Gray',
     '  Minimum=-5683.000, Maximum=7681.000, Mean=4050.129, StdDev=1902.494',
     '  NoData Value=-32768',
     '  Offset: 0,   Scale:0.0001',
     '  Metadata:',
     '    STATISTICS_MAXIMUM=7681',
     '    STATISTICS_MEAN=4050.12853107',
     '    STATISTICS_MINIMUM=-5683',
     '    STATISTICS_STDDEV=1902.49367627',
     '    STATISTICS_VALID_PERCENT=48.16'])]),

 # t_project[sentinel2-evi-toa] recording:
 ('evi-toa',
  [('0/2017183_S2A_evi-toa.tif',
    'raster',
    'gdalinfo-stats',
    ['Driver: GTiff/GeoTIFF',
     'Size is 42, 35',
     'Coordinate System is:',
     'PROJCS["WGS 84 / UTM zone 19N",',
     '    GEOGCS["WGS 84",',
     '        DATUM["WGS_1984",',
     '            SPHEROID["WGS 84",6378137,298.25722356,',
     '                AUTHORITY["EPSG","7030"]],',
     '            AUTHORITY["EPSG","6326"]],',
     '        PRIMEM["Greenwich",0,',
     '            AUTHORITY["EPSG","8901"]],',
     '        UNIT["degree",0.01745329,',
     '            AUTHORITY["EPSG","9122"]],',
     '        AUTHORITY["EPSG","4326"]],',
     '    PROJECTION["Transverse_Mercator"],',
     '    PARAMETER["latitude_of_origin",0],',
     '    PARAMETER["central_meridian",-69],',
     '    PARAMETER["scale_factor",0.9996],',
     '    PARAMETER["false_easting",500000],',
     '    PARAMETER["false_northing",0],',
     '    UNIT["metre",1,',
     '        AUTHORITY["EPSG","9001"]],',
     '    AXIS["Easting",EAST],',
     '    AXIS["Northing",NORTH],',
     '    AUTHORITY["EPSG","32619"]]',
     'Origin = (341557.17135443,4780009.98284440)',
     'Pixel Size = (100.00000000,-100.00000000)',
     'Metadata:',
     '  AREA_OR_POINT=Area',
     '  GIPS_Sentinel2_Version=0.1.1',
     '  '
     'GIPS_Source_Assets=S2A_MSIL1C_20170702T154421_N0205_R011_T19TCH_20170702T154703.zip',
     '  GIPS_Version=0.0.0-dev',
     'Image Structure Metadata:',
     '  INTERLEAVE=BAND',
     'Corner Coordinates:',
     'Upper Left  (  341557.171, 4780009.983) ( 70d56\'55.70"W, 43d 9\'22.51"N)',
     'Lower Left  (  341557.171, 4776509.983) ( 70d56\'52.10"W, 43d 7\'29.11"N)',
     'Upper Right (  345757.171, 4780009.983) ( 70d53\'49.83"W, 43d 9\'25.63"N)',
     'Lower Right (  345757.171, 4776509.983) ( 70d53\'46.32"W, 43d 7\'32.23"N)',
     'Center      (  343657.171, 4778259.983) ( 70d55\'20.99"W, 43d 8\'27.38"N)',
     'Band 1 Block=42x35 Type=Int16, ColorInterp=Gray',
     '  Minimum=-2574.000, Maximum=11507.000, Mean=6485.282, StdDev=2303.892',
     '  NoData Value=-32768',
     '  Offset: 0,   Scale:0.0001',
     '  Metadata:',
     '    STATISTICS_MAXIMUM=11507',
     '    STATISTICS_MEAN=6485.28248587',
     '    STATISTICS_MINIMUM=-2574',
     '    STATISTICS_STDDEV=2303.89155042',
     '    STATISTICS_VALID_PERCENT=48.16'])]),
])
