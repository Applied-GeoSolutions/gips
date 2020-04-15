import os
import shutil
import re
import importlib
import hashlib
import pprint

import pytest
import _pytest.mark.structures
import sh

from gips.inventory import orm # believed to be safe even though it's the code under test

def set_constants(config):
    """Use pytest config API to set globals pointing at needed file paths."""
    global TEST_DATA_DIR, DATA_REPO_ROOT, OUTPUT_DIR, NH_SHP_PATH, DURHAM_SHP_PATH, NE_SHP_PATH
    TEST_DATA_DIR  = str(config.rootdir.join('gips/test'))
    DATA_REPO_ROOT = config.getini('data-repo')
    OUTPUT_DIR     = config.getini('output-dir')
    NH_SHP_PATH    = os.path.join(TEST_DATA_DIR, 'NHseacoast.shp')
    NE_SHP_PATH    = os.path.join(TEST_DATA_DIR, 'NE.shp')
    DURHAM_SHP_PATH = os.path.join(TEST_DATA_DIR, 'durham.shp')

slow = pytest.mark.skipif('not config.getoption("slow")',
                          reason="--slow is required for this test")
acolite = pytest.mark.skipif('not config.getoption("acolite")',
                          reason="--acolite is required for this test")
sys = pytest.mark.skipif('not config.getoption("sys")', reason="--sys is required for this test")

lite = pytest.mark.lite


def extract_hashes(files):
    """Return a dict of file names and unique hashes of their content.

    `files` should be a dict in a result object from TestFileEnvironment.run().
    Directories' don't have hashes so use None instead."""
    return {k: getattr(v, 'hash', None) for k, v in files.items()}


def extract_timestamps(files):
    """Return a dict of file names and unique hashes of their content.

    `files` should be a dict in a result object from TestFileEnvironment.run().
    Directories' don't have hashes so use None instead."""
    return {k: getattr(v, 'hash', None) for k, v in files.items()}


class GipsProcResult(object):
    """Storage & equality comparison for a process's various outcomes.

    Standard output is handled specially for equality comparison; see __eq__.
    Can accept scripttest.ProcResult objects at initialization; see __init__.
    """
    attribs = ('exit_status', 'stdout', 'stderr', 'updated', 'deleted',
               'created', 'ignored',)  # 'timestamps')

    def __init__(self, proc_result=None, compare_stdout=None, compare_stderr=True, **kwargs):
        """Initialize the object using a ProcResult, explicit kwargs, or both.

        ProcResults' reports on files (created, deleted, updated) are saved as
        their names and hashes.  compare_stdout is an explicit way to request
        stdout be considered in __eq__; see below.  If it is not set, then
        self.stdout is examined.  If set by the user, it is assumed stdout
        comparison is desired.  compare_stderr is less magical:  Do the
        comparison unless the user specifies otherwise.
        """
        if proc_result is None:
            self.exit_status = 0
            self.stdout = None
            self.stderr = u''
            self.updated = {}
            self.deleted = {}
            self.created = {}
            # self.timestamps = {}
        else:
            # self.proc_result = proc_result # not sure if this is needed
            self.exit_status = proc_result.returncode
            self.stdout = proc_result.stdout
            self.stderr = proc_result.stderr
            self.updated = extract_hashes(proc_result.files_updated)
            self.deleted = extract_hashes(proc_result.files_deleted)
            self.created = extract_hashes(proc_result.files_created)
            # self.timestamps = dict()
            # for files in [proc_result.files_updated, proc_result.files_created]:
            #     self.timestamps.update(extract_timestamps(files))

        self.ignored = []  # list of filenames to ignore for comparison purposes

        # special keys are permitted if they begin with an underscore
        input_fields = set(k for k in kwargs.keys() if k[0] != '_')
        if not input_fields.issubset(set(self.attribs)):
            raise ValueError('Unknown attributes for GipsProcResult',
                             list(input_fields - set(self.attribs)))

        self.__dict__.update(kwargs)  # set user's desired values

        # guess the user's wishes regarding stdout comparison;
        # explicit request should override guesswork
        if compare_stdout is not None:
            self.compare_stdout = compare_stdout
        else:
            self.compare_stdout = self.stdout is not None
        # need a valid value to compare against either way
        # self.stdout = self.stdout or u''
        self.compare_stderr = compare_stderr

    def strip_ignored(self, d):
        """Return a copy of dict d but strip out items in self.ignored.

        If self.ignored = ['a', 'b'] then
        strip_ignored({'a': 1, 'b': 2, 'c': 2}) returns {'c': 2}.
        """
        return {k: v for k, v in d.items() if k not in self.ignored}

    def __eq__(self, other):
        """Equality means all attributes must match, except possibly stdout & stderr.

        Note that the type of other is not considered.
        """
        # only compare standard streams if both parties agree
        compare_stdout = self.compare_stdout and other.compare_stdout
        compare_stderr = self.compare_stderr and other.compare_stderr
        matches = (
            self.exit_status == other.exit_status,
            not compare_stdout or self.stdout == other.stdout,
            not compare_stderr or self.stderr == other.stderr,
            self.strip_ignored(self.updated) == self.strip_ignored(other.updated),
            self.strip_ignored(self.deleted) == self.strip_ignored(other.deleted),
            self.strip_ignored(self.created) == self.strip_ignored(other.created),
        )
        return all(matches)


