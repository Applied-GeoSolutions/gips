#!/usr/bin/env bash

# Installs system packages needed for gips; no need to run as root if a
# virtualenvironment is activated.  Run via `source` or as its own process.

set -e -v

# python deps that are difficult to install with setuptools:
pip3 install -U numpy # gippy has some kind of problem otherwise
# see setup.py for why this is done here:
c_url=https://github.com/ubarsc
pip3 install -U "${c_url}/rios/archive/rios-1.4.3.zip#egg=rios-1.4.3"
pip3 install -U "${c_url}/python-fmask/archive/python-fmask-0.5.0.zip#egg=python-fmask-0.5.0"
