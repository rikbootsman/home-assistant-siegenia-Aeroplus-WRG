from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, DATA_CLIENT, DATA_COORDINATOR

def _combined(data: dict | None) -> dict:
    data = data or {}
    merged = {}
    for key in ("state", "params", "info"):
        v = data.get(key) or {}
        if isinstance(v, dict):
            merged.update(v)
    return merged

# Automode Switch
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    async_add_entities([SiegeniaAutoModeSwitch(hass, entry)], True)
    async_add_entities([SiegeniaDeviceActiveSwitch(hass, entry)], True)

class SiegeniaAutoModeSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        coord = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
        super().__init__(coord)
        self._client = hass.data[DOMAIN][entry.entry_id][DATA_CLIENT]
        self._entry = entry
        # Get system name from device info
        system_name = self._get_system_name()
        self._attr_name = f"{system_name} Auto Mode" if system_name else "Siegenia Auto Mode"
        self._attr_unique_id = f"{entry.entry_id}-automode"
        
    def _get_system_name(self) -> str | None:
        """Get the system name from device info."""
        data = self.coordinator.data or {}
        for part in ("state", "params", "info"):
            d = data.get(part) or {}
            if isinstance(d, dict):
                system_name = d.get("systemname") or d.get("device_name")
                if system_name:
                    return system_name
        return None

    def _d(self) -> dict:
        return _combined(self.coordinator.data)

    @property
    def is_on(self) -> bool:
        d = self._d()
        return bool(d.get("automode", d.get("auto_mode", False)))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._client.set_device_params({"automode": True, "auto_mode": True})
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._client.set_device_params({"automode": False, "auto_mode": False})
        await self.coordinator.async_request_refresh()

# Device active Switch
class SiegeniaDeviceActiveSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        coord = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
        super().__init__(coord)
        self._client = hass.data[DOMAIN][entry.entry_id][DATA_CLIENT]
        self._entry = entry
        # Get system name from device info
        system_name = self._get_system_name()
        self._attr_name = f"{system_name} Device active" if system_name else "Siegenia Device active"
        self._attr_unique_id = f"{entry.entry_id}-deviceactive"
        
    def _get_system_name(self) -> str | None:
        """Get the system name from device info."""
        data = self.coordinator.data or {}
        for part in ("state", "params", "info"):
            d = data.get(part) or {}
            if isinstance(d, dict):
                system_name = d.get("systemname") or d.get("device_name")
                if system_name:
                    return system_name
        return None

    def _d(self) -> dict:
        return _combined(self.coordinator.data)

    @property
    def is_on(self) -> bool:
        d = self._d()
        return bool(d.get("deviceactive", d.get("device_active", False)))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._client.set_device_params({"deviceactive": True, "device_active": True})
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._client.set_device_params({"deviceactive": False, "device_active": False})
        await self.coordinator.async_request_refresh()
