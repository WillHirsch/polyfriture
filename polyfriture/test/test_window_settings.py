"""Window restoration and versioned historical conversions tolerate bad fields."""

import pytest
from PyQt6.QtCore import QByteArray, QSettings

from polyfriture import analyzer
from polyfriture.settings_schema import apply_upgrades


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "profile.ini"), QSettings.Format.IniFormat)


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
    values = dict(before)
    apply_upgrades(values, 0)
    assert values == before
    assert {key: settings.value(key) for key in settings.allKeys()} == before


def test_historical_conversion_preserves_invalid_type_for_owner_recovery(settings):
    settings.setValue("Docks/dockNames", ["Bad type", "Old levels"])
    settings.setValue("Docks/Bad type/type", "broken")
    settings.setValue("Docks/Bad type/extension", "retained")
    settings.setValue("Docks/Old levels/type", 0)
    settings.setValue("CentralWidget/type", 2)
    values = {key: settings.value(key) for key in settings.allKeys()}
    apply_upgrades(values, 0)
    assert values["Docks/dockNames"] == ["Meters", "central", "Bad type"]
    assert values["Docks/Meters/type"] == 9
    assert values["Docks/Bad type/extension"] == "retained"
    assert values["Docks/central/type"] == 2
    assert "CentralWidget/type" not in values
    assert "Docks/Old levels/type" not in values
    # Schema preparation works on a snapshot, before initialization writes it.
    assert settings.value("CentralWidget/type") == 2
    assert settings.value("Docks/Old levels/type") == 0
