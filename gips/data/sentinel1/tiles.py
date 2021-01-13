from __future__ import print_function

import os
import glob
from collections import defaultdict

import fiona
from fiona.crs import from_epsg

from shapely import geometry, speedups
from shapely.wkt import loads

from osgeo import ogr


speedups.enable()


TEMPDIR = "/archive/vector"


# Tile dimensions
DLON = 0.15
DLAT = 0.15


def write_feature(vector, outfile):
    """ make a shapefile out of a feature """
    import geopandas as gpd

    wkt = vector.wkt_geometry()
    proj = vector.srs()
    gdf = gpd.GeoDataFrame([{'geometry':loads(wkt)}], geometry='geometry', crs=proj)
    print('writing', outfile)
    gdf.to_file(outfile)


def extract(source, target, output, merge, buffer, buffer_after, filter, same_attrs):
    """
    extract features of source vector file that intersect or contain
    features in target vector file
    """
    from rtree import index
    idx = index.Index()
    geoms = {}

    if merge is True and buffer is not None:
        print('Warning: buffer and merge together might produce unexpected results')

    print('initial pass through source tiles')
    with fiona.open(source, 'r') as tiles:
        tiles_crs = tiles.crs
        print('number of source tiles:', len(tiles))
        for tile in tiles:
            fid = int(tile['id'])
            geoms[fid] = geometry.shape(tile['geometry'])
            idx.insert(fid, geoms[fid].bounds)

    print('loop through target parcels against rtree boxes')
    fids = set()
    target_properties = defaultdict(list)
    count = defaultdict(int)
    with fiona.open(target) as parcels:
        if parcels.crs != tiles_crs:
            raise Exception(
                'Input CRS do not match {} {}'.format(parcels.crs, tiles_crs))
        print('number of target parcels:', len(parcels))
        target_schema = parcels.schema

        filtercount = 0
        for parcel in parcels:

            if filter is not None:
                parts = filter.split()
                assert len(parts) == 3, "Bad filter specification"
                attr = parts[0]
                oper = ' '.join(parts[1:])
                statement = "parcel['properties'][attr] {}".format(oper)
                if eval(statement):
                    filtercount += 1
                    continue
            try:
                geom = geometry.shape(parcel['geometry'])
            except Exception:
                print('WARNING: bad geometry', parcel)
                continue

            for hit in idx.intersection(geom.bounds):
                if buffer:
                    geom = geom.buffer(buffer)
                if geoms[hit].intersects(geom):
                    fids.add(hit)
                    target_properties[hit].append(parcel['properties'])
                    count[hit] += 1

        if filter is not None:
            print('filtered target features:', filtercount)

    print('selected tiles:', len(fids))

    print('extract and write selected tiles')
    fp = fiona.open(source, 'r')
    driver = "ESRI Shapefile"

    schema = fp.schema
    schema['properties'].update({'count': 'int:9'})
    if merge is True:
        schema['properties'].update(target_schema['properties'])

    crs = fp.crs
    tilelist = []
    outcount = 0
    with fp as tiles:
        with fiona.open(output, 'w', driver, schema, crs) as outtiles:
            for tile in tiles:
                fid = int(tile['id'])
                if fid in fids:
                    tile['properties'].update({'count': count[fid]})
                    tilelist.append(tile['properties']['tileid'])
                    if merge is True:
                        tprops0 = target_properties[fid][0]
                        if count[fid] > 1 and same_attrs is not None:
                            ok = True
                            for tprops in target_properties[fid][1:]:
                                for same_attr in same_attrs:
                                    if tprops[same_attr] != tprops0[same_attr]:
                                        print('ERROR: same attrs different value')
                                        ok = False
                                        break

                            if ok is False:
                                continue

                        tile['properties'].update(tprops0)

                    if buffer_after is not None:
                        geom = geometry.shape(tile['geometry'])
                        geom = geom.buffer(buffer_after)
                        tile['geometry'] = geometry.mapping(geom)
                    outtiles.write(tile)
                    outcount += 1

    if outcount == 0:
        prefix = os.path.splitext(output)[0]
        assert(len(prefix) > 0)
        cmd = "rm {}.*".format(prefix)
        print('removing empty {}'.format(output))
        print(cmd)
        os.system(cmd)

    assert len(tilelist) == len(set(tilelist))
    return tilelist


