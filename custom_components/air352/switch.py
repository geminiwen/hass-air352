from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    DEVICE_TYPE_AIR,
    DEVICE_TYPE_PURIFIER,
    DEVICE_TYPE_HUMIDIFIER,
    normalize_device_category,
)
from .coordinator import Air352Coordinator


@dataclass(frozen=True, kw_only=True)
class Air352SwitchDescription(SwitchEntityDescription):
    category_keys: tuple[str, ...] = ()


SWITCH_DESCRIPTIONS: list[Air352SwitchDescription] = [
    Air352SwitchDescription(
        key="PowerSwitch", name="Power",
        icon="mdi:power",
        category_keys=(DEVICE_TYPE_HUMIDIFIER,),
    ),
    Air352SwitchDescription(
        key="ChildLockSwitch", name="Child Lock",
        icon="mdi:lock",
        category_keys=(DEVICE_TYPE_AIR, DEVICE_TYPE_HUMIDIFIER, DEVICE_TYPE_PURIFIER),
    ),
    Air352SwitchDescription(
        key="ScreenSwitch", name="Screen",
        icon="mdi:monitor",
        category_keys=(DEVICE_TYPE_AIR, DEVICE_TYPE_HUMIDIFIER),
    ),
    Air352SwitchDescription(
        key="IonsSwitch", name="Ionizer",
        icon="mdi:atom",
        category_keys=(DEVICE_TYPE_AIR,),
    ),
    Air352SwitchDescription(
        key="SmartModeSwitch", name="Smart Mode",
        icon="mdi:brain",
        category_keys=(DEVICE_TYPE_HUMIDIFIER,),
    ),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: Air352Coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for device in coordinator.devices:
        category = normalize_device_category(device.get("categoryKey"))
        iot_id = device["iotId"]
        props = coordinator.data.get(iot_id, {}) if coordinator.data else {}
        for desc in SWITCH_DESCRIPTIONS:
            if category in desc.category_keys and desc.key in props:
                entities.append(Air352Switch(coordinator, device, desc))
    async_add_entities(entities)


class Air352Switch(CoordinatorEntity[Air352Coordinator], SwitchEntity):
    _attr_has_entity_name = True
    entity_description: Air352SwitchDescription

    def __init__(self, coordinator: Air352Coordinator, device: dict, description: Air352SwitchDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._iot_id = device["iotId"]
        self._attr_unique_id = f"{self._iot_id}_{description.key}"
        self._attr_translation_key = description.key.lower()
        info = coordinator.device_infos.get(self._iot_id, {})
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._iot_id)},
            "name": device.get("productName", "352 Device"),
            "manufacturer": MANUFACTURER,
            "model": info.get("firmwareVersion", device.get("productModel", "")),
        }

    @property
    def is_on(self) -> bool | None:
        props = self.coordinator.data.get(self._iot_id, {})
        prop = props.get(self.entity_description.key)
        if prop is None:
            return None
        val = prop.get("value") if isinstance(prop, dict) else prop
        return bool(val)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.api.set_device_properties(self._iot_id, {self.entity_description.key: 1})
        self._update_local_state(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.api.set_device_properties(self._iot_id, {self.entity_description.key: 0})
        self._update_local_state(0)

    def _update_local_state(self, value: int) -> None:
        props = self.coordinator.data.get(self._iot_id, {})
        prop = props.get(self.entity_description.key)
        if isinstance(prop, dict):
            prop["value"] = value
        else:
            props[self.entity_description.key] = {"value": value}
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._iot_id in (self.coordinator.data or {})
