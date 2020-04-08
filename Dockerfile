# syntax = docker/dockerfile:1.0-experimental
# Builds basic gips docker image; used as a foundation or basis.

FROM ubuntu:18.04

ARG GIPPY_INSTALL_URL="git+https://gitlab.com/daganinc/gippy.git@1.0.4#egg=gippy"

COPY . /gips
WORKDIR /gips

### install dependencies
RUN cd /gips && ./install-sys-deps.sh && ./install-py-deps.sh

### install gippy & its dependencies suitably for developing gippy concurrently if needed
RUN apt-get install -y swig git ssh
RUN pip3 install -e $GIPPY_INSTALL_URL --src /
# at least one causes a version conflict later due to the python3-cryptography ubuntu pkg:
RUN apt-get remove -y --auto-remove git ssh

### install gips proper
RUN cd /gips && python3 setup.py develop && \
    gips_config env --repos /archive --email nobody@example.com

### cleanup
RUN apt-get -y autoremove \
    && apt-get -y autoclean
