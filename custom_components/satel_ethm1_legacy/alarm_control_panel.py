"""Alarm control panels for SATEL partitions."""

from __future__ import annotations

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import SatelEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up alarm entities for dynamically discovered partitions."""
    runtime = entry.runtime_data
    async_add_entities(
        SatelPartitionAlarm(
            runtime.coordinator,
            runtime.panel,
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
            partition,
        )
        for partition in runtime.partitions
    )


class SatelPartitionAlarm(SatelEntity, AlarmControlPanelEntity):
    """Representation of one INTEGRA partition."""

    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_NIGHT
    )
    # The SATEL user code is stored in the config entry and used by the integration.
    # HA therefore does not need to request the code for every service call.
    _attr_code_arm_required = False

    def __init__(self, coordinator, panel, host, port, partition) -> None:
        super().__init__(coordinator, panel, host, port)
        self.partition = partition
        self._attr_name = partition.name
        self._attr_unique_id = f"{host}:{port}:partition:{partition.partition_id}"

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return partition state from the latest coordinator snapshot."""
        pid = self.partition.partition_id
        data = self.coordinator.data

        if pid in data.alarm_partitions:
            return AlarmControlPanelState.TRIGGERED
        if pid in data.exit_time_partitions:
            return AlarmControlPanelState.ARMING
        if pid in data.entry_time_partitions:
            return AlarmControlPanelState.DISARMING
        if pid in data.armed_partitions:
            if pid in data.mode3_partitions:
                return AlarmControlPanelState.ARMED_NIGHT
            if pid in data.mode2_partitions:
                return AlarmControlPanelState.ARMED_HOME
            return AlarmControlPanelState.ARMED_AWAY
        return AlarmControlPanelState.DISARMED

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        await self.coordinator.client.arm_away(self.partition.partition_id)
        await self.coordinator.async_request_refresh()

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        await self.coordinator.client.arm_home(self.partition.partition_id)
        await self.coordinator.async_request_refresh()

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        await self.coordinator.client.arm_night(self.partition.partition_id)
        await self.coordinator.async_request_refresh()

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        await self.coordinator.client.disarm(self.partition.partition_id)
        await self.coordinator.async_request_refresh()
