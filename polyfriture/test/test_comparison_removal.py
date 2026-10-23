"""Compatibility with saved panels retired from Polyfriture."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest
from PyQt6.QtCore import QByteArray, QSettings
from PyQt6.QtWidgets import QApplication, QWidget

from polyfriture.audiobuffer import AudioBuffer
from polyfriture.audiobackend import SAMPLING_RATE
from polyfriture.dockmanager import DockLayoutSettings, DockManager
from polyfriture.spectrum import Spectrum_Widget
from polyfriture.settings_initialization import initialize_settings
from polyfriture.widgetdict import getWidgetById, widgetIds


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "profile.ini"), QSettings.Format.IniFormat)


def initialize_profile(settings):
    source = QSettings(settings.fileName() + ".empty-friture", QSettings.Format.IniFormat)
    source.setFallbacksEnabled(False)
    initialize_settings(settings, source)
    settings.sync()
    assert settings.status() == QSettings.Status.NoError


def test_retired_panels_are_removed_without_changing_surviving_settings(settings):
    settings.setValue("Docks/dockNames", ["scope", "delay", "levels", "pitch", "old-level"])
    for name, widget_id in [("scope", 1), ("delay", 6), ("levels", 7), ("pitch", 8), ("old-level", 0)]:
        settings.setValue(f"Docks/{name}/type", widget_id)
    settings.setValue("Docks/delay/delay_range", 4.5)
    settings.setValue("Docks/scope/timeRange", 25)
    settings.setValue("Docks/levels/history_length", 600)
    settings.setValue("Docks/pitch/freqMin", 80)
    settings.setValue("Docks/widgetIdStack", [6, 7, 6, 8, 2])
    settings.setValue("Docks/lastSettings/6/delay_range", 4.5)
    settings.setValue("Docks/lastSettings/7/history_length", 300)
    settings.setValue("Docks/lastSettings/2/fftSize", 9)
    settings.setValue("unrelated", "preserved")

    initialize_profile(settings)

    assert settings.value("Docks/dockNames") == ["Meters", "scope", "levels", "pitch"]
    assert settings.value("Docks/widgetIdStack") == [7, 8, 2]
    for group in ("Docks/delay", "Docks/old-level", "Docks/lastSettings/6"):
        assert not any(key.startswith(group + "/") for key in settings.allKeys())
    assert settings.value("Docks/levels/type") == 7
    assert settings.value("Docks/pitch/type") == 8
    assert settings.value("Docks/scope/timeRange") == 25
    assert settings.value("Docks/levels/history_length") == 600
    assert settings.value("Docks/pitch/freqMin") == 80
    assert settings.value("Docks/lastSettings/7/history_length") == 300
    assert settings.value("Docks/lastSettings/2/fftSize") == 9
    assert settings.value("unrelated") == "preserved"

    first_result = {key: settings.value(key) for key in settings.allKeys()}
    initialize_profile(settings)
    assert {key: settings.value(key) for key in settings.allKeys()} == first_result


@pytest.mark.parametrize("widget_id", [6, "6"])
def test_retired_central_panel_is_removed_after_legacy_relocation(settings, widget_id):
    settings.setValue("CentralWidget/type", widget_id)
    settings.setValue("CentralWidget/delay_range", 4.5)
    settings.setValue("Docks/dockNames", ["spectrum"])
    settings.setValue("Docks/spectrum/type", 2)
    settings.setValue("Docks/spectrum/fftSize", 9)

    initialize_profile(settings)

    assert settings.value("Docks/dockNames") == ["Meters", "spectrum"]
    assert settings.value("Docks/spectrum/fftSize") == 9
    assert not any(key.startswith(("CentralWidget/", "Docks/central/")) for key in settings.allKeys())


def test_retired_legacy_central_panel_preserves_existing_central_panel(settings):
    settings.setValue("CentralWidget/type", 6)
    settings.setValue("Docks/dockNames", ["central"])
    settings.setValue("Docks/central/type", 7)
    settings.setValue("Docks/central/history_length", 600)

    initialize_profile(settings)

    assert settings.value("Docks/dockNames") == ["Meters", "central"]
    assert settings.value("Docks/central/type") == 7
    assert settings.value("Docks/central/history_length") == 600
    assert not settings.contains("CentralWidget/type")


@pytest.mark.parametrize("central", [False, True])
def test_singleton_ini_dock_names_keep_surviving_panel(settings, central):
    # This is the valid historical INI encoding, rather than a malformed dock name.
    settings.setValue("Docks/dockNames", "spectrum")
    settings.setValue("Docks/spectrum/type", 2)
    settings.setValue("Docks/spectrum/fftSize", 9)
    if central:
        settings.setValue("CentralWidget/type", 6)
    settings.sync()
    loaded = QSettings(settings.fileName(), QSettings.Format.IniFormat)
    assert loaded.value("Docks/dockNames") == "spectrum"

    initialize_profile(loaded)

    assert loaded.value("Docks/dockNames") == ["Meters", "spectrum"]
    assert loaded.value("Docks/spectrum/type") == 2
    assert loaded.value("Docks/spectrum/fftSize") == 9


@pytest.mark.parametrize("stack, expected", [
    (6, []), ("6", []), ("+006", []), ([], []), (None, []),
    (7, [7]), ("8", ["8"]),
    ([6, "006", "+6", " 6 ", 7, "8", 6.5, "other"], [7, "8", 6.5, "other"]),
])
def test_historical_stack_encodings_remove_only_retired_widget(settings, stack, expected):
    settings.setValue("Docks/widgetIdStack", stack)
    settings.sync()
    loaded = QSettings(settings.fileName(), QSettings.Format.IniFormat)

    initialize_profile(loaded)

    assert loaded.value("Docks/widgetIdStack") == expected


@pytest.mark.parametrize("stack", [1.5, 0.0, True, False, QByteArray(b"23"), {"old": 6}])
def test_cleanup_preserves_unrecognized_stack_types_and_removes_retired_cache(settings, stack):
    settings.setValue("Docks/widgetIdStack", stack)
    settings.setValue("Docks/lastSettings/6/delay_range", 4.5)
    settings.setValue("Docks/lastSettings/2/fftSize", 7)

    initialize_profile(settings)

    assert settings.value("Docks/widgetIdStack") == stack
    assert not settings.contains("Docks/lastSettings/6/delay_range")
    assert settings.value("Docks/lastSettings/2/fftSize") == 7


@pytest.mark.parametrize("central", [False, True])
def test_all_retired_layout_restores_only_the_former_permanent_meters(settings, central):
    if central:
        settings.setValue("CentralWidget/type", 6)
    else:
        settings.setValue("Docks/dockNames", ["delay"])
        settings.setValue("Docks/delay/type", 6)
    settings.setValue("Docks/widgetIdStack", [6])
    settings.setValue("Docks/lastSettings/6/delay_range", 4.5)

    initialize_profile(settings)

    # Read the persisted representation after retirement and meter migration.
    restored = QSettings(settings.fileName(), QSettings.Format.IniFormat)
    restored.beginGroup("Docks")
    host = SimpleNamespace(qml_engine=object())
    manager = SimpleNamespace(docks=[], last_widget_stack=[], last_settings={}, logger=Mock(),
                              settings_model=DockLayoutSettings(), parent=lambda: host)
    # The new meter replaces the old permanent component. Retiring the delay
    # layout must still never substitute unrelated analyzer panels or open audio.
    with patch("polyfriture.dockmanager.Dock") as dock:
        DockManager.restoreState(manager, restored)
        dock.assert_called_once_with(host, "Meters", host.qml_engine, 9)
        dock.return_value.restoreState.assert_called_once_with(restored)
        assert manager.docks == [dock.return_value]
    assert restored.value("Meters/type") == 9
    assert manager.last_widget_stack == []
    assert manager.last_settings == {}


def test_panel_registry_keeps_surviving_numeric_ids():
    assert widgetIds() == [1, 2, 3, 4, 5, 7, 8, 9]
    assert getWidgetById(7)["Name"] == "Long-time levels"
    assert getWidgetById(8)["Name"] == "Pitch Tracker"
    assert getWidgetById(9)["Name"] == "Level meters"


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def spectrum(app):
    parent = QWidget()
    widget = Spectrum_Widget(parent)
    widget.setfftsize(1024)
    buffer = AudioBuffer()
    from polyfriture.channel_configuration import ChannelConfiguration
    buffer.handle_configuration_changed(ChannelConfiguration(0, (0, 1), 2, 1))
    widget.set_buffer(buffer)
    yield widget, buffer
    widget.settings_dialog.close()
    parent.close()
    parent.deleteLater()
    app.processEvents()


def test_spectrum_keeps_weighted_first_channel_measurement_and_peaks(spectrum):
    widget, buffer = spectrum
    times = np.arange(widget.fft_size * 4) / SAMPLING_RATE
    samples = np.vstack([
        np.sin(2 * np.pi * 1500 * times),
        10 * np.sin(2 * np.pi * 6000 * times),
    ])
    buffer.handle_new_data(samples, 0.0, None, buffer.channel_configuration.generation)
    state = widget._channels[0]
    with patch.object(state.plot, "setdata", wraps=state.plot.setdata) as setdata:
        widget.handle_new_data(samples)

    frequencies, levels, peak_frequency, _ = setdata.call_args.args
    assert peak_frequency == pytest.approx(1500, abs=SAMPLING_RATE / widget.fft_size)
    np.testing.assert_allclose(levels, widget.log_spectrogram(state.dispbuffer) + widget.w)
    assert frequencies.shape == levels.shape == state.plot.peak.shape
    assert np.isfinite(levels).all()
    assert state.plot.view_model().vertical_axis.name == "PSD (dB A)"


def test_spectrum_saved_parameters_survive_restoration(spectrum, settings):
    widget, _ = spectrum
    parameters = {
        "fftSize": 7, "freqScale": 1, "freqMin": 80, "freqMax": 16000,
        "Min": -120, "Max": -10, "weighting": 2, "responseTime": 3,
        "showFreqLabels": False, "showPitchLabel": False,
    }
    for key, value in parameters.items():
        settings.setValue(key, value)

    widget.restoreState(settings)
    saved = QSettings(settings.fileName() + ".saved", QSettings.Format.IniFormat)
    widget.saveState(saved)

    assert {key: saved.value(key) for key in saved.allKeys()} == parameters
    assert widget.fft_size == 4096
    assert widget.minfreq == 80
    assert widget.maxfreq == 16000
    assert widget.weighting == 2
    assert widget.response_time == 1.0
