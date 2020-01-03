#!/usr/bin/env bash

# Installs system packages needed for gips.  Should be run as root/sudo.
# Run via `source` or as its own process.

set -e -v

# installing gdal 2 via ubuntugis ppa:
apt-get update -y
apt-get install -y software-properties-common
add-apt-repository -y ppa:ubuntugis/ppa
apt-get update -y

# installing gips essentials:
# TODO not sure why need both curl & wget
# TODO installing system pip means pip can't upgrade itself without breaking
# TODO not clear if any of these are necessary; they were part of the gippy 0 + py2 installer:
#sudo apt-get install virtualenv libboost-all-dev libfreetype6-dev libgnutls-dev \
#   libatlas-base-dev python-numpy python-scipy swig2.0
#   # also this came from one of the docker files, purpose uncertain:  libcurl4-gnutls-dev
# would be better to install python3-gdal via pypi package GDAL, but it causes conflicts
# some tools (such as gdal_polygonize.py) are only included with python-gdal
#   (that is, python 2), and not python3-gdal; it's not known if python 3
#   versions of these tools exist.
# TODO gfortran is only needed for sixs; remove it to the sixs install script
apt-get install -y \
    gdal-bin libgdal-dev python-dev python3-dev python3-gdal python-gdal \
    curl wget gfortran libgnutls28-dev

# needed for coregistration routines
curl -o /usr/local/bin/ortho \
     https://gitlab.com/daganinc/arop/raw/v2.2.9/bin/ortho?inline=false \
    && chmod +x /usr/local/bin/ortho

# can't presume user wants ubuntu's python3-pip because it's common practice to install
# it themselves, so need to check first
if command -v pip3 &>/dev/null; then
    echo 'pip3 found in PATH; not installing'
else
    echo 'pip3 not found in PATH; installing:'
    apt-get install -y python3-pip
fi
