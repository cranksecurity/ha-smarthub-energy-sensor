"""Test file for basic SmartHub integration functionality."""
import pytest
import functools
from unittest.mock import Mock, patch, AsyncMock
from collections.abc import Generator
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smarthub import async_setup_entry
from custom_components.smarthub.api import SmartHubAPI, SmartHubAPIError, SmartHubLocation, Aggregation
from custom_components.smarthub.const import DOMAIN, ENERGY_SENSOR_KEY, ELECTRIC_SERVICE, WATER_SERVICE
from custom_components.smarthub.sensor import SmartHubDataUpdateCoordinator
from homeassistant.components.recorder import Recorder, get_instance

from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
    get_metadata,
)

from datetime import timedelta
from homeassistant.util import dt as dt_util

@pytest.fixture(autouse=True)
def mock_smarthub_api(hass) -> Generator[AsyncMock]:
    """Mock the config entry ..."""

    api = SmartHubAPI(
        email="test@example.com",
        password="testpass",
        account_id="123456",
        timezone="UTC",
        mfa_totp="",
        host="test.smarthub.coop"
    )

    with patch(
        "custom_components.smarthub.api.SmartHubAPI", autospec=True
    ) as mock_api:

        mock_api.timezone="UTC"
        mock_api.parse_usage = api.parse_usage
        mock_api.get_service_locations.return_value = []
        mock_api.get_energy_data.return_value = {}
        yield mock_api



@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    return MockConfigEntry(
        version=1,
        domain=DOMAIN,
        title="SmartHub Test",
        data={
            "email": "test@example.com",
            "password": "testpass",
            "account_id": "123456",
            "location_id": "789012",
            "host": "test.smarthub.coop",
            "poll_interval": 60,
            "timezone": "UTC",
            "mfa_totp": "",
        },
        unique_id="test@example.com_test.smarthub.coop_123456",
    )


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = Mock(spec=HomeAssistant)
    hass.data = {}
    return hass

@pytest.fixture
def api_instance():
    """Create an API instance for testing."""
    return SmartHubAPI(
        email="test@example.com",
        password="testpass",
        account_id="123456",
        timezone="UTC",
        mfa_totp="",
        host="test.smarthub.coop"
    )

def test_parse_usage_valid_data(api_instance):
    """Test parsing valid usage data."""
    test_data = {
        "data": {
            "hasDaily": False,
            "WATER": [
                {
                    "type": "USAGE",
                    "series": [
                        {
                            "name": "YYYYYY",
                            "meterNumber": "YYYYYY",
                            "data": [
                              {
                                "x": 1739836800000,
                                "y": 3.2,
                                "enableDrilldown": True
                              },
                              {
                                "x": 1739923200000,
                                "y": 2.64,
                                "enableDrilldown": True
                              }
                            ]
                        }
                    ]
                }
            ]
        }
    }

    result = api_instance.parse_usage(test_data, Aggregation.HOURLY)

    assert "USAGE" in result[WATER_SERVICE]
    assert len(result[WATER_SERVICE]["USAGE"]) == 2
    assert result[WATER_SERVICE]["USAGE"][1]["consumption"] == 2.64

