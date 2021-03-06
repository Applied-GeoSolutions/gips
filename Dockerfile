# syntax = docker/dockerfile:1.0-experimental
# Builds basic gips docker image; used as a foundation or basis.

FROM ubuntu:18.04


ARG GIPPY_REF=1.0.5
# for develop mode using your own external gippy
# pass --build-arg GIPPY_INSTALL_URL="--src=/ -e git+https://github.com/daganinc/gippy.git@${GIPPY_REF}#egg=gippy"
ARG GIPPY_INSTALL_URL="https://github.com/daganinc/gippy/archive/${GIPPY_REF}.tar.gz#egg=gippy"

COPY . /gips
WORKDIR /gips

### install dependencies
RUN cd /gips && ./install-sys-deps.sh && ./install-py-deps.sh

### install gippy & its dependencies suitably for developing gippy concurrently if needed
RUN apt-get install -y swig git ssh
### RUN pip3 install $GIPPY_INSTALL_URL
# at least one causes a version conflict later due to the python3-cryptography ubuntu pkg:
RUN apt-get remove -y --auto-remove git ssh

### install gips proper
RUN cd /gips && pip3 install -e . && \
    gips_config env --repos /archive --email nobody@example.com

### cleanup
RUN apt-get -y autoremove \
    && apt-get -y autoclean

ARG SENTINEL1

RUN if [ "$SENTINEL1" = "YES" ] ; then echo 'BUILDING SENTINEL1' \
    && mkdir /snap \
    && wget -nd -P /snap http://step.esa.int/downloads/6.0/installers/esa-snap_sentinel_unix_6_0.sh \
    && chmod +x /snap/esa-snap_sentinel_unix_6_0.sh \
    && /snap/esa-snap_sentinel_unix_6_0.sh -q -c \
    && ln -s /usr/local/snap/bin/gpt /usr/bin/gpt \
    && /usr/local/snap/bin/snap --nosplash --nogui --modules --update-all \
    && sed -i -e 's/-Xmx1G/-Xmx16G/g' /usr/local/snap/bin/gpt.vmoptions \
    && rm -rf /snap; fi
