"""Read raw Friture preferences without owning application validation rules."""

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QByteArray, QSettings

from polyfriture import friture_settings, friture_settings_windows


def test_windows_reader_prefers_standalone_profile_without_combining_sources(monkeypatch):
    monkeypatch.setattr(friture_settings_windows, "read_native_settings",
                        lambda: {"themePreference": 1})

    def unexpected_store_access():
        raise AssertionError("A standalone profile must take precedence over Store settings")

    monkeypatch.setattr(friture_settings_windows, "read_store_settings", unexpected_store_access)

    assert friture_settings._read_windows() == ({"themePreference": 1}, "imported")


def test_nonempty_standalone_profile_is_read_without_validation_or_store_fallback(monkeypatch):
    monkeypatch.setattr(friture_settings_windows, "read_native_settings",
                        lambda: {"themePreference": "invalid"})

    def unexpected_store_access():
        raise AssertionError("A nonempty standalone profile must not select another installation")

    monkeypatch.setattr(friture_settings_windows, "read_store_settings", unexpected_store_access)

    assert friture_settings._read_windows() == ({"themePreference": "invalid"}, "imported")


def test_standalone_metadata_alone_does_not_hide_store_preferences(monkeypatch):
    monkeypatch.setattr(friture_settings_windows, "read_native_settings",
                        lambda: {"Polyfriture/schemaVersion": 999})
    monkeypatch.setattr(friture_settings_windows, "read_store_settings",
                        lambda: {"themePreference": 2})

    assert friture_settings._read_windows() == ({"themePreference": 2}, "imported")


def test_explicit_friture_source_bypasses_default_discovery(tmp_path, monkeypatch):
    source = QSettings(str(tmp_path / "friture.ini"), QSettings.Format.IniFormat)
    source.setValue("themePreference", 1)
    source.sync()

    def unexpected_discovery():
        raise AssertionError("An explicit Friture store must bypass automatic discovery")

    monkeypatch.setattr(friture_settings, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(friture_settings, "_read_windows", unexpected_discovery)

    assert friture_settings.read_friture_settings(source) == ({"themePreference": 1}, "imported")


def test_reader_preserves_raw_preferences_qt_values_and_source_bytes(tmp_path):
    source = QSettings(str(tmp_path / "friture.ini"), QSettings.Format.IniFormat)
    values = {
        "AudioBackend/deviceName": "Input",
        "CentralWidget/type": 2,
        "CentralWidget/custom/value": "historical layout retained",
        "Docks/dockNames": ["Sweep"],
        "Docks/Sweep/type": 5,
        "Docks/Sweep/sweep start frequency": "20.5",
        "Docks/Sweep/sweep stop frequency": 21999.5,
        "extension/value": QByteArray(b"\x00\xff\x01"),
        "Polyfriture/schemaVersion": 999,
        "pOlYfRiTuRe/unrecognized": "destination metadata excluded",
    }
    for key, value in values.items():
        source.setValue(key, value)
    source.sync()
    before = (tmp_path / "friture.ini").read_bytes()

    imported, state = friture_settings.read_friture_settings(source)

    assert state == "imported"
    assert imported == {key: value for key, value in values.items()
                        if key.split("/", 1)[0].casefold() != "polyfriture"}
    assert isinstance(imported["extension/value"], QByteArray)
    assert (tmp_path / "friture.ini").read_bytes() == before
    assert source.value("Polyfriture/schemaVersion") == 999


@pytest.mark.parametrize("key,value", [
    ("themePreference", "invalid"),
    ("AudioBackend/firstChannel", -1),
    ("Docks/dockNames", ["bad/name"]),
    ("Docks/Scope/type", "unknown"),
    ("Docks/Spectrum/fftSize", "invalid"),
    ("Docks/Pitch/conf", "nan"),
    ("MainWindow/windowGeometry", "not a byte array"),
])
def test_reader_leaves_value_validation_to_normal_settings_owners(tmp_path, key, value):
    source = QSettings(str(tmp_path / "friture.ini"), QSettings.Format.IniFormat)
    source.setValue(key, value)
    source.setValue("extension/value", QByteArray(b"retain"))
    source.sync()
    before = (tmp_path / "friture.ini").read_bytes()

    assert friture_settings.read_friture_settings(source) == (
        {key: value, "extension/value": QByteArray(b"retain")}, "imported")
    assert (tmp_path / "friture.ini").read_bytes() == before
