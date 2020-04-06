# syntax = docker/dockerfile:1.0-experimental
# Builds basic gips docker image; used as a foundation or basis.

FROM ubuntu:18.04

ARG GIPPY_INSTALL_URL="git+ssh://git@gitlab.com/daganinc/gippy.git@1.0.4#egg=gippy"

COPY . /gips
WORKDIR /gips

RUN cd /gips && ./install-sys-deps.sh && ./install-py-deps.sh

### install gippy & its dependencies suitably for developing gippy concurrently if needed
RUN apt-get install -y swig
RUN --mount=type=ssh ssh -T -oStrictHostKeyChecking=no git@gitlab.com && \
                     pip3 install -e $GIPPY_INSTALL_URL --src /
RUN pip3 install -r /gippy/requirements-dev.txt

RUN cd /gips && python3 setup.py develop && \
    gips_config env --repos /archive --email nobody@example.com

RUN apt-get -y autoremove \
    && apt-get -y autoclean
