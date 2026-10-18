"""Fork settings isolation, including settings snapshots used by closed docks."""

from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QSettings

from friture_monitor.application import application_settings, temporary_settings


def test_persistent_settings_use_fork_namespace_without_caller_metadata():
    previous_organization = QCoreApplication.organizationName()
    previous_application = QCoreApplication.applicationName()
    try:
        QCoreApplication.setOrganizationName("Unrelated host")
        QCoreApplication.setApplicationName("Unrelated application")

        settings = application_settings()
        upstream = QSettings("Friture", "Friture")

        assert settings.organizationName() == "friture-monitor"
        assert settings.applicationName() == "friture-monitor"
        assert settings.fileName() != upstream.fileName()
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
        assert first.fileName() != application_settings().fileName()
    finally:
        sip.delete(first)
        sip.delete(second)

    assert not first_path.exists()
    assert not second_path.exists()
