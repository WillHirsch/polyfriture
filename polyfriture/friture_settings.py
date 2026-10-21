"""Read Friture preferences for a one-time Polyfriture import.

The source is read without changing it. Unknown keys and Qt-specific values are
retained; Polyfriture metadata is excluded because it belongs to the destination.
Schema upgrades and durable destination writes belong to Polyfriture settings
initialization, rather than this source reader.
"""

import logging
import sys
from typing import Any

from PyQt6.QtCore import QSettings


logger = logging.getLogger(__name__)


def _polyfriture_metadata(key: str) -> bool:
    return key.split("/", 1)[0].casefold() == "polyfriture"


def _profile(values: dict[str, Any]) -> tuple[dict[str, Any], str]:
    # Value validation belongs to the ordinary settings owners after schema
    # upgrades, just as it does when loading an existing Polyfriture profile.
    values = {key: value for key, value in values.items() if not _polyfriture_metadata(key)}
    return values, "imported" if values else "absent"


def _read_qsettings(source: QSettings) -> tuple[dict[str, Any], str]:
    source.setFallbacksEnabled(False)
    values = {
        key: source.value(key)
        for key in source.allKeys()
        if not _polyfriture_metadata(key)
    }
    status = source.status()
    if status == QSettings.Status.FormatError:
        logger.warning("Ignoring malformed Friture settings at %s; using defaults", source.fileName())
        return {}, "invalid"
    if status != QSettings.Status.NoError:
        raise OSError(f"Cannot access settings at {source.fileName()}: {status.name}")
    return _profile(values)


def _read_windows() -> tuple[dict[str, Any], str]:
    from polyfriture.friture_settings_windows import read_native_settings, read_store_settings

    values = {
        key: value
        for key, value in read_native_settings().items()
        if not _polyfriture_metadata(key)
    }
    source = "the standalone Windows registry namespace"
    if not values:
        values = read_store_settings()
        source = "the Microsoft Store Friture settings hive"
    if values:
        logger.info("Importing Friture preferences from %s", source)
    return _profile(values)


def read_friture_settings(source: QSettings | None = None) -> tuple[dict[str, Any], str]:
    """Return a source snapshot and its import classification.

    An explicit store supports isolated tests and file-based callers. Otherwise,
    nonempty standalone Windows preferences take precedence over the Microsoft
    Store installation's private registry hive; the two profiles are never mixed.
    Other platforms use Friture's ordinary QSettings namespace.

    Undecodable or absent profiles return empty snapshots with ``invalid`` or
    ``absent`` classification. Nonempty profiles return ``imported`` for the
    initializer to record after a durable import. Access failures raise OSError,
    allowing initialization to stop and retry without recording an empty import.
    """
    if source is not None:
        return _read_qsettings(source)
    if sys.platform == "win32":
        return _read_windows()
    return _read_qsettings(QSettings("Friture", "Friture"))
