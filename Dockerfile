# Builds basic gips docker image; used as a foundation or basis.

FROM ubuntu:18.04

COPY . /gips
WORKDIR /gips

RUN cd /gips && ./install-sys-deps.sh && ./install-py-deps.sh
RUN cd /gips && python3 setup.py develop && \
    gips_config env --repos /archive --email nobody@example.com

RUN apt-get -y autoremove \
    && apt-get -y autoclean
