from collections import OrderedDict

expectations = OrderedDict([
 # t_process[sentinel1-sigma0] recording:
 ('sigma0',
  [('sentinel1/tiles/563-313/2020006/563-313_2020006_S1_sigma0.tif',
    'raster',
    'gdalinfo-stats',
    ['Driver: GTiff/GeoTIFF',
     'Size is 1500, 1500',
     'Coordinate System is:',
     'GEOGCS["WGS 84",',
     '    DATUM["WGS_1984",',
     '        SPHEROID["WGS 84",6378137,298.25722356,',
     '            AUTHORITY["EPSG","7030"]],',
     '        AUTHORITY["EPSG","6326"]],',
     '    PRIMEM["Greenwich",0],',
     '    UNIT["degree",0.01745329],',
     '    AUTHORITY["EPSG","4326"]]',
     'Origin = (-95.54999999,43.04999999)',
     'Pixel Size = (0.00010000,-0.00010000)',
     'Metadata:',
     '  AREA_OR_POINT=Area',
     '  TIFFTAG_RESOLUTIONUNIT=1 (unitless)',
     '  TIFFTAG_XRESOLUTION=1',
     '  TIFFTAG_YRESOLUTION=1',
     'Image Structure Metadata:',
     '  INTERLEAVE=PIXEL',
     'Corner Coordinates:',
     'Upper Left  ( -95.5500000,  43.0500000) ( 95d33\' 0.00"W, 43d 3\' 0.00"N)',
     'Lower Left  ( -95.5500000,  42.9000000) ( 95d33\' 0.00"W, 42d54\' 0.00"N)',
     'Upper Right ( -95.4000000,  43.0500000) ( 95d24\' 0.00"W, 43d 3\' 0.00"N)',
     'Lower Right ( -95.4000000,  42.9000000) ( 95d24\' 0.00"W, 42d54\' 0.00"N)',
     'Center      ( -95.4750000,  42.9750000) ( 95d28\'30.00"W, 42d58\'30.00"N)',
     'Band 1 Block=1500x1 Type=Float32, ColorInterp=Gray',
     '  Minimum=-43.087, Maximum=2.850, Mean=-20.386, StdDev=3.374',
     '  Metadata:',
     '    STATISTICS_MAXIMUM=2.84963035',
     '    STATISTICS_MEAN=-20.38625096',
     '    STATISTICS_MINIMUM=-43.08692169',
     '    STATISTICS_STDDEV=3.37426050',
     '    STATISTICS_VALID_PERCENT=100',
     'Band 2 Block=1500x1 Type=Float32, ColorInterp=Undefined',
     '  Minimum=-30.473, Maximum=15.594, Mean=-11.180, StdDev=2.511',
     '  Metadata:',
     '    STATISTICS_MAXIMUM=15.59434223',
     '    STATISTICS_MEAN=-11.17951949',
     '    STATISTICS_MINIMUM=-30.47262382',
     '    STATISTICS_STDDEV=2.51056528',
     '    STATISTICS_VALID_PERCENT=100'])]),
])
