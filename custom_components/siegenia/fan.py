
from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, DATA_CLIENT, DATA_COORDINATOR
from .device import build_device_info

_LOGGER = logging.getLogger(__name__)

PERCENTAGE_FLAG = getattr(FanEntityFeature, "SET_PERCENTAGE", getattr(FanEntityFeature, "SET_SPEED", 0))
DEFAULT_MAX_M3H = 60


def _active_param(active: bool) -> dict[str, Any]:
    """Build the on/off parameter.

    getDeviceState reports the flag flat as "deviceactive", but setDeviceParams
    expects it nested below "devicestate". Sent flat, the device silently
    accepts the call and ignores it.
    """
    return {"devicestate": {"deviceactive": active}}

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    client = data[DATA_CLIENT]
    coordinator = data[DATA_COORDINATOR]
    async_add_entities([SiegeniaFanEntity(client, coordinator, entry)], True)


class SiegeniaFanEntity(CoordinatorEntity, FanEntity):
    _attr_has_entity_name = True

    def __init__(self, client, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._client = client
        self._entry = entry
        # Get system name from device info
        system_name = self._get_system_name()
        self._attr_name = f"{system_name} Fan" if system_name else "Siegenia Fan"
        self._attr_unique_id = f"{entry.entry_id}-fan"
        
    def _get_system_name(self) -> str | None:
        """Get the system name from device info."""
        data = self.coordinator.data or {}
        for part in ("state", "params", "info"):
            d = data.get(part) or {}
            if isinstance(d, dict):
                system_name = d.get("systemname") or d.get("devicename") or d.get("device_name")
                if system_name:
                    return system_name
        return None

    @property
    def device_info(self):
        return build_device_info(
            self.coordinator.data, self._entry.entry_id, self._entry.data.get("host")
        )

    def _combined(self) -> dict:
        data = self.coordinator.data or {}
        merged: dict[str, Any] = {}
        for part in ("state", "params", "info"):
            v = data.get(part) or {}
            if isinstance(v, dict):
                merged.update(v)
        return merged

    def _raw_max_m3h(self, d: dict) -> int:
        for k in ("maxfanpower", "max_fan_power"):
            if k in d:
                try:
                    val = int(d.get(k) or 0)
                    if val > 0:
                        return val
                except Exception:
                    continue
        return DEFAULT_MAX_M3H

    def _manual_cap_m3h(self, d: dict, raw_max: int) -> Optional[int]:
        for k in ("maxfanpowermanual", "manual_maxfanpower"):
            if k in d and d.get(k) is not None:
                try:
                    val = int(d.get(k))
                    if val <= 0:
                        continue
                    # Heuristic: <=100 => treat as percent cap; >100 => absolute m³/h
                    if val <= 100:
                        return max(1, int(round(raw_max * val / 100)))
                    return val
                except Exception:
                    continue
        return None

    def _effective_max_m3h(self, d: dict) -> int:
        raw_max = self._raw_max_m3h(d)
        cap = self._manual_cap_m3h(d, raw_max)
        if cap is not None:
            return min(raw_max, cap)
        return raw_max

    @property
    def is_on(self) -> bool:
        d = self._combined()
        # Siegenia reports the on/off state as "deviceactive"; the other keys are
        # kept as a fallback for device types that might not send it.
        for k in ("deviceactive", "power", "on", "enabled"):
            if k in d:
                return bool(d.get(k))
        try:
            p = int(d.get("fanpower", 0) or 0)  # percent
            return p > 0
        except Exception:
            return False

    @property
    def percentage(self) -> int | None:
        # The device keeps its last fanpower while switched off; Home Assistant
        # expects 0 for an off fan.
        if not self.is_on:
            return 0
        d = self._combined()
        try:
            p = int(d.get("fanpower", 0) or 0)  # Siegenia reports percent 0..100
        except Exception:
            p = 0
        return max(0, min(100, p))

    @property
    def supported_features(self) -> int:
        return PERCENTAGE_FLAG | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._combined()
        raw_max = self._raw_max_m3h(d)
        eff_max = self._effective_max_m3h(d)
        try:
            p = int(d.get("fanpower", 0) or 0)
        except Exception:
            p = 0
        airflow = round(eff_max * p / 100) if eff_max else None
        manual_cap_field = None
        for k in ("maxfanpowermanual", "manual_maxfanpower"):
            if k in d:
                manual_cap_field = d.get(k)
                break
        return {
            "fanmode": d.get("fanmode"),
            "fanpower_percent": p,
            "raw_maxfanpower_m3h": raw_max,
            "manual_cap_reported": manual_cap_field,
            "effective_maxfanpower_m3h": eff_max,
            "airflow_m3h": airflow,
            "systemname": d.get("systemname") or d.get("devicename") or d.get("device_name"),
        }

    async def async_set_percentage(self, percentage: int) -> None:
        target_pct = max(0, min(100, int(percentage or 0)))
        # 0 % means off in Home Assistant; the device rejects "fanpower": 0.
        if target_pct == 0:
            await self.async_turn_off()
            return
        params: dict[str, Any] = {
            **_active_param(True),
            "automode": False,
            "fanpower": target_pct,
        }
        await self._client.set_device_params(params)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        if percentage is None:
            percentage = kwargs.get("percentage")
        if percentage is not None:
            await self.async_set_percentage(percentage)
            return
        await self._client.set_device_params(_active_param(True))
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._client.set_device_params(_active_param(False))
        await self.coordinator.async_request_refresh()