def segmentize(geom, mindist):
    # shapely Polygon to wkt
    wkt = geom.wkt
    # create ogr geometry
    geom = ogr.CreateGeometryFromWkt(wkt)
    # densify geometry
    geom.Segmentize(mindist)
    # ogr geometry to wkt
    wkt2 = geom.ExportToWkt()
    # wkt to shapely Polygon
    geom2 = loads(wkt2)
    return geom2


def make_rectangular_tilegrid(outdir, tileid, nxgrid, nygrid, tileid_attribute, filename=None):
    """ create a rectangular grid of tiles that can be trimmed down later """

    htile, vtile = [int(t) for t in tileid.split('-')]

    lon_ul = -180.0 + DLON*htile
    lat_ul = 90.0 - DLAT*vtile

    if filename is None:
        outfile = os.path.join(outdir, '{}_{}_{}.shp'.format(tileid, nxgrid, nygrid))
    else:
        outfile = os.path.join(outdir, filename)

    dlon = DLON
    dlat = DLAT

    schema = {
        'geometry': 'Polygon',
        'properties': {'tileid': 'str', 'h':'int', 'v':'int', 'bounds': 'str'},
    }
    print(dlon, dlat)
    crs = from_epsg(4326)

    # set_trace()

    with fiona.open(outfile, 'w', 'ESRI Shapefile', schema, crs=crs) as shp:
        # latitude
        for i in range(nygrid):
            lat1 = lat_ul - i*dlat
            lat0 = lat1 - dlat
            # longitude
            for j in range(nxgrid):
                lon0 = lon_ul + j*dlon
                lon1 = lon0 + dlon
                poly = geometry.Polygon(
                    [(lon0, lat1), (lon1, lat1), (lon1, lat0), (lon0, lat0), (lon0, lat1)])
                poly = segmentize(poly, dlon/10.)
                h = j + htile
                v = i + vtile
                tileid = "%03d-%03d" % (h, v)
                bounds = str((lon0, lat0, lon1, lat1))
                shp.write({
                    'geometry': geometry.mapping(poly),
                    'properties': {'tileid': tileid,'bounds': bounds, 'h':int(h), 'v':int(v)},
                })

    print('wrote', outfile)
    return(outfile)


def make_tilegrid(shpfile, outdir, outname, tileid_pattern, tileid_attribute, append=False):
    import geopandas as gpd

    gdf = gpd.read_file(shpfile)
    orig_crs = gdf.crs
    gdf = gdf.to_crs(epsg=4326)
    bounds = gdf.bounds

    outfile = os.path.join(outdir, outname)

    if append is True:
        # deal with the case of multiple features
        existing_tiles = gpd.read_file(outfile)

    # UL
    minx = bounds['minx'].min()
    maxy = bounds['maxy'].max()
    # LR
    maxx = bounds['maxx'].max()
    miny = bounds['miny'].min()

    print(minx, maxx, miny, maxy)

    v_ul = int((90. - maxy)/DLON)
    h_ul = int((minx + 180.)/DLON)

    v_lr = int((90. - miny)/DLON)
    h_lr = int((maxx + 180.)/DLON)

    nygrid = v_lr - v_ul + 1
    nxgrid = h_lr - h_ul + 1

    # IMPORTANT - SET TILEID
    tileid = tileid_pattern.format(h_ul, v_ul)

    rectfile = make_rectangular_tilegrid(outdir, tileid, nxgrid, nygrid, tileid_attribute)

    # change crs of rectfile to match crs of shpfile
    gdf = gpd.read_file(rectfile)
    gdf = gdf.to_crs(orig_crs)
    gdf.to_file(rectfile)

    print('extracting', rectfile, shpfile, outfile)
    tilelist = extract(rectfile, shpfile, outfile,
               merge=True, buffer=None, buffer_after=None, filter=None, same_attrs=None)

    if append is True:
        # deal with the case of multiple features open and rewrite tiles.shp
        new_tiles = gpd.read_file(outfile)
        new_tiles = new_tiles.append(existing_tiles, ignore_index=True)
        new_tiles = gpd.GeoDataFrame(new_tiles, crs=existing_tiles.crs, geometry='geometry')
        new_tiles = new_tiles.loc[~new_tiles.tileid.duplicated(keep='first')]
        new_tiles.to_file(outfile)

    print('removing', rectfile)
    # TODO: use temp file
    for file in glob.glob(os.path.splitext(rectfile)[0] + '.*'):
        os.remove(file)

    # return the tilelist
    return tilelist

