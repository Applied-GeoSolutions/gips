source credentials.sh

wget -O sixs ftp://${AGSFTPCREDS}@agsftp.ags.io/gipsftp/sixs
cp -f gips/settings_template_docker.py gips/settings.py
sed -i~ \
    -e "s/^EARTHDATA_USER.*/EARTHDATA_USER = \"${EARTHDATA_USER}\"/" \
    -e "s/^EARTHDATA_PASS.*/EARTHDATA_PASS = \"${EARTHDATA_PASS}\"/" \
    -e "s/^USGS_USER.*/USGS_USER = \"${USGS_USER}\"/" \
    -e "s/^USGS_PASS.*/USGS_PASS = \"${USGS_PASS}\"/" \
    -e "s/^ESA_USER.*/ESA_USER = \"${ESA_USER}\"/" \
    -e "s/^ESA_PASS.*/ESA_PASS = \"${ESA_PASS}\"/" \
    gips/settings.py

docker build -t gips --no-cache .

rm -rf ${ARCHIVEDIR}

docker run --rm --name gips -h gips -v ${ARCHIVEDIR}:/archive gips gips_config env

wget -O aod.composites.tgz ftp://${AGSFTPCREDS}@agsftp.ags.io/gipsftp/aod.composites.tar.gz
tar xfvz aod.composites.tgz -C ${ARCHIVEDIR}
rm aod.composites.tgz
rm sixs

docker run --rm --name gips -h gips -e GIPS_OVERRIDE_VERSION=0.8.2 -v ${ARCHIVEDIR}:/archive gips pytest -vv --setup-repo --slow --sys -s -k 'cdl and t_project'
