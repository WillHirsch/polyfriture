"""Capture controls and profile compatibility after playback removal."""

import sys
from unittest.mock import Mock

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from polyfriture import analyzer, settings as settings_module, theme_manager
from polyfriture.settings_initialization import initialize_settings


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def profile(tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "profile.ini"), QSettings.Format.IniFormat)
    settings.setFallbacksEnabled(False)
    monkeypatch.setattr(analyzer, "application_settings", lambda: settings)
    monkeypatch.setattr(theme_manager, "application_settings", lambda: settings)
    yield settings
    sip.delete(settings)


@pytest.fixture
def friture_source(tmp_path):
    source = QSettings(str(tmp_path / "empty-friture.ini"), QSettings.Format.IniFormat)
    source.setFallbacksEnabled(False)
    yield source
    sip.delete(source)


def test_migration_discards_only_playback_preferences(profile, friture_source):
    # Invalid retired values must also be harmless and must not be interpreted.
    profile.setValue("AudioBackend/showPlayback", "invalid")
    profile.setValue("AudioBackend/historyLength", "invalid")
    profile.setValue("AudioBackend/deviceName", "Saved device")
    profile.setValue("AudioBackend/firstChannel", 3)
    profile.setValue("AudioBackend/themePreference", 2)
    profile.setValue("Docks/lastSettings/5/type", 5)
    profile.setValue("Docks/lastSettings/5/generator kind", 3)

    initialize_settings(profile, friture_source)
    first_result = {key: profile.value(key) for key in profile.allKeys()}
    initialize_settings(profile, friture_source)
    assert {key: profile.value(key) for key in profile.allKeys()} == first_result

    assert not profile.contains("AudioBackend/showPlayback")
    assert not profile.contains("AudioBackend/historyLength")
    assert profile.value("AudioBackend/deviceName") == "Saved device"
    assert profile.value("AudioBackend/firstChannel", type=int) == 3
    assert profile.value("AudioBackend/themePreference", type=int) == 2
    assert profile.value("Docks/lastSettings/5/type", type=int) == 5
    assert profile.value("Docks/lastSettings/5/generator kind", type=int) == 3


def test_window_starts_and_capture_toggles_without_playback(app, profile, friture_source, monkeypatch):
    # Keep the real window, QML, settings dialog, capture timer and dock manager;
    # substitute hardware and a fresh empty layout rather than opening devices.
    backend = Mock()
    backend.channel_configuration = None
    backend.get_readable_devices_list.return_value = []
    monkeypatch.setattr(analyzer, "AudioBackend", lambda: backend)
    monkeypatch.setattr(settings_module, "AudioBackend", lambda: backend)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    profile.setValue("Docks/dockNames", [])
    profile.setValue("AudioBackend/showPlayback", 2)
    profile.setValue("AudioBackend/historyLength", 600)
    initialize_settings(profile, friture_source)

    window = analyzer.Friture()
    try:
        assert window.main_tile_layout is not None
        assert window.display_timer.isActive()
        assert window._main_window_view_model.toolbar_view_model.recording
        assert not hasattr(window, "player")
        assert not hasattr(window, "playback_widget")
        assert not hasattr(window.settings_dialog, "playbackGroup")
        backend.restart.assert_called_once()

        toolbar = window._main_window_view_model.toolbar_view_model
        toolbar.recording_toggle()
        assert not window.display_timer.isActive()
        assert not toolbar.recording
        backend.pause.assert_called_once()

        toolbar.recording_toggle()
        assert window.display_timer.isActive()
        assert toolbar.recording
        assert backend.restart.call_count == 2
    finally:
        window.display_timer.stop()
        window.slow_timer.stop()
        window.close()
        sip.delete(window)

    assert not profile.contains("AudioBackend/showPlayback")
    assert not profile.contains("AudioBackend/historyLength")