def find_files(path):
    """Finds all non-directory files under the given path.

    A lot like running find(1) with no arguments.  Doesn't follow symlinks.
    Doesn't report errors (see os.walk docs for details).
    """
    found_files = [os.path.join(subpath, f)
            for subpath, _, filenames in os.walk(path) for f in filenames]
    return found_files

def generate_expectation(filename, base_path, e_type=None):
    """Return an expectation of the file's content, based on its file type.

    Pass in e_type to coerce the file into the given format, instead of
    letting the function choose for itself.  Absent files can't be coerced.

    Expectation formats:
        Symlink:  (filename, 'symlink', prefix_string, suffix_string)
            With symlinks one often can't use the whole link target
            because parts differ across environments (eg /home/usr/etc).
             So just use the bits before and after the base_path.
        Hash:  (filename, 'hash', 'sha256', <hex digest string>).
            Used as a fallback if nothing else matches the file type.
        Text-full:  (filename, 'text-full', list(<lines-in-file>))
        Raster:  (filename, 'raster', 'gdalinfo-stats', list(<lines-in-output>)
        Finally, if the file is absent:  (filename, 'absent')
    """
    # may want to try python-magic at some point:  https://github.com/ahupp/python-magic
    # but for now going by file extension seems to be sufficient.
    full_path = os.path.join(base_path, filename)

    # have to use lexists to cover for foolish abuse of symlinks by GDAL et al
    if not os.path.lexists(full_path):
        return (filename, 'absent')

    if e_type is None:
        e_type = ('symlink'   if os.path.islink(full_path) else
                  'text-full' if filename.endswith('.txt') else
                  'raster'    if filename.endswith('.tif') else 'hash')

    # symlinks
    if e_type == 'symlink':
        #                  have to remove this non-generic bit
        #                     vvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
        # HDF4_EOS:EOS_GRID:"/home/tolson/src/gips/data-root/modis/tiles/h12v04/2012337
        #   /MCD43A2.A2012337.h12v04.006.2016112013509.hdf":MOD_Grid_BRDF:Snow_BRDF_Albedo
        # when recording the path, do '<record_dir>/foo/bar/baz/file.tif'
        link_target = os.readlink(full_path)
        prefix, suffix = link_target.split(base_path)
        return (filename, e_type, prefix, suffix)

    # text files
    if e_type == 'text-full':
        size_threshold = 80 * 25 # about one terminal-screen
        f_size = os.stat(full_path).st_size
        if f_size <= size_threshold: # give up if there's too much text
            with open(full_path) as fo:
                lines = fo.readlines()
            return (filename, e_type, lines)
        print('{} ({} bytes) exceeds max supported size for text diffs'
              ' ({} bytes); defaulting to checksum'.format(
                    full_path, f_size, size_threshold))
        e_type = 'hash'

    # product TIFFs
    if e_type == 'raster':
        return (filename, e_type, 'gdalinfo-stats',
                generate_gdalinfo_stats_expectation(full_path))

    # use a hash as a fallback
    return (filename, e_type, 'sha256', generate_file_hash(full_path))

