"""Shared entity helpers for SATEL ETHM-1 Legacy."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SatelCoordinator
from .protocol import PanelInfo


class SatelEntity(CoordinatorEntity[SatelCoordinator]):
    """Base SATEL entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SatelCoordinator,
        panel: PanelInfo,
        host: str,
        port: int,
    ) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{host}:{port}")},
            manufacturer="SATEL",
            model=panel.model,
            name=panel.model,
            sw_version=panel.version,
        )
