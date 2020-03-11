#!/usr/bin/env bash

# Installs system packages needed for gips; no need to run as root if a
# virtualenvironment is activated.  Run via `source` or as its own process.

set -e -v

# python deps that are difficult to install with setuptools:
pip3 install -U numpy # gippy has some kind of problem otherwise
# see setup.py for why this is done here:
c_url=git+https://github.com/ubarsc
pip3 install -U "${c_url}/rios@rios-1.4.6"
pip3 install -U "${c_url}/python-fmask@egg=pythonfmask-0.5.0"