def generate_file_hash(filename, blocksize=2**20):
    # stolen from SO: https://stackoverflow.com/questions/1131220/get-md5-hash-of-big-files-in-python
    m = hashlib.sha256()
    with open(filename, 'rb' ) as f:
        while True:
            buf = f.read(blocksize)
            if not buf:
                break
            m.update(buf)
    return m.hexdigest()

def generate_gdalinfo_stats_expectation(filename):
    """Use `gdalinfo -stats <filename>` to generate an expectation object."""
    # Sooooo gdal generates these 'sidecar' files, ending in .aux.xml.
    # It can be told not to do that, but can't be told to ignore them
    # when they already exist.  Whether or not they exist changes the
    # output of gdalinfo -stats (reason unkonwn).  This can't be worked
    # around in any way, so we're obliged to delete them beforehand.
    sidecar = filename + '.aux.xml'
    os.path.exists(sidecar) and os.remove(sidecar) # RACE CONDITION LOL
    os.environ['GDAL_PAM_ENABLED'] = 'NO'
    # if needed switch to -json for more programmatic access to the data
    outcome = sh.gdalinfo('-stats', filename)
    # The output includes unpredictable file paths, so filter them out:
    lines = []
    in_files_block = False
    for l in outcome.stdout.decode().splitlines():
        # first detect whether we're in a 'Files:' block
        in_files_block = (l.startswith('Files: ')
                          or (in_files_block and l.startswith(' ')))
        if in_files_block:
            continue

        # stop at a certain decimal place for all decimal numbers
        significant_digits = 8
        sig_digits_re = r'(\.\d{' + str(significant_digits) + r'})\d+'
        lines.append(re.sub(sig_digits_re, r'\1', l))
    return lines

def params_from_expectations(expectations, mark_spec=None):
    """Generates a standard system test (driver, product) parameter list.

    Pass in a dict for mark_spec and any marks matching the given driver
    or (driver, product) will be applied accordingly.  These marks can be
    singular or in iterables."""
    mark_spec = {} if mark_spec is None else mark_spec
    params = []

    def get_mark_spec(i):
        msi = mark_spec.get(i, [])
        is_mark = isinstance(msi, _pytest.mark.structures.MarkDecorator)
        return [msi] if is_mark else list(msi) # handle case of multiple marks

    for driver, prod_expectations in expectations.items():
        dm = get_mark_spec(driver) # get driver-scoped marks
        for product in prod_expectations:
            dpm = get_mark_spec((driver, product)) # get product-scoped marks
            params.append(pytest.param(driver, product, marks=(dm + dpm)))
    return params

def record_path():
    path = pytest._config_saved_by_gips.getoption('--record')
    print("RECORD PATH:", path)
    return False if path in (None, '') else path

