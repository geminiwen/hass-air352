from __future__ import annotations

import math
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from .const import DOMAIN, MANUFACTURER, DEVICE_TYPE_AIR, normalize_device_category
from .coordinator import Air352Coordinator

SPEED_RANGE = (1, 6)

PRESET_MODE_AUTO = "auto"
PRESET_MODE_SLEEP = "sleep"
PRESET_MODE_MANUAL = "manual"

PRESET_MODES = [PRESET_MODE_AUTO, PRESET_MODE_SLEEP, PRESET_MODE_MANUAL]

WORKMODE_MAP = {
    PRESET_MODE_AUTO: 1,
    PRESET_MODE_MANUAL: 2,
    PRESET_MODE_SLEEP: 3,
}

WORKMODE_REVERSE = {v: k for k, v in WORKMODE_MAP.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: Air352Coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for device in coordinator.devices:
        category = normalize_device_category(device.get("categoryKey"))
        if category != DEVICE_TYPE_AIR:
            continue
        iot_id = device["iotId"]
        props = coordinator.data.get(iot_id, {}) if coordinator.data else {}
        if "PowerSwitch" in props:
            entities.append(Air352Fan(coordinator, device))
    async_add_entities(entities)


class Air352Fan(CoordinatorEntity[Air352Coordinator], FanEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "air_purifier"
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    _attr_preset_modes = PRESET_MODES
    _attr_speed_count = 6

    def __init__(self, coordinator: Air352Coordinator, device: dict) -> None:
        super().__init__(coordinator)
        self._iot_id = device["iotId"]
        self._attr_unique_id = f"{self._iot_id}_fan"
        info = coordinator.device_infos.get(self._iot_id, {})
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._iot_id)},
            "name": device.get("productName", "352 Device"),
            "manufacturer": MANUFACTURER,
            "model": info.get("firmwareVersion", device.get("productModel", "")),
        }

    def _get_prop_value(self, key: str) -> Any:
        props = self.coordinator.data.get(self._iot_id, {})
        prop = props.get(key)
        if prop is None:
            return None
        return prop.get("value") if isinstance(prop, dict) else prop

    def _get_speed_key(self) -> str | None:
        props = self.coordinator.data.get(self._iot_id, {})
        if "WindSpeed" in props:
            return "WindSpeed"
        if "windspeed" in props:
            return "windspeed"
        return None

    @property
    def is_on(self) -> bool | None:
        val = self._get_prop_value("PowerSwitch")
        if val is None:
            return None
        return bool(val)

    @property
    def percentage(self) -> int | None:
        speed_key = self._get_speed_key()
        if speed_key is None:
            return None
        val = self._get_prop_value(speed_key)
        if val is None or val == 0:
            return 0
        return ranged_value_to_percentage(SPEED_RANGE, val)

    @property
    def preset_mode(self) -> str | None:
        val = self._get_prop_value("WorkMode")
        if val is None:
            return None
        return WORKMODE_REVERSE.get(val)

    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any
    ) -> None:
        props: dict[str, int] = {"PowerSwitch": 1}
        if preset_mode is not None:
            wm = WORKMODE_MAP.get(preset_mode)
            if wm is not None:
                props["WorkMode"] = wm
        if percentage is not None:
            speed = math.ceil(percentage_to_ranged_value(SPEED_RANGE, percentage))
            speed_key = self._get_speed_key() or "WindSpeed"
            props[speed_key] = speed
            props.setdefault("WorkMode", WORKMODE_MAP[PRESET_MODE_MANUAL])
        await self.coordinator.api.set_device_properties(self._iot_id, props)
        self._update_local_state(props)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.api.set_device_properties(self._iot_id, {"PowerSwitch": 0})
        self._update_local_state({"PowerSwitch": 0})

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
            return
        speed = math.ceil(percentage_to_ranged_value(SPEED_RANGE, percentage))
        speed_key = self._get_speed_key() or "WindSpeed"
        props = {speed_key: speed, "WorkMode": WORKMODE_MAP[PRESET_MODE_MANUAL]}
        await self.coordinator.api.set_device_properties(self._iot_id, props)
        self._update_local_state(props)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        wm = WORKMODE_MAP.get(preset_mode)
        if wm is None:
            return
        await self.coordinator.api.set_device_properties(self._iot_id, {"WorkMode": wm})
        self._update_local_state({"WorkMode": wm})

    def _update_local_state(self, values: dict[str, int]) -> None:
        props = self.coordinator.data.get(self._iot_id, {})
        for key, value in values.items():
            prop = props.get(key)
            if isinstance(prop, dict):
                prop["value"] = value
            else:
                props[key] = {"value": value}
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._iot_id in (self.coordinator.data or {})