async def test_coordinator_first_run_water_electric(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_smarthub_api: AsyncMock,
) -> None:
    """Test the coordinator on its first run with no existing statistics."""
    mock_smarthub_api.get_service_locations.return_value = [
      SmartHubLocation(
        id="11111",
        service=ELECTRIC_SERVICE,
        description="test location",
        provider="test provider",
      ),
      SmartHubLocation(
        id="11112", # ID could be the same or unique from electric.
        service=WATER_SERVICE,
        description="test location",
        provider="test provider",
      )
    ]

    test_data = {
        "data": {
            "hasDaily": True,
            "ELECTRIC": [
                {
                    "type": "USAGE",
                    "series": [
                        {
                            "meters": [
                             {'meterNumber': '1ND81111111', 'seriesId': '1ND81111111', 'flowDirection': 'NET', 'isNetMeter': True}, # Non net meters have Forward flow as default
                            ],
                            "data": [
                                {"x": 1640995200000, "y": 100.5},
                                {"x": 1641081600000, "y": 150.2},
                            ]
                        }
                    ]
                }
            ],
            "WATER": [
                {
                    "type": "USAGE",
                    "series": [
                        {
                            "name": "YYYYYY",
                            "meterNumber": "YYYYYY",
                            "data": [
                              {
                                "x": 1739836800000,
                                "y": 3.2,
                                "enableDrilldown": True
                              },
                              {
                                "x": 1739923200000,
                                "y": 2.64,
                                "enableDrilldown": True
                              }
                            ]
                        }
                    ]
                }
            ]
        }
    }

    mock_smarthub_api.get_energy_data.return_value = mock_smarthub_api.parse_usage(test_data, Aggregation.HOURLY)

    coordinator = SmartHubDataUpdateCoordinator(hass, api=mock_smarthub_api, update_interval=timedelta(minutes=720), config_entry=mock_config_entry)

    entities = await coordinator._async_update_data()
    assert len(entities) == 1
    assert entities["11111"][ENERGY_SENSOR_KEY] == 150.2

    await async_wait_recording_done(hass)

    # Check stats for electric account '111111'
    stats = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        dt_util.utc_from_timestamp(0),
        None,
        {
            "smarthub:smarthub_energy_sensor_daily_123456_11111",
        },
        "hour",
        None,
        {"state", "sum"},
    )

    # Check stats for electric account '111111'
    water_stats = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        dt_util.utc_from_timestamp(0),
        None,
        {
            "smarthub:smarthub_water_sensor_monthly_123456_11112",
        },
        "hour",
        None,
        {"state", "sum"},
    )

    water_metadata = await get_instance(hass).async_add_executor_job(
      functools.partial(
        get_metadata,
        hass,
        statistic_ids={
            "smarthub:smarthub_water_sensor_monthly_123456_11112",
        },
      )
    )

    # The first hour's statistics summary is...
    assert stats["smarthub:smarthub_energy_sensor_daily_123456_11111"][0]["sum"] == 100.5
    assert water_stats["smarthub:smarthub_water_sensor_monthly_123456_11112"][0]["sum"] == 3.2 # must be lowercase

    assert water_metadata["smarthub:smarthub_water_sensor_monthly_123456_11112"][1]["name"] == 'test provider SmartHub WATER Monthly Usage - 123456 - test location'

async def test_coordinator_water_metadata(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_smarthub_api: AsyncMock,
) -> None:
    """Test the metadata on its first run with no existing statistics."""
    mock_smarthub_api.get_service_locations.return_value = [
      SmartHubLocation(
        id="11112", # ID could be the same or unique from electric.
        service=WATER_SERVICE,
        description="withDesc",
        provider="test provider",
      ),
      SmartHubLocation(
        id="11113", # ID could be the same or unique from electric.
        service=WATER_SERVICE,
        description="",
        provider="test provider",
      )
    ]

    test_data = {
        "data": {
            "WATER": [
                {
                    "type": "USAGE",
                    "series": [
                        {
                            "name": "YYYYYY",
                            "meterNumber": "YYYYYY",
                            "data": [
                              {
                                "x": 1739836800000,
                                "y": 3.2,
                                "enableDrilldown": True
                              },
                              {
                                "x": 1739923200000,
                                "y": 2.64,
                                "enableDrilldown": True
                              }
                            ]
                        }
                    ]
                }
            ]
        }
    }

    mock_smarthub_api.get_energy_data.return_value = mock_smarthub_api.parse_usage(test_data, Aggregation.HOURLY)

    coordinator = SmartHubDataUpdateCoordinator(hass, api=mock_smarthub_api, update_interval=timedelta(minutes=720), config_entry=mock_config_entry)

    entities = await coordinator._async_update_data()
    await async_wait_recording_done(hass)

    water_metadata = await get_instance(hass).async_add_executor_job(
      functools.partial(
        get_metadata,
        hass,
        statistic_ids={
            "smarthub:smarthub_water_sensor_monthly_123456_11112",
            "smarthub:smarthub_water_sensor_monthly_123456_11113",
        },
      )
    )

    assert water_metadata["smarthub:smarthub_water_sensor_monthly_123456_11112"][1]["name"] == 'test provider SmartHub WATER Monthly Usage - 123456 - withDesc'
    assert water_metadata["smarthub:smarthub_water_sensor_monthly_123456_11113"][1]["name"] == 'test provider SmartHub WATER Monthly Usage - 123456 - YYYYYY'



async def async_wait_recording_done(hass) -> None:
    """Async wait until recording is done."""
    await hass.async_block_till_done()
    get_instance(hass)._async_commit(dt_util.utcnow())
    await hass.async_block_till_done()
    await hass.async_add_executor_job(get_instance(hass).block_till_done)
    await hass.async_block_till_done()
