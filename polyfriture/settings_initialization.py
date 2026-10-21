"""Initialize Polyfriture settings with one-time Friture import and schema upgrades.

This module owns first-run decisions and durable writes. Friture source access
belongs to friture_settings; pure format upgrades belong to settings_schema.
Values are validated by their normal owners during settings restoration.
A journal is saved before application keys so interrupted
initialization can resume the same snapshot without rereading Friture.
"""

import logging
from typing import Any

from PyQt6.QtCore import QSettings

from polyfriture import settings_schema
from polyfriture.application import application_settings
from polyfriture.friture_settings import read_friture_settings


SCHEMA_VERSION_KEY = "Polyfriture/schemaVersion"
# Keep these persisted names so existing profiles and journals still load.
FRITURE_IMPORT_STATE_KEY = "Polyfriture/upstreamImport"
INITIALIZATION_JOURNAL_KEY = "Polyfriture/pendingMigration"
_FRITURE_IMPORT_STATES = {"imported", "absent", "invalid", "existing"}
logger = logging.getLogger(__name__)


class SettingsInitializationError(RuntimeError):
    """Preferences could not be initialized safely; do not start the UI."""


def _metadata_key(key: str) -> bool:
    return key.split("/", 1)[0].casefold() == "polyfriture"


def _snapshot(settings: QSettings) -> dict[str, Any]:
    return {key: settings.value(key) for key in settings.allKeys() if not _metadata_key(key)}


def _check_status(settings: QSettings) -> None:
    status = settings.status()
    if status != QSettings.Status.NoError:
        raise SettingsInitializationError(
            f"Cannot access settings at {settings.fileName()}: {status.name}"
        )


def _sync(settings: QSettings) -> None:
    try:
        settings.sync()
    except OSError as error:
        raise SettingsInitializationError(f"Cannot save settings at {settings.fileName()}") from error
    _check_status(settings)


def _schema_version(value: Any) -> int:
    try:
        return settings_schema.parse_version(value)
    except settings_schema.SettingsSchemaError as error:
        raise SettingsInitializationError(str(error)) from error


def _replay(settings: QSettings, journal: Any, version: int) -> None:
    if not isinstance(journal, dict):
        raise SettingsInitializationError("Invalid pending settings initialization")
    target_version = _schema_version(journal.get("schemaVersion"))
    values = journal.get("values")
    removed = journal.get("remove")
    # The journal's serialized field name is retained for existing retries.
    import_state = journal.get("upstreamImport")
    if (
        target_version < max(1, version)
        or not isinstance(values, dict)
        or any(not isinstance(key, str) or not key or _metadata_key(key) for key in values)
        or not isinstance(removed, list)
        or any(not isinstance(key, str) or not key or _metadata_key(key) for key in removed)
        or not isinstance(import_state, str)
        or import_state not in _FRITURE_IMPORT_STATES
    ):
        raise SettingsInitializationError("Invalid pending settings initialization")

    # Replay the prepared snapshot, rather than reading changed source settings.
    for key in removed:
        settings.remove(key)
    for key, value in values.items():
        settings.setValue(key, value)
    _sync(settings)

    # Publish completion only after every application key is durable, and retain
    # the journal until both completion markers have also been synchronized.
    settings.setValue(FRITURE_IMPORT_STATE_KEY, import_state)
    settings.setValue(SCHEMA_VERSION_KEY, target_version)
    _sync(settings)
    settings.remove(INITIALIZATION_JOURNAL_KEY)
    _sync(settings)


def initialize_settings(settings: QSettings | None = None, friture_source: QSettings | None = None) -> None:
    """Import Friture once into an empty store, then upgrade Polyfriture's schema.

    Existing Polyfriture preferences are adopted without importing Friture.
    Schema upgrades apply to both imported profiles and existing profiles.
    Optional stores support isolated tests and callers with an explicit source.
    """
    if settings is None:
        settings = application_settings()
    settings.setFallbacksEnabled(False)
    _sync(settings)
    version = _schema_version(settings.value(SCHEMA_VERSION_KEY, 0))

    if settings.contains(INITIALIZATION_JOURNAL_KEY):
        _replay(settings, settings.value(INITIALIZATION_JOURNAL_KEY), version)
        # Finish an older journal before applying any newer schema upgrades.
        initialize_settings(settings, friture_source)
        return

    import_state = settings.value(FRITURE_IMPORT_STATE_KEY)
    if import_state is not None and (
        not isinstance(import_state, str) or import_state not in _FRITURE_IMPORT_STATES
    ):
        raise SettingsInitializationError("Invalid Friture-import state in Polyfriture settings")
    if version == settings_schema.CURRENT_VERSION and import_state is not None:
        return

    original = _snapshot(settings)
    _check_status(settings)
    values = original.copy()
    if import_state is None:
        if original or version:
            import_state = "existing"
        else:
            try:
                values, import_state = read_friture_settings(friture_source)
            except OSError as error:
                raise SettingsInitializationError(f"Cannot read Friture preferences: {error}") from error

    try:
        settings_schema.apply_upgrades(values, version)
    except settings_schema.SettingsSchemaError as error:
        raise SettingsInitializationError(str(error)) from error

    journal = {
        "values": values,
        "remove": sorted(original.keys() - values.keys()),
        "schemaVersion": settings_schema.CURRENT_VERSION,
        "upstreamImport": import_state,
    }
    settings.setValue(INITIALIZATION_JOURNAL_KEY, journal)
    _sync(settings)
    _replay(settings, journal, version)
    logger.info("Settings initialized at schema %d (Friture import: %s)",
                settings_schema.CURRENT_VERSION, import_state)