def sys_test_wrapper(request, path):
    """Provides for system testing by watching the specified directory.

    `request` is a pytest request object probably passed in to a fixture
    that is calling this function. Yields to let some process work, then
    reports on files created in the path during the wait.

    Presently depends on the module of the test having an expectations name
    that is a dict, or a dict of dicts, and the test getting a 'driver' param,
    and optionally a 'product' param.
    """
    rp = record_path() # does the user want record mode?  If so, save it where?
    driver = request.node.callspec.params['driver']
    product = request.node.callspec.params.get('product', None)
    # expected is an array of tuples:  (filename, type, data, data, data . . .)
    if product is None:
        expected = request.module.expectations[driver]
    else:
        expected = request.module.expectations[driver][product]
    expected_filenames = [e[0] for e in expected]

    if not rp:
        interlopers = [fn for fn in expected_filenames
                       if os.path.exists(os.path.join(path, fn))]
        if interlopers:
            raise IOError('Files in the way of the test: {}'.format(interlopers))

    initial_files = [] # getting around a scoping problem with python

    def wrapped_runner(cmd_string, *args):
        print("command line: `{} {}`".format(cmd_string, ' '.join(args)))
        if rp:
            initial_files.extend(find_files(path))
        # TODO can't pdb within a system test's subprocess; think settinng _in
        # might help, but neither `_in=sys.stdin` nor `_in='/dev/stdin'` works
        outcome = sh.Command(cmd_string)(
            *args, _err='/dev/stderr', _out='/dev/stdout')
        return outcome, [generate_expectation(e[0], path, e[1])
                         for e in expected]

    yield bool(rp), wrapped_runner

    if rp:
        final_files = find_files(path)
        created_files = set(final_files) - set(initial_files)
        # when recording the path, don't capture the directory of interest
        rel_cf = sorted(os.path.relpath(fp, path) for fp in created_files)

        # generate expectations but ignore index files
        cf_expectations = [generate_expectation(fn, path) for fn in rel_cf
                           if not fn.endswith('.index')]
        print("Recording {} outcome to {}.".format(product or driver, rp))
        with open(rp, 'a') as rfo:
            indent = ' '
            if product is None:
                comment = '\n{}# {}[{}] recording:'.format(
                    indent, request.function.__name__, driver)
                pf_lines = pprint.pformat(
                    (driver, cf_expectations)).splitlines()
            else:
                comment = '\n{}# {}[{}-{}] recording:'.format(
                    indent, request.function.__name__, driver, product)
                pf_lines = pprint.pformat(
                    (product, cf_expectations)).splitlines()
            print(comment, file=rfo)
            pf_str = '\n'.join(indent + l for l in pf_lines)
            print(pf_str, end='', file=rfo)
            print(',', file=rfo)

@pytest.yield_fixture
def repo_wrapper(request):
    """Fixture for tests that operate mostly on the data repo."""
    # This is how you wrap a generator in python:
    # https://stackoverflow.com/questions/11197186/
    for rv in sys_test_wrapper(request, DATA_REPO_ROOT):
        yield rv

@pytest.yield_fixture
def export_wrapper(request):
    """Fixture for tests that operate on an output directory.

    Makes a working directory that nests inside the OUTPUT_DIR."""
    driver = request.node.callspec.params['driver']
    product = request.node.callspec.params['product']
    working_dir = os.path.join(OUTPUT_DIR, '{}-{}-{}'.format(
        request.function.__name__, driver, product))
    os.makedirs(working_dir) # raises if leaf dir exists; this is desired
    # This is how you wrap a generator in python:
    # https://stackoverflow.com/questions/11197186/
    for rv in sys_test_wrapper(request, working_dir):
        yield rv + (working_dir,)

def load_expectation_module(name):
    """Use introspection to find known-good values for test assertions.

    Loads the model given by a part of `name`.  For instance, pass in
    'foo.bar.baz.t_qux' to locate and load the module `..expected.qux`.
    """
    _, mod_name = name.split('.')[-1].split('_', 1)
    relative_mod_name = '..expected.' + mod_name
    try:
        return importlib.import_module(relative_mod_name, __name__)
    except ImportError as ie:
        msg = "Eror importing expectations from {}.".format(relative_mod_name)
        raise ImportError(msg, ie.args)

@pytest.fixture
def expected(request):
    """Load the expectations for the running test.

    For example, assume a test named 't_process' in t_modis.py.
    expected() will then load a result object with values from
    expected.modis.t_process.
    """
    module = load_expectation_module(request.module.__name__)
    return GipsProcResult(**getattr(module, request.function.__name__))
