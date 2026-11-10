"""Data coordinator for SATEL ETHM-1 Legacy."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .protocol import SatelClient, SatelError, SatelStatus

_LOGGER = logging.getLogger(__name__)


class SatelCoordinator(DataUpdateCoordinator[SatelStatus]):
    """Poll the panel once for all entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SatelClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=scan_interval),
            always_update=False,
        )
        self.client = client

    async def _async_update_data(self) -> SatelStatus:
        try:
            return await self.client.read_status()
        except SatelError as err:
            await self.client.close()
            raise UpdateFailed(f"SATEL communication failed: {err}") from err
        except (OSError, TimeoutError) as err:
            await self.client.close()
            raise UpdateFailed(f"SATEL transport failed: {err}") from err
