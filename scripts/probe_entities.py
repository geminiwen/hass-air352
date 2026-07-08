#!/usr/bin/env python3
"""Probe 352 account data and show which HA entities would be created.

Run from the repository root:

    python3 scripts/probe_entities.py

The script asks for credentials interactively, then performs the same remote
steps used by the integration until the first property refresh. It does not
import Home Assistant, so it can run in a plain Python environment with aiohttp.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import importlib
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

DEVICE_TYPE_AIR = "AirPurifier"
DEVICE_TYPE_HUMIDIFIER = "Humidifier"
DEVICE_TYPE_PURIFIER = "WaterPurifier"
CATEGORY_KEY_ALIASES = {
    DEVICE_TYPE_AIR.lower(): DEVICE_TYPE_AIR,
    DEVICE_TYPE_HUMIDIFIER.lower(): DEVICE_TYPE_HUMIDIFIER,
    DEVICE_TYPE_PURIFIER.lower(): DEVICE_TYPE_PURIFIER,
}


@dataclass(frozen=True)
class EntityRule:
    platform: str
    key: str
    name: str
    category_keys: tuple[str, ...]


SENSOR_RULES = (
    EntityRule("sensor", "PM25", "PM2.5", (DEVICE_TYPE_AIR, DEVICE_TYPE_HUMIDIFIER)),
    EntityRule("sensor", "TVOC", "TVOC", (DEVICE_TYPE_AIR,)),
    EntityRule("sensor", "HCHO", "Formaldehyde", (DEVICE_TYPE_AIR,)),
    EntityRule("sensor", "CO2", "CO2", (DEVICE_TYPE_AIR,)),
    EntityRule("sensor", "CurrentTemperature", "Temperature", (DEVICE_TYPE_AIR, DEVICE_TYPE_HUMIDIFIER)),
    EntityRule("sensor", "RelativeHumidity", "Humidity", (DEVICE_TYPE_AIR, DEVICE_TYPE_HUMIDIFIER)),
    EntityRule(
        "sensor",
        "FilterLifeTimePercent_1",
        "Filter 1 Life",
        (DEVICE_TYPE_AIR, DEVICE_TYPE_PURIFIER, DEVICE_TYPE_HUMIDIFIER),
    ),
    EntityRule(
        "sensor",
        "FilterLifeTimePercent_2",
        "Filter 2 Life",
        (DEVICE_TYPE_AIR, DEVICE_TYPE_PURIFIER),
    ),
    EntityRule("sensor", "FilterLifeTimePercent_3", "Filter 3 Life", (DEVICE_TYPE_AIR,)),
    EntityRule("sensor", "FinishedWaterTDS", "Output TDS", (DEVICE_TYPE_PURIFIER,)),
    EntityRule("sensor", "RawWaterTDS", "Input TDS", (DEVICE_TYPE_PURIFIER,)),
    EntityRule("sensor", "WaterTemperature", "Water Temperature", (DEVICE_TYPE_PURIFIER,)),
    EntityRule("sensor", "TotalPureWater", "Total Pure Water", (DEVICE_TYPE_PURIFIER,)),
    EntityRule(
        "sensor",
        "WiFI_RSSI",
        "WiFi Signal",
        (DEVICE_TYPE_AIR, DEVICE_TYPE_PURIFIER, DEVICE_TYPE_HUMIDIFIER),
    ),
)

SWITCH_RULES = (
    EntityRule("switch", "PowerSwitch", "Power", (DEVICE_TYPE_HUMIDIFIER,)),
    EntityRule(
        "switch",
        "ChildLockSwitch",
        "Child Lock",
        (DEVICE_TYPE_AIR, DEVICE_TYPE_HUMIDIFIER, DEVICE_TYPE_PURIFIER),
    ),
    EntityRule("switch", "ScreenSwitch", "Screen", (DEVICE_TYPE_AIR, DEVICE_TYPE_HUMIDIFIER)),
    EntityRule("switch", "IonsSwitch", "Ionizer", (DEVICE_TYPE_AIR,)),
    EntityRule("switch", "SmartModeSwitch", "Smart Mode", (DEVICE_TYPE_HUMIDIFIER,)),
)

ALL_RULES = SENSOR_RULES + SWITCH_RULES
SUPPORTED_CATEGORIES = {DEVICE_TYPE_AIR, DEVICE_TYPE_HUMIDIFIER, DEVICE_TYPE_PURIFIER}


def load_api_client_class() -> type:
    """Load Air352ApiClient without executing the HA integration __init__.py."""
    custom_components_path = REPO_ROOT / "custom_components"
    air352_path = custom_components_path / "air352"

    if "custom_components" not in sys.modules:
        custom_components_pkg = types.ModuleType("custom_components")
        custom_components_pkg.__path__ = [str(custom_components_path)]
        sys.modules["custom_components"] = custom_components_pkg

    if "custom_components.air352" not in sys.modules:
        air352_pkg = types.ModuleType("custom_components.air352")
        air352_pkg.__path__ = [str(air352_path)]
        sys.modules["custom_components.air352"] = air352_pkg

    return importlib.import_module("custom_components.air352.api").Air352ApiClient


def normalize_device_category(category_key: str | None) -> str:
    if not category_key:
        return ""
    category = str(category_key)
    return CATEGORY_KEY_ALIASES.get(category.lower(), category)


def prop_value(prop: Any) -> Any:
    if isinstance(prop, dict) and "value" in prop:
        return prop["value"]
    return prop


def summarize_device(device: dict[str, Any]) -> dict[str, Any]:
    keys = ("iotId", "productName", "productModel", "categoryKey", "nickName", "status")
    return {key: device.get(key) for key in keys if key in device}


def build_entities(device: dict[str, Any], props: dict[str, Any]) -> list[dict[str, Any]]:
    iot_id = device["iotId"]
    category = normalize_device_category(device.get("categoryKey"))
    entities: list[dict[str, Any]] = []

    if category == DEVICE_TYPE_AIR and "PowerSwitch" in props:
        entities.append(
            {
                "platform": "fan",
                "unique_id": f"{iot_id}_fan",
                "name": "Air Purifier",
                "key": "PowerSwitch",
                "value": prop_value(props["PowerSwitch"]),
            }
        )

    for rule in ALL_RULES:
        if category in rule.category_keys and rule.key in props:
            entities.append(
                {
                    "platform": rule.platform,
                    "unique_id": f"{iot_id}_{rule.key}",
                    "name": rule.name,
                    "key": rule.key,
                    "value": prop_value(props[rule.key]),
                }
            )

    return entities


def print_section(title: str) -> None:
    print()
    print(f"== {title} ==")


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def print_probe_result(
    devices: list[dict[str, Any]],
    device_infos: dict[str, dict[str, Any]],
    properties: dict[str, dict[str, Any]],
    show_raw: bool,
) -> None:
    print_section("Devices")
    print(f"Found {len(devices)} device(s).")
    for index, device in enumerate(devices, start=1):
        print(f"[{index}]")
        print_json(summarize_device(device))

    all_entities: list[dict[str, Any]] = []

    for device in devices:
        iot_id = device["iotId"]
        raw_category = device.get("categoryKey", "")
        category = normalize_device_category(raw_category)
        props = properties.get(iot_id, {})
        entities = build_entities(device, props)
        all_entities.extend(entities)

        print_section(f"Device {iot_id}")
        print(f"categoryKey: {raw_category or '<missing>'}")
        if category != raw_category:
            print(f"normalized categoryKey: {category}")
        print(f"productName: {device.get('productName') or device.get('nickName') or '<missing>'}")

        info = device_infos.get(iot_id)
        if info:
            print("device_info:")
            print_json(info)

        prop_keys = sorted(props.keys())
        print(f"property key count: {len(prop_keys)}")
        print("property keys:")
        print(", ".join(prop_keys) if prop_keys else "<none>")

        if show_raw:
            print("raw properties:")
            print_json(props)

        print("matched entities:")
        if entities:
            for entity in entities:
                print(
                    "- {platform}.{name} unique_id={unique_id} key={key} value={value}".format(
                        **entity
                    )
                )
        else:
            print("<none>")
            if category not in SUPPORTED_CATEGORIES:
                print(f"reason: unsupported categoryKey {category!r}")
            elif not props:
                print("reason: /thing/properties/get returned no properties for this device")
            else:
                print("reason: category is supported, but none of the current entity keys matched")

    print_section("Summary")
    entity_word = "entity" if len(all_entities) == 1 else "entities"
    print(f"Would create {len(all_entities)} {entity_word}.")
    if all_entities:
        by_platform: dict[str, int] = {}
        for entity in all_entities:
            by_platform[entity["platform"]] = by_platform.get(entity["platform"], 0) + 1
        print_json(by_platform)


async def async_main() -> int:
    parser = argparse.ArgumentParser(
        description="Log in to 352/Ali IoT and print the entities this integration would create."
    )
    parser.add_argument("--username", help="352Life account. If omitted, prompt interactively.")
    parser.add_argument("--password", help="352Life password. If omitted, prompt securely.")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print full raw device properties, not only property keys and matched entities.",
    )
    args = parser.parse_args()

    try:
        import aiohttp

        Air352ApiClient = load_api_client_class()
    except ModuleNotFoundError as err:
        missing = err.name or "required module"
        print(
            f"Missing Python module: {missing}. Run this script in the Home Assistant "
            "Python environment, or install aiohttp in your local environment.",
            file=sys.stderr,
        )
        return 4

    username = args.username or input("352Life username: ").strip()
    password = args.password or getpass.getpass("352Life password: ")

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        api = Air352ApiClient(session, username, password)

        print_section("Login")
        print("Authenticating...")
        await api.authenticate()
        print("Authentication OK.")

        print_section("Device List")
        devices = await api.get_device_list()
        print(f"Device list OK: {len(devices)} device(s).")

        device_infos: dict[str, dict[str, Any]] = {}
        properties: dict[str, dict[str, Any]] = {}

        for device in devices:
            iot_id = device["iotId"]
            try:
                device_infos[iot_id] = await api.get_device_info(iot_id)
            except Exception as err:  # noqa: BLE001 - probe script should keep going.
                print(f"Warning: get_device_info failed for {iot_id}: {err}")

            try:
                properties[iot_id] = await api.get_device_properties(iot_id)
            except Exception as err:  # noqa: BLE001 - show partial results for diagnosis.
                print(f"Warning: get_device_properties failed for {iot_id}: {err}")
                properties[iot_id] = {}

        print_probe_result(devices, device_infos, properties, args.raw)
        return 0


def main() -> int:
    try:
        return asyncio.run(async_main())
    except Exception as err:
        err_types = {cls.__name__ for cls in type(err).mro()}
        if "Air352AuthError" in err_types:
            print(f"Auth failed: {err}", file=sys.stderr)
            return 2
        if err_types & {
            "Air352ConnectionError",
            "Air352ApiError",
            "ClientError",
            "TimeoutError",
        }:
            print(f"Request failed: {err}", file=sys.stderr)
            return 3
        raise
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
