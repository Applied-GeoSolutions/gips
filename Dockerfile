FROM ubuntu:16.04

RUN echo "deb http://ppa.launchpad.net/ubuntugis/ppa/ubuntu xenial main" >> \
       /etc/apt/sources.list \
    && apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 314DF160 \
    && apt-get -y update \
    && apt-get install -y \
    python python-apt \
    python-pip \
    gfortran \
    libboost-system1.58.0 \
    libboost-log1.58.0 \
    libboost-all-dev \
    libfreetype6-dev \
    libgnutls-dev \
    libatlas-base-dev \
    libgdal-dev \
    libcurl4-gnutls-dev \
    gdal-bin \
    python-numpy \
    python-scipy \
    python-gdal \
    swig2.0 \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && pip install -U pip==9.0.3 setuptools wheel \
    && pip install https://github.com/Applied-GeoSolutions/gippy/archive/v0.3.11.tar.gz#egg=gippy

COPY . /gips

RUN cd /gips \
    && pip install -r dev_requirements.txt \
    && pip install --process-dependency-links -e . \
    && mv sixs /usr/local/bin/sixs \
    && chmod +x /usr/local/bin/sixs

RUN apt-get -y purge \
       gfortran \
       libboost-all-dev \
       libfreetype6-dev \
       libatlas-base-dev \
       libgdal-dev \
       swig2.0 \
    && apt-get -y autoremove \
    && apt-get -y autoclean

ARG UID
#ARG GID
RUN groupadd -g $UID gips \
    && mkdir /archive \
    && useradd -m -r -u $UID -g gips gips \
    && chown -R gips:gips /gips /archive

VOLUME /archive
VOLUME /gips
WORKDIR /gips
USER gips



#ARG UID
#ARG UNAME
#RUN groupadd -g $UID $UNAME \
#    && useradd -m -r -u $UID -g $UNAME $UNAME \
#    && chown -R $UNAME:$UNAME /gips /archive

#ARG GID
#ARG GNAME

#RUN groupadd -g $GID $GNAME \
#    && useradd -m -r -u $UID -g $GID $UNAME \
#    && chown -R $UNAME:$GNAME /gips /archive
#USER $UNAME

#RUN useradd -m -r -u $UID -g 20 $UNAME \
#    && chown -R $UNAME:staff /gips /archive

#USER $UNAME
