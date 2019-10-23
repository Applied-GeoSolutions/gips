[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.1289915.svg)](https://doi.org/10.5281/zenodo.1289915)

# GIPS

See http://gipit.github.io/gips/ for more documentation, but know it is not
current.

## Installation

gips is known to work only on Ubuntu 18.04.

You can build a docker container for gips, or install to a python virtual
environment, or install gips natively on your operating system.  You can also
use the install scripts piecemeal for your own needs.

### Native Installs

For native installs, use the install script, which will install ubuntu
packages, pip packages, and gips itself, then configure gips for use. Read this
short script before you run it:

```
$ sudo ./install.sh /path/to/gips/archive/dir nobody@example.com
```

Optionally, install [6S](http://6s.ltdri.org/) if you wish to use gips to
produce atmospherically-corrected products:

```
$ sudo ./install-sixs.sh
```

### Container Builds & Test Suite

See `docker/README.md`.  Also describes how to run the test suite.

### Python Virtual Environments & Piecemeal Installs

`install.sh` is a short script; its lines can be called separately if needed:

* `install-sys-deps.sh` uses apt to add the ubuntugis ppa, then install needed
    ubuntu packages, including `python3-pip` if no `pip3` is found in `$PATH`.
* `install-py-deps.sh`, which uses `pip3` to install a few python packages that
    are difficult to install in other ways.

You can also use them to install gips to a virtual environment:

```
$ sudo ./install-sys-deps.sh
$ sudo ./install-sixs.sh            # if needed, see above
$ sudo apt-get install python3-venv # if needed
$ python3 -m venv /path/to/gips-venv --system-site-packages
$ source /path/to/gips-venv/bin/activate
(gips-venv) $ ./install-py-deps.sh      # installs packages to your venv
(gips-venv) $ python3 setup.py develop  # installs packages to your venv, including gips
(gips-venv) $ gips_config env --repos /path/to/gips/archive/dir --email nobody@example.com
```

## Configuration

### GIPS Settings

`STATS_FORMAT` controls the way `gips_stats` formats its output, and is passed
in to python's `cvs.writer` as a dict of keyword options.

`GIPS_ORM` controls whether the ORM is activated, and whether gips will keep
an inventory of its content in the database configured in `DATABASES`.

### MODIS configuration note

If you wish to work with modis data, edit `~/.gips/settings.py` (if
that file doesn't exist, run `gips_config user` to create it) and
alter the `'modis'` entry in the `REPOS` dict by adding the following
to the end of that file:

```
REPOS['modis'].update(
    {
        'username': 'YOUR-EARTHDATA-USERNAME',
        'password': 'YOUR-EARTHDATA-PASSWORD', # Use os.environ to avoid saving
                                               # a password in a file.
    }
)
```

This username and password must match your Earthdata credentials; for more
information on obtaining credentials:

https://lpdaac.usgs.gov/about/news_archive/important_changes_lp_daac_data_access

For information on setting up automated testing, see `gips/test/README.md`.

### Landsat S3 Configuration Note

GIPS supports Landsat data access via AWS S3:

https://aws.amazon.com/public-datasets/landsat/

Most GIPS products are supported if you have API access to AWS:

https://aws.amazon.com/premiumsupport/knowledge-center/create-access-key/

Provide the special access tokens via environment variable:

```
export AWS_ACCESS_KEY_ID='your-id'
export AWS_SECRET_ACCESS_KEY='your-key'
```

Finally set `settings.py` to tell gips to fetch C1 assets from S3:

```
REPOS = {
    'landsat': {
        # . . .
        'source': 's3', # default is 'usgs'
    }
}
```

After this is done, `gips_inventory --fetch`, `gips_inventory`, and
`gips_process -p <product-list-here>` should work for S3 assets.

Contributor & Developer Guide
-----------------------------
We're grateful for any contributions to GIPS.  Guidelines:

* New code should be based on branch 'dev'; we use 'master' for official
  releases.
* Keep your diff to about 500 lines or less, breaking up your PRs if needed
  (use feature toggles etc to keep the dev branch clean).
* Style:  For new code, follow PEP8, but know that we're loose about some of
  its rules (such as two spaces before a comment).  Also, don't reformat files
  for compliance alone.
* Testing:  New code should be covered by unit tests.  Know also that we use
  an internal CI pipeline to run our suite of system tests and won't generally
  merge code that breaks them.  See `gips/test/README.md` for details.
* These rules aren't absolute; ask if you feel an exception is warranted.


## Authors and Contributors
The following have been authors or contributers to GIPS

    Bobby Braswell (Rob), rbraswell@appliedgeosolutions.com
    Ian Cooke, icooke@appliedgeosolutions.com
    Rick Emery, remery@appliedgeosolutions.com
    Justin Fisk, jfisk@appliedgeosolutions.com
    Matthew Hanson, matt.a.hanson@gmail.com
    Tom Olson, tolson@appliedgeosolutions.com
    Nate Rubin, nrubing@appliedgeosolutions.com

## License (GPL v3)

    Copyright (C) 2014-2018 Applied Geosolutions, oss@appliedgeosolutions.com

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

   You should have received a copy of the GNU General Public License
   along with this program. If not, see <http://www.gnu.org/licenses/>
