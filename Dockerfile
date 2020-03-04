# Builds basic gips docker image; used as a foundation or basis.

FROM ubuntu:18.04

COPY . /gips
WORKDIR /gips

RUN cd /gips && ./install-sys-deps.sh && ./install-py-deps.sh

# can't COPY ./local-gippy /gippy because the local path might not be there,
# and docker in its genius doesn't support any kind of conditionality in its
# build process.
# (if this gets much longer than 5 lines, make a separate script)
RUN if [ -e /gips/local-gippy ]; then \
    cp -r /gips/local-gippy /gippy && \
    apt-get install -y swig && \
    pip3 install /gippy --no-cache && \
    pip3 install -r /gippy/requirements-dev.txt; fi

RUN cd /gips && python3 setup.py develop && \
    gips_config env --repos /archive --email nobody@example.com

RUN apt-get -y autoremove \
    && apt-get -y autoclean
