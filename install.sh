#!/usr/bin/env bash

# This is a system install script for gips, known to work for Ubuntu 18.04.
# Call it with a root path to your gips data repository root and email
# address:
#
#   ./install.sh /archive user@example.com
#
# It installs system packages via apt and pip3 so should be run as root/sudo.


die () {
    echo >&2 "$@"
    exit 1
}

[ "$#" -eq 2 ] || die "Usage:  $0 REPO_ROOT EMAIL"
# setuptools has no way to filter out a specific python file so:
[ -e gips/settings.py ] && die "gips/settings.py exists; shouldn't continue"

set -e
set -v

source install-sys-deps.sh # mostly through apt-get install

# TODO optionally install in a virtualenv:
# virtualenv --system-site-packages venv; source venv/bin/activate


### python deps (venv-able)
# Right now dependency_links is being removed, probably, from setuptools. The
# "foo @ url" syntax isn't documented and doesn't seem to work. So, have to
# install things directly:
# more funny deps that are difficult to install with setuptools:
pip3 install -U numpy # gippy has some kind of problem otherwise
c_url=https://bitbucket.org/chchrsc
pip3 install -U "${c_url}/rios/downloads/rios-1.4.3.zip#egg=rios-1.4.3"
pip3 install -U "${c_url}/python-fmask/downloads/python-fmask-0.5.0.zip#egg=python-fmask-0.5.0"


### gips install (venv-able)
# system install, not venv nor developer install:
python3 setup.py install
# TODO if this is extended to support developer and/or venv installs:
# pip3 install -r dev_requirements.txt # if you wish to run the test suite; CF docker/
# then one of setup.py or pip3 -e:
#python3 setup.py develop
# not sure if option still supported, and not sure if needed at all:
#                   vvvvvvvvvvvvvvvvvvv
#pip3 install --process-dependency-links -e .


### configuration (varies by install type?  I guess?)
# TODO used to do config but it's not clear that the email option is needed anymore:
gips_config env --repos "$1" --email "$2"

# TODO add advice for EARTHDATA_USER & EARTHDATA_PASS?
# To establish user-specific settings, run `gips_config user` then edit ~/.gips/'
