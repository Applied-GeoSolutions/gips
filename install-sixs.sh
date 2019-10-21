#!/bin/bash

# Downloads & installs sixs, aka 6S; for internet searches try '6S atmospheric model'.

# if you have the sixs binary handy you can copy it into place instead:
#apt-get install -y libgfortran3 && cp sixs /usr/local/bin && chmod +x /usr/local/bin/sixs

set -e -v

tmp_dir_name=$(mktemp -d)
cd "$tmp_dir_name"
# why not the official download?  This seems to be a 3rd party that makes py6s:
curl http://rtwilson.com/downloads/6SV-1.1.tar | tar -x
cd 6SV1.1
# makefile munging is brittle and risky; is there no better alternative?
# note a binary named sixsV1.1 is included in the tarball; compilation overwrites it
sed -i 's/g77/gfortran -std=legacy -ffixed-line-length-none -ffpe-summary=none/g' Makefile
make
mv sixsV1.1 /usr/local/bin/sixs
cd /tmp
rm -r "$tmp_dir_name"
