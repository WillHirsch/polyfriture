"""Version and upgrade Polyfriture settings snapshots without accessing stores.

Append transformations to UPGRADES; never reorder existing entries. Each step
receives a private snapshot, retains unknown keys and Qt values, and must be
idempotent. Imported Friture profiles and existing unversioned Polyfriture
profiles both start at version zero.
"""

import re
from typing import Any


class SettingsSchemaError(ValueError):
    """A settings schema version cannot safely be read by this release."""


def _v0_dock_names(value: Any) -> list[str] | None:
    # Freeze the v0 representations here: Qt can reload empty lists as None
    # and singleton INI lists as strings. Do not depend on a future owner format.
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return None
    if any(
        not isinstance(name, str)
        or not name
        or any(character in name for character in "/\\\0")
        or name in {"lastSettings", "dockNames", "widgetIdStack"}
        for name in value
    ):
        return None
    if len(set(value)) != len(value):
        return None
    return list(value)


def _v0_obsolete_level_widget(value: Any) -> bool:
    # Match the old integer setting parser: bools, floats and whitespace-padded
    # strings are not valid widget IDs. Every valid representation of ID 0 is.
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value == 0
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value):
        try:
            return int(value) == 0
        except ValueError:
            pass
    return False


def _upgrade_to_v1(values: dict[str, Any]) -> None:
    """Adopt the dock layout and normalize historical optional settings."""
    device_key = "AudioBackend/deviceName"
    if isinstance(values.get(device_key), str):
        # The old restore path uses button(0) when this optional setting is
        # missing, although the automatically assigned button IDs are -2/-3.
        values.setdefault("AudioBackend/duoInput", -2)
    if "Docks/widgetIdStack" in values and values["Docks/widgetIdStack"] is None:
        values["Docks/widgetIdStack"] = []

    names = _v0_dock_names(values.get("Docks/dockNames"))
    if names is None:
        return

    if "CentralWidget/type" in values:
        if "Docks/central/type" not in values:
            for key, value in list(values.items()):
                if key.startswith("CentralWidget/"):
                    values["Docks/central/" + key[len("CentralWidget/"):]] = value
            if "central" not in names:
                names.insert(0, "central")
            values["Docks/dockNames"] = names
        for key in list(values):
            if key == "CentralWidget" or key.startswith("CentralWidget/"):
                del values[key]

    if "Docks/dockNames" not in values:
        return
    retained_names = []
    for name in names:
        prefix = "Docks/" + name + "/"
        if _v0_obsolete_level_widget(values.get(prefix + "type", 0)):
            for key in list(values):
                if key == prefix[:-1] or key.startswith(prefix):
                    del values[key]
        else:
            retained_names.append(name)
    values["Docks/dockNames"] = retained_names


def _v1_delay_widget(value: Any) -> bool:
    # Freeze the retired ID's native and INI representations. Qt's old integer
    # conversion also accepted signed, zero-padded and whitespace-padded strings.
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value == 6
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        try:
            return int(value) == 6
        except ValueError:
            pass
    return False


def _upgrade_to_v2(values: dict[str, Any]) -> None:
    """Discard preferences and saved panels for removed playback/comparison features."""
    values.pop("AudioBackend/showPlayback", None)
    values.pop("AudioBackend/historyLength", None)

    # These cleanups do not depend on a readable active layout. Preserve unknown
    # stack entries for normal restoration to handle, rather than validating them.
    stack_key = "Docks/widgetIdStack"
    if stack_key in values:
        stack = values[stack_key]
        if stack is None:
            stack = []
        elif isinstance(stack, (int, str)) and not isinstance(stack, bool):
            stack = [stack]
        if isinstance(stack, list):
            values[stack_key] = [widget_id for widget_id in stack if not _v1_delay_widget(widget_id)]
    cache_prefix = "Docks/lastSettings/6"
    for key in list(values):
        if key == cache_prefix or key.startswith(cache_prefix + "/"):
            del values[key]

    # Version 1 retains the historical dock-name format interpreted by v0.
    names_key = "Docks/dockNames"
    if names_key not in values:
        return
    names = _v0_dock_names(values[names_key])
    if names is None:
        return
    retained_names = []
    for name in names:
        prefix = "Docks/" + name + "/"
        if _v1_delay_widget(values.get(prefix + "type")):
            for key in list(values):
                if key == prefix[:-1] or key.startswith(prefix):
                    del values[key]
        else:
            retained_names.append(name)
    values[names_key] = retained_names


def _v2_meter_widget(value: Any) -> bool:
    # Freeze the meter panel's initial integer/INI representations independently
    # of future widget registries and owner validation rules.
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value == 9
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        try:
            return int(value) == 9
        except ValueError:
            pass
    return False


def _upgrade_to_v3(values: dict[str, Any]) -> None:
    """Keep the former permanent meters as an ordinary removable panel."""
    names_key = "Docks/dockNames"
    if names_key not in values:
        # Fresh/default layouts include the meter panel without materializing
        # an otherwise absent layout in the persisted profile.
        return
    names = _v0_dock_names(values[names_key])
    if names is None or any(_v2_meter_widget(values.get(f"Docks/{name}/type")) for name in names):
        return
    suffix = 1
    name = "Meters"
    while name in names or any(key == f"Docks/{name}" or key.startswith(f"Docks/{name}/") for key in values):
        suffix += 1
        name = f"Meters {suffix}"
    values[names_key] = [name, *names]
    values[f"Docks/{name}/type"] = 9


UPGRADES = (_upgrade_to_v1, _upgrade_to_v2, _upgrade_to_v3)
CURRENT_VERSION = len(UPGRADES)


def parse_version(value: Any) -> int:
    """Read a native or INI version and reject unsupported schema versions."""
    # Native stores retain integers, while INI stores can return numeric strings.
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise SettingsSchemaError("Invalid Polyfriture settings schema version")
    try:
        version = int(value)
    except ValueError as error:
        raise SettingsSchemaError("Invalid Polyfriture settings schema version") from error
    if version < 0:
        raise SettingsSchemaError("Invalid Polyfriture settings schema version")
    if version > CURRENT_VERSION:
        raise SettingsSchemaError(
            "These preferences were saved by a newer Polyfriture version. "
            "Use that version to avoid overwriting them."
        )
    return version


def apply_upgrades(values: dict[str, Any], from_version: int) -> None:
    """Apply only pending upgrades to a private settings snapshot, in order."""
    version = parse_version(from_version)
    for upgrade in UPGRADES[version:]:
        upgrade(values)
