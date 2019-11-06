This is a quick and dirty guide to building gips containers, mostly for
development purposes.

`docker/gips-test-full.docker` is the fullest option for dev purposes.  It
contains sixs and can pass the tests that require it.  Build it with:

```
docker build --no-cache -t gips-base -f Dockerfile .
docker build --no-cache -t gips-ci -f docker/gips-ci.docker .  # CF .gitlab-ci.yml
docker build --no-cache -t gips-test-full -f docker/gips-test-full.docker .
```

Running the edit-test-debug cycle
=================================
Use an alias to make life easier (a function would be better probably).  this
lets you edit code on the host machine using a modern IDE.  You can trash the
container after every run, thus ensuring a clean slate:

```
# handy alias
alias r='docker run --rm -i -v /home/tolson/src/gips/:/gips -v /home/tolson/src/gips-sys-test-assets:/artifact-store'

# unit & integration tests:
time r gips-test-full pytest -r es -s -vv --setup-repo -k 'unit or int'

# system tests for landsat, say:
time r gips-test-full pytest -r es --slow --sys -s -vv --setup-repo --stepwise -k 'sys and landsat'
```

Interactive Shells
------------------
Usually only needed for debugging using `pdb`; these seem to need `-t` for
allocating a TTY:

```
alias rt='docker run --rm -it -v /home/tolson/src/gips/:/gips -v /home/tolson/src/gips-sys-test-assets:/artifact-store'
rt gips-test-full bash
root@a9e700cd3838:/gips# gips_inventory landsat
```
