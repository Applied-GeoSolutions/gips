#!/usr/bin/env bash

# Installs system packages needed for gips; no need to run as root if a
# virtualenvironment is activated.  Run via `source` or as its own process.

set -e -v

# python deps that are difficult to install with setuptools:
pip3 install -U numpy # gippy has some kind of problem otherwise
# see setup.py for why this is done here:
c_url=https://github.com/ubarsc
pip3 install -U "${c_url}/rios/releases/download/rios-1.4.6/rios-1.4.6.zip#egg=rios-1.4.6"
pip3 install -U "${c_url}/python-fmask/releases/download/pythonfmask-0.5.2/python-fmask-0.5.2.tar.gz#egg=python-fmask-0.5.2"

pip3 install "git+https://github.com/jonas-eberle/esa_sentinel@v0.6.1#egg=sentinel_api"
