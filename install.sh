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
source install-py-deps.sh

# TODO optionally install in a virtualenv:
# virtualenv --system-site-packages venv; source venv/bin/activate

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
