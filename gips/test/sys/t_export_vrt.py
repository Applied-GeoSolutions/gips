import pytest

from . import util
from .util import export_wrapper
from . import driver_setup

pytestmark = util.sys

from .expected.std_export_vrt import expectations, mark_spec


@pytest.mark.parametrize("driver, product", [('prism', 'ppt'), ('prism', 'vrtppt')])
def t_export_vrt(export_wrapper, driver, product):
    record_mode, runner, working_dir = export_wrapper
    driver_setup.setup_repo_data(driver)
    args = ('gips_export', 'prism', '-s', util.NH_4326_PATH, '-d', '1982-12-01,1982-12-03',
        '--res', '0.05', '0.05', '--outdir', working_dir, '--notld',
        '-p', product, '--vrt')
    outcome, actual = runner(*args)
    if not record_mode:
        assert (outcome.exit_code == 0
                and expectations[driver][product] == actual)
