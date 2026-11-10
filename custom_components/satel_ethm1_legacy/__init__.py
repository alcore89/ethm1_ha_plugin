"""SATEL ETHM-1 Legacy Home Assistant integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_INTEGRATION_KEY,
    CONF_SCAN_INTERVAL,
    CONF_USER_CODE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import SatelCoordinator
from .protocol import PanelInfo, PartitionInfo, SatelClient, ZoneInfo

PLATFORMS = [Platform.BINARY_SENSOR, Platform.ALARM_CONTROL_PANEL]


@dataclass
class SatelRuntimeData:
    """Runtime objects shared by integration platforms."""

    client: SatelClient
    coordinator: SatelCoordinator
    panel: PanelInfo
    zones: list[ZoneInfo]
    partitions: list[PartitionInfo]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SATEL ETHM-1 Legacy from a config entry."""
    client = SatelClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        user_code=entry.data[CONF_USER_CODE],
        integration_key=entry.data.get(CONF_INTEGRATION_KEY, ""),
    )

    try:
        panel = await client.get_panel_info()
        zones = await client.discover_zones()
        partitions = await client.discover_partitions_for_zones(zones)
    except Exception as err:
        await client.close()
        raise ConfigEntryNotReady(f"Cannot initialize SATEL ETHM-1: {err}") from err

    coordinator = SatelCoordinator(
        hass,
        entry,
        client,
        int(entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = SatelRuntimeData(
        client=client,
        coordinator=coordinator,
        panel=panel,
        zones=zones,
        partitions=partitions,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.close()
    return unloaded
