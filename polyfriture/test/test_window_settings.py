"""Window state and historical conversion recover malformed profiles safely."""

import logging
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QByteArray, QSettings

from polyfriture import analyzer


@pytest.fixture
def settings(tmp_path, monkeypatch):
    store = QSettings(str(tmp_path / "profile.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(analyzer, "application_settings", lambda: store)
    return store


def test_invalid_geometry_does_not_discard_valid_window_state(settings):
    settings.setValue("windowGeometry", "invalid")
    state = QByteArray(b"\0\xffwindow-state")
    settings.setValue("windowState", state)
    model = analyzer.WindowSettings()
    model.restore(settings)
    assert model.get("windowGeometry") == QByteArray()
    assert model.get("windowState") == state
    assert settings.value("windowGeometry") == "invalid"


def test_historical_conversion_leaves_malformed_layout_for_normal_recovery(settings):
    settings.setValue("Docks/dockNames", ["invalid/name"])
    settings.setValue("CentralWidget/type", 2)
    before = {key: settings.value(key) for key in settings.allKeys()}
    analyzer.Friture.migrateSettings(SimpleNamespace(logger=logging.getLogger(__name__)))
    assert {key: settings.value(key) for key in settings.allKeys()} == before


def test_historical_conversion_preserves_invalid_type_for_owner_recovery(settings):
    settings.setValue("Docks/dockNames", ["Bad type", "Old levels"])
    settings.setValue("Docks/Bad type/type", "broken")
    settings.setValue("Docks/Bad type/extension", "retained")
    settings.setValue("Docks/Old levels/type", 0)
    settings.setValue("CentralWidget/type", 2)
    analyzer.Friture.migrateSettings(SimpleNamespace(logger=logging.getLogger(__name__)))
    assert settings.value("Docks/dockNames") == ["central", "Bad type"]
    assert settings.value("Docks/Bad type/extension") == "retained"
    assert settings.value("Docks/central/type") == 2
    assert not settings.contains("CentralWidget/type")
