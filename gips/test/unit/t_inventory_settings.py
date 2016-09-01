import sys

import pytest

import gips.utils
from gips.inventory.orm import settings

@pytest.yield_fixture
def override_settings(mocker):
    """Mocks settings with specified values and performs cleanup."""
    class FakeSettings(object):
        DATABASES = 'hello!'
        DEBUG = 'maybe'
        CUSTOM_SETTING = 3
        foo = 17
    s_mock = mocker.Mock()
    s_mock.return_value = FakeSettings
    saved_settings = sys.modules['gips.utils'].settings # for restoration after test
    sys.modules['gips.utils'].settings = s_mock
    # do the test run; have to reload to exercise the module code again after installing the mock
    reload(settings)
    yield
    # we twiddled a global object so clean that up
    sys.modules['gips.utils'].settings = saved_settings # restore normal settings function
    reload(settings) # load correct values
    del settings.CUSTOM_SETTING # delete test value


def t_inventory_settings_melding(override_settings):
    """Confirm GIPS settings make their way into Django ORM settings."""
    # test is already done by fixture, so check outcomes here
    s = settings
    assert (s.DATABASES, s.DEBUG, s.CUSTOM_SETTING) == ('hello!', 'maybe', 3)
    assert getattr(s, 'foo', None) == None  # it shouldn't load non-caps names