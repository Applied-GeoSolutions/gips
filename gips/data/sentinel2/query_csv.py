#!/usr/bin/env python3

import csv
import contextlib
from datetime import date
import datetime
import pprint


@contextlib.contextmanager
def csv_dict_reader(csv_path):
    with open(csv_path, newline='') as fo: # newline='' is official csv docs' recommendation
        yield csv.DictReader(fo)


def query_index_csv(tiles, start_date, end_date, cloud_cover_threshold, csv_path):
    """A generator that searches the sentinel-2 index file.

    Generates tuples resembling (tile, date, cloud_cover_percent, base_url).

    This is slow, about 1m45s on a container on an old-ish laptop (as of
    august 2020 the index file is 14 million lines). No attempt has been made
    to optimize I/O, which is probably a bottleneck, so probably look there
    first to try to optimize (maybe chunking reads differently?).
    """
    assert start_date <= end_date # sanity check
    with csv_dict_reader(csv_path) as dr:
        for r in dr:
            t = r['MGRS_TILE']
            if t not in tiles:
                continue

            cc = float(r['CLOUD_COVER'])
            if cc > cloud_cover_threshold:
                continue

            d_raw = r['SENSING_TIME'] # example raw date: 2020-07-06T18:09:31.042000Z
            # couldn't be bothered to look up the sentinel-2 date format, and gips.data.sentinel2
            # doesn't have a separate parser:
            d = date(int(d_raw[0:4]), int(d_raw[5:7]), int(d_raw[8:10]))
            if start_date <= d <= end_date:
                bu = r['BASE_URL']
                print("MATCH:", bu)
                yield (t, d, cc, bu)


def test_execution(full_run=False):
    # cut millions of lines down to 100,000: gunzip -c index.csv.gz | head -n100000 > test-index.csv
    csv_path = './test-index.csv'
    if full_run:
        csv_path = './index.csv'
    # this date & tile set grabs these two plus one more asset if you use the 100k line csv:
    # L1C_T20MKU_A023974_20200124T143654,41.3563 # cc pct
    # L1C_T57MYM_A010695_20190324T233816,25.4006 # cc pct
    tiles = '20MKU', '57MYM'
    dates = date(2019, 3, 20), date(2020, 1, 25)
    ccthresh = 50.0
    rv = list(query_index_csv(tiles, *dates, ccthresh, csv_path))
    print("GOT results list:")
    pprint.pprint(rv)


if __name__ == '__main__':
    test_execution()
