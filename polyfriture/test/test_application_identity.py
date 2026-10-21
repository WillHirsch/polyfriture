"""Fork settings isolation, including settings snapshots used by closed docks."""

from pathlib import Path
from unittest.mock import Mock

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QSettings

from polyfriture import application
from polyfriture.application import application_settings, temporary_settings


def test_persistent_settings_use_fork_namespace_without_caller_metadata(monkeypatch):
    # Inspect the factory without constructing a native QSettings: even opening
    # an absent Windows profile can create an empty application registry key.
    store = Mock()
    factory = Mock(return_value=store)
    monkeypatch.setattr(application, "QSettings", factory)
    previous_organization = QCoreApplication.organizationName()
    previous_application = QCoreApplication.applicationName()
    try:
        QCoreApplication.setOrganizationName("Unrelated host")
        QCoreApplication.setApplicationName("Unrelated application")

        settings = application_settings()

        assert settings is store
        factory.assert_called_once_with("polyfriture", "polyfriture")
        store.setFallbacksEnabled.assert_called_once_with(False)
    finally:
        QCoreApplication.setOrganizationName(previous_organization)
        QCoreApplication.setApplicationName(previous_application)


def test_widget_settings_snapshots_are_independent_and_removed():
    first = temporary_settings()
    second = temporary_settings()
    first_path = Path(first.fileName())
    second_path = Path(second.fileName())
    try:
        first.setValue("type", 1)
        first.setValue("settings/range", 30)
        second.setValue("type", 2)
        second.setValue("settings/range", 60)
        first.sync()
        second.sync()

        assert first_path != second_path
        assert first_path.is_file() and second_path.is_file()
        assert first.value("type", type=int) == 1
        assert first.value("settings/range", type=int) == 30
        assert second.value("type", type=int) == 2
        assert second.value("settings/range", type=int) == 60
        assert first.format() == second.format() == QSettings.Format.IniFormat
        assert not first.fallbacksEnabled() and not second.fallbacksEnabled()
    finally:
        sip.delete(first)
        sip.delete(second)

    assert not first_path.exists()
    assert not second_path.exists()
