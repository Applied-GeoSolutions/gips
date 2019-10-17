#!/usr/bin/env bash

set -e
set -v

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
# would be better to install python3-gdal via pypi package GDAL, but it causes conflicts
apt-get install -y \
    gdal-bin libgdal-dev python-dev python3-dev python3-gdal python3-pip \
    curl wget gfortran libgnutls28-dev

# more funny deps that are difficult to install with setuptools:
pip3 install -U numpy # gippy has some kind of problem otherwise
c_url=https://bitbucket.org/chchrsc
pip3 install -U "${c_url}/rios/downloads/rios-1.4.3.zip#egg=rios-1.4.3"
pip3 install -U "${c_url}/python-fmask/downloads/python-fmask-0.5.0.zip#egg=python-fmask-0.5.0"

# setuptools has no way to filter out a specific python file so:
if [ -e gips/settings.py ]; then
    echo "gips/settings.py exists; shouldn't continue" >/dev/stderr
    exit 1
fi
# system install, not venv nor developer install:
python3 setup.py install


# TODO if this is extended to support developer and/or venv installs:
# pip3 install -r dev_requirements.txt # if you wish to run the test suite; CF docker/
# then one of setup.py or pip3 -e:
#python3 setup.py develop
# not sure if option still supported, and not sure if needed at all:
#                   vvvvvvvvvvvvvvvvvvv
#pip3 install --process-dependency-links -e .

# TODO used to do config but it's not clear that the email option is needed anymore:
#gips_config env -r $ARCHIVEDIR -e $EMAIL # eg -r /archive -e nobody@example.com
#gips_config user # TODO does this set up ~/.gips/ ?

# TODO make an option
# virtualenv --system-site-packages venv
# source venv/bin/activate

# TODO UX?
#echo "Now edit settings.py for things like EARTHDATA password"
#echo "gips_project modis --fetch -s gips/test/NHseacoast.shp -d 2017-5-25 -v5 -p ndvi8"
