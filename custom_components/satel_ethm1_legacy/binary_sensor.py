"""Binary sensors for SATEL alarm zones."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import (
    CONF_MOTION_HOLD_SECONDS,
    CONF_MOTION_HOLD_ZONES,
    DEFAULT_MOTION_HOLD_SECONDS,
    DEFAULT_MOTION_HOLD_ZONES,
)
from .entity import SatelEntity
from .utils import parse_zone_spec


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up dynamically discovered SATEL zones."""
    runtime = entry.runtime_data
    hold_seconds = int(
        entry.data.get(CONF_MOTION_HOLD_SECONDS, DEFAULT_MOTION_HOLD_SECONDS)
    )
    hold_zones = parse_zone_spec(
        str(entry.data.get(CONF_MOTION_HOLD_ZONES, DEFAULT_MOTION_HOLD_ZONES))
    )

    async_add_entities(
        SatelZoneBinarySensor(
            runtime.coordinator,
            runtime.panel,
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
            zone,
            runtime.partitions,
            hold_seconds,
            zone.zone_id in hold_zones,
        )
        for zone in runtime.zones
    )


class SatelZoneBinarySensor(SatelEntity, BinarySensorEntity):
    """A configured INTEGRA zone."""

    def __init__(
        self,
        coordinator,
        panel,
        host,
        port,
        zone,
        partitions,
        hold_seconds: int,
        hold_enabled: bool,
    ) -> None:
        super().__init__(coordinator, panel, host, port)
        self.zone = zone
        self._partitions = {p.partition_id: p for p in partitions}
        self._attr_name = zone.name
        self._attr_unique_id = f"{host}:{port}:zone:{zone.zone_id}"

        # 0.1.3 motion hold is deliberately only a presentation layer.
        # Raw SATEL/coordinator state is untouched.
        self._hold_seconds = max(0, int(hold_seconds))
        self._hold_enabled = bool(hold_enabled and self._hold_seconds > 0)
        self._display_is_on = self._raw_is_on
        self._cancel_hold: Callable[[], None] | None = None

    @property
    def _raw_is_on(self) -> bool:
        """Return the current raw zone state from the coordinator."""
        return self.zone.zone_id in self.coordinator.data.violated_zones

    @property
    def is_on(self) -> bool:
        """Return the HA-visible state, optionally holding motion ON for a while."""
        if not self._hold_enabled:
            # This is exactly the 0.1.2 behavior for zones not configured for hold.
            return self._raw_is_on
        return self._display_is_on

    @callback
    def _cancel_pending_hold(self) -> None:
        """Cancel a pending delayed OFF transition."""
        if self._cancel_hold is not None:
            self._cancel_hold()
            self._cancel_hold = None

    @callback
    def _finish_motion_hold(self, _now: datetime) -> None:
        """Publish OFF after the configured quiet period, unless motion returned."""
        self._cancel_hold = None
        if self._raw_is_on:
            return
        if not self._display_is_on:
            return
        self._display_is_on = False
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle a raw SATEL update while preserving normal CoordinatorEntity behavior."""
        if not self._hold_enabled:
            super()._handle_coordinator_update()
            return

        raw_is_on = self._raw_is_on

        if raw_is_on:
            # Motion is always reported immediately.
            self._cancel_pending_hold()
            self._display_is_on = True
        elif self._display_is_on and self._cancel_hold is None:
            # Raw OFF is delayed. Further raw OFF polls do not create more timers.
            self._cancel_hold = async_call_later(
                self.hass,
                self._hold_seconds,
                self._finish_motion_hold,
            )

        # Keep availability and normal CoordinatorEntity semantics intact.
        # If the held state did not change, HA will not create a new logical
        # ON/OFF transition in the recorder.
        super()._handle_coordinator_update()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel pending timer when the entity is unloaded/reconfigured."""
        self._cancel_pending_hold()
        await super().async_will_remove_from_hass()

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose useful SATEL metadata."""
        partition = self._partitions.get(self.zone.partition_id)
        return {
            "zone_number": self.zone.zone_id,
            "zone_function": self.zone.function,
            "partition_number": self.zone.partition_id,
            "partition_name": partition.name if partition else None,
        }
