import pytest

from . import util
from .util import export_wrapper
from . import driver_setup

pytestmark = util.sys # skip everything unless --sys

# 'driver': {'prodnuct': [ (path, type, data...),...]...}
from .expected.std_export import expectations, mark_spec
from .expected.std_export_vrt import expectations as vrt_expectations

@pytest.mark.parametrize("driver, product",
                         util.params_from_expectations(expectations, mark_spec))
def t_export(export_wrapper, driver, product):
    """Test gips_project with warping."""
    record_mode, runner, working_dir = export_wrapper
    driver_setup.setup_repo_data(driver)
    args = ('gips_export',) + driver_setup.STD_ARGS[driver] + (
        '--res', '100', '100', '--outdir', working_dir, '--notld',
        '-p', product)
    outcome, actual = runner(*args)
    if not record_mode: # don't evaluate assertions when in record-mode
        assert (outcome.exit_code == 0
                and expectations[driver][product] == actual)


@pytest.mark.parametrize("driver, product",
                         util.params_from_expectations(expectations, mark_spec))
def t_export_vrt(export_wrapper, driver, product):
    record_mode, runner, working_dir = export_wrapper
    driver_setup.setup_repo_data(driver)
    args = ('gips_export',) + driver_setup.STD_ARGS[driver] + (
        '--res', '100', '100', '--outdir', working_dir, '--notld',
        '-p', product, '--vrt')
    outcome, actual = runner(*args)
    if not record_mode:
        assert (outcome.exit_code == 0
                and vrt_expectations[driver][product] == actual)
