# Builds basic gips docker image; used as a foundation or basis.

FROM ubuntu:18.04

COPY . /gips
WORKDIR /gips

# TODO not clear if gfortran is needed when we're not compiling sixs after all
RUN cd /gips && ./install.sh /archive nobody@example.com

RUN apt-get -y autoremove \
    && apt-get -y autoclean

