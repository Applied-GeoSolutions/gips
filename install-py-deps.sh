#!/usr/bin/env bash

# Installs system packages needed for gips; no need to run as root if a
# virtualenvironment is activated.  Run via `source` or as its own process.

set -e -v

# python deps that are difficult to install with setuptools:
pip3 install -U numpy # gippy has some kind of problem otherwise
pip3 install Cython # This needs to be first because pip is dumb

