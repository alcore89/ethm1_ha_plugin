"""Config flow for SATEL ETHM-1 Legacy."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_INTEGRATION_KEY,
    CONF_MOTION_HOLD_SECONDS,
    CONF_MOTION_HOLD_ZONES,
    CONF_SCAN_INTERVAL,
    CONF_USER_CODE,
    DEFAULT_MOTION_HOLD_SECONDS,
    DEFAULT_MOTION_HOLD_ZONES,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .protocol import SatelClient, SatelError
from .utils import parse_zone_spec

_LOGGER = logging.getLogger(__name__)


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            ),
            vol.Required(CONF_USER_CODE, default=defaults.get(CONF_USER_CODE, "")): TextSelector(
                TextSelectorConfig(
                    type=TextSelectorType.PASSWORD,
                    autocomplete="current-password",
                )
            ),
            vol.Optional(
                CONF_INTEGRATION_KEY,
                default=defaults.get(CONF_INTEGRATION_KEY, ""),
            ): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="off")
            ),
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
            vol.Required(
                CONF_MOTION_HOLD_SECONDS,
                default=defaults.get(
                    CONF_MOTION_HOLD_SECONDS, DEFAULT_MOTION_HOLD_SECONDS
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=600)),
            vol.Optional(
                CONF_MOTION_HOLD_ZONES,
                default=defaults.get(
                    CONF_MOTION_HOLD_ZONES, DEFAULT_MOTION_HOLD_ZONES
                ),
            ): str,
        }
    )


def _normalize(user_input: dict[str, Any]) -> dict[str, Any]:
    data = dict(user_input)
    data[CONF_HOST] = str(data[CONF_HOST]).strip()
    data[CONF_USER_CODE] = str(data[CONF_USER_CODE]).strip()
    data[CONF_INTEGRATION_KEY] = str(data.get(CONF_INTEGRATION_KEY, ""))
    data[CONF_MOTION_HOLD_ZONES] = str(
        data.get(CONF_MOTION_HOLD_ZONES, DEFAULT_MOTION_HOLD_ZONES)
    ).strip()
    return data


async def _validate(user_input: dict[str, Any]) -> str:
    code = str(user_input[CONF_USER_CODE]).strip()
    if not code.isdigit() or not 1 <= len(code) <= 16:
        raise ValueError("invalid_code")

    key = str(user_input.get(CONF_INTEGRATION_KEY, ""))
    try:
        key_bytes = key.encode("ascii")
    except UnicodeEncodeError as err:
        raise ValueError("invalid_key") from err
    if len(key_bytes) > 12:
        raise ValueError("invalid_key")

    try:
        parse_zone_spec(str(user_input.get(CONF_MOTION_HOLD_ZONES, "")))
    except (ValueError, TypeError):
        raise ValueError("invalid_zones")

    client = SatelClient(
        host=user_input[CONF_HOST],
        port=user_input[CONF_PORT],
        user_code=code,
        integration_key=key,
    )
    try:
        panel = await client.get_panel_info()
    finally:
        await client.close()
    return panel.model


class SatelEthm1LegacyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def _handle_form(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
        defaults: dict[str, Any] | None = None,
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            data = _normalize(user_input)
            try:
                model = await _validate(data)
            except ValueError as err:
                if str(err) == "invalid_key":
                    errors[CONF_INTEGRATION_KEY] = "invalid_key"
                elif str(err) == "invalid_zones":
                    errors[CONF_MOTION_HOLD_ZONES] = "invalid_zones"
                else:
                    errors[CONF_USER_CODE] = "invalid_code"
            except (SatelError, OSError, asyncio.TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception during SATEL config flow")
                errors["base"] = "unknown"
            else:
                if step_id == "reconfigure":
                    return self.async_update_reload_and_abort(
                        self._get_reconfigure_entry(),
                        data_updates=data,
                    )

                self._async_abort_entries_match(
                    {CONF_HOST: data[CONF_HOST], CONF_PORT: data[CONF_PORT]}
                )
                return self.async_create_entry(title=model, data=data)
            defaults = data

        return self.async_show_form(
            step_id=step_id,
            data_schema=_schema(defaults),
            errors=errors,
        )

    async def async_step_user(self, user_input=None) -> FlowResult:
        return await self._handle_form("user", user_input)

    async def async_step_reconfigure(self, user_input=None) -> FlowResult:
        entry = self._get_reconfigure_entry()
        return await self._handle_form("reconfigure", user_input, dict(entry.data))
