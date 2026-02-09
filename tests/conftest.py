"""Fixtures for SmartHub tests."""
from unittest.mock import patch, AsyncMock
from collections.abc import Generator

from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.smarthub.const import DOMAIN

import pytest

# @pytest.fixture(autouse=False)
# def auto_enable_custom_integrations(enable_custom_integrations):
#     """Enable custom integrations for testing."""
#     yield

# @pytest.fixture(autouse=True)
# def mock_recorder(hass):
#     """Mock the recorder component to avoid setup failures in tests."""
#     with patch("homeassistant.components.recorder.async_setup", return_value=True):
#         hass.data["recorder"] = True
#         hass.data["recorder_instance"] = True
#         yield

@pytest.fixture(autouse=True)
def base_recorder_fixture(recorder_mock, enable_custom_integrations):
    pass
