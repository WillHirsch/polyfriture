"""Exercise selected channels through the real window, docks and saved profile."""

import os
from pathlib import Path
import subprocess
import sys


WINDOW_SCRIPT = r"""
import sys
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QSettings, QSignalBlocker, Qt
from PyQt6.QtWidgets import QApplication

from polyfriture import (
    analyzer, audiobackend, generator, settings as settings_module,
    spectrogram, statisticswidget, theme_manager,
)
from polyfriture.settings_initialization import (
    FRITURE_IMPORT_STATE_KEY, initialize_settings,
)
from polyfriture.store import GetStore
from polyfriture.test.test_channel_configuration import SyntheticCaptureRing, SyntheticStream


app = QApplication([])
phase, profile_path, source_path = sys.argv[1:]
profile = QSettings(profile_path, QSettings.Format.IniFormat)
source = QSettings(source_path, QSettings.Format.IniFormat)
profile.setFallbacksEnabled(False)
source.setFallbacksEnabled(False)
interface = {"name": "USB interface", "index": 3, "hostapi": 0, "max_input_channels": 8}
alternate = {"name": "Alternate input", "index": 11, "hostapi": 0, "max_input_channels": 4}
# Reopening uses a different default and enumeration order. Saved identity must
# still refer to the interface, rather than the selector's previous index.
devices = [interface, alternate] if phase == "import" else [alternate, interface]
backend_type = getattr(audiobackend, "__AudioBackend")


def query_devices(*args, kind=None):
    return devices[0] if kind == "input" else devices


def open_stream(self, device):
    action = SimpleNamespace(stats=SimpleNamespace(input_overflows=0))
    return (SyntheticStream(device["index"]),
            SyntheticCaptureRing(device["max_input_channels"]),
            action, device["max_input_channels"])


with (
    patch.object(backend_type, "get_input_devices", lambda self: devices),
    patch.object(backend_type, "get_output_devices", lambda self: []),
    patch.object(backend_type, "open_stream", open_stream),
    patch.object(audiobackend.sounddevice, "query_devices", query_devices),
    patch.object(audiobackend.sounddevice, "query_hostapis", lambda index: {"name": "Synthetic API"}),
):
    backend = backend_type()

if phase == "import":
    # A genuine old-format channel pair is imported, then interpreted by the
    # ordinary settings owner. Importing must not change the source profile.
    source.setValue("AudioBackend/deviceName", "USB interface (8 channels) (Synthetic API)  (default)")
    source.setValue("AudioBackend/firstChannel", 7)
    source.setValue("AudioBackend/secondChannel", 2)
    source.setValue("AudioBackend/duoInput", -3)
    source.setValue("AudioBackend/channelGridColumns", 2)
    names = ["Scope", "FFT", "Spectrogram", "Octave", "Long", "Pitch"]
    source.setValue("Docks/dockNames", names)
    for name, identifier in zip(names, (1, 2, 3, 4, 7, 8)):
        source.setValue("Docks/" + name + "/type", identifier)
    source.setValue("sourceMarker", "original")
    source.sync()
    original_source = {key: source.value(key) for key in source.allKeys()}
    initialize_settings(profile, source)
    assert {key: source.value(key) for key in source.allKeys()} == original_source
else:
    saved = {key: profile.value(key) for key in profile.allKeys()}
    # A later Friture change must never replace this application's saved choices.
    source.setValue("AudioBackend/firstChannel", 0)
    source.setValue("AudioBackend/channelGridColumns", 17)
    source.setValue("sourceMarker", "changed after import")
    source.sync()
    initialize_settings(profile, source)
    assert {key: profile.value(key) for key in profile.allKeys()} == saved

assert profile.value(FRITURE_IMPORT_STATE_KEY) == "imported"

# Patch every production lookup, including the statistics timer and spectrogram
# clock. No singleton may enumerate or open real audio devices in this test.
for module in (analyzer, audiobackend, generator, settings_module, spectrogram, statisticswidget):
    module.AudioBackend = lambda: backend
analyzer.application_settings = lambda: profile
theme_manager.application_settings = lambda: profile

# Keep the synthetic enumeration patches throughout subsequent settings calls.
with (
    patch.object(audiobackend.sounddevice, "query_devices", query_devices),
    patch.object(audiobackend.sounddevice, "query_hostapis", lambda index: {"name": "Synthetic API"}),
    patch.object(backend_type, "open_stream", open_stream),
):
    window = analyzer.Friture()
    # Qt reports exceptions from Python slots through excepthook and continues.
    # Record them so a failed DSP/reset slot cannot quietly pass this test.
    signal_errors = []
    def exception_hook(kind, value, traceback):
        signal_errors.append(str(value))
        sys.__excepthook__(kind, value, traceback)
    sys.excepthook = exception_hook
    warnings = []
    window.qml_engine.warnings.connect(warnings.extend)
    window.resize(1600, 1100)
    window.show()
    app.processEvents()
    window.timer_toggle()
    assert not window.display_timer.isActive()
    assert not backend.running and not backend.stream.active

    panels = {dock.widgetId: dock.audiowidget for dock in window.dockmanager.docks}
    assert set(panels) == {1, 2, 3, 4, 7, 8, 9}
    dialog = window.settings_dialog
    final_ids = (1, 2, 4, 6, 7)

    def checked_ids():
        return tuple(index for index in range(dialog.listWidget_channels.count())
                     if dialog.listWidget_channels.item(index).checkState() == Qt.CheckState.Checked)

    def assert_selection(ids):
        configuration = backend.channel_configuration
        assert configuration.device_id == interface["index"]
        assert configuration.channel_ids == ids, (configuration.channel_ids, ids, dialog.label_inputStatus.text())
        assert window.audiobuffer.channel_configuration is configuration
        assert checked_ids() == ids
        for identifier, panel in panels.items():
            if identifier == 1:
                assert tuple(panel._curves) == ids
                labels = tuple(curve.name for curve in panel.view_model().plot_items)
            else:
                assert tuple(panel._channels) == ids
                labels = tuple(channel.label for channel in panel.view_model().channels)
            assert labels == configuration.channel_labels, (identifier, labels)

    def choose_channels(ids):
        # Prepare one checkbox-list edit, then exercise its normal Qt signal.
        # Per-click behavior is covered by dialog tests; repeated intermediate
        # selections would needlessly reconstruct all seven panels here.
        with QSignalBlocker(dialog.listWidget_channels):
            for channel_id in range(dialog.listWidget_channels.count()):
                state = Qt.CheckState.Checked if channel_id in ids else Qt.CheckState.Unchecked
                dialog.listWidget_channels.item(channel_id).setCheckState(state)
        dialog.listWidget_channels.itemChanged.emit(dialog.listWidget_channels.item(ids[0]))

    def assert_cleared():
        assert window.audiobuffer.newpoints == 0
        assert window.audiobuffer.lastDataTime == 0.
        assert all(curve.y_array().size == 0 for curve in panels[1]._curves.values())
        assert all(not np.any(state.dispbuffer) for state in panels[2]._channels.values())
        assert all(state.image.last_data_time == 0. for state in panels[3]._channels.values())
        assert all(not np.any(state.dispbuffers) for state in panels[4]._channels.values())
        assert all(state.ringbuffer.offset == 0 for state in panels[7]._channels.values())
        assert all(state.tracker.input_buf.offset == 0 for state in panels[8]._channels.values())
        assert all(state.old_max == state.old_rms == 1e-30 for state in panels[9]._channels.values())

    if phase == "import":
        assert_selection((2, 7))
        assert GetStore().channel_grid_columns == 2
        panels[1].settings_dialog.doubleSpinBox_timerange.setValue(600.)
        for ids in ((7,), (0, 3, 7), (0, 2, 3, 5, 7), final_ids):
            before = backend.channel_configuration.generation
            choose_channels(ids)
            assert_selection(ids)
            assert backend.channel_configuration.generation > before
            assert not backend.running and not backend.stream.active
            assert not window.display_timer.isActive()
            assert_cleared()
            # Real backend routing, AudioBuffer and Dock subscriptions all run.
            # Different physical inputs carry distinguishable tones and levels.
            window.timer_toggle()
            for packet in range(16):
                time = (packet * audiobackend.FRAMES_PER_BUFFER
                        + np.arange(audiobackend.FRAMES_PER_BUFFER)) / audiobackend.SAMPLING_RATE
                samples = np.stack([.02 * (channel + 1) * np.sin(2 * np.pi * (300 + 100 * channel) * time)
                                    for channel in range(8)], axis=1).astype(np.float32)
                backend.ringBuffer.load(samples)
                backend.fetchAudioData()
            np.testing.assert_array_equal(window.audiobuffer.data(len(samples)), samples[:, ids].T)
            for physical_id, state in panels[8]._channels.items():
                np.testing.assert_array_equal(state.tracker.input_buf.data(len(samples)),
                                              samples[:, physical_id][None, :])
            assert all(state.old_max > .01 for state in panels[9]._channels.values())
            assert all(state.image.last_data_time > 0. for state in panels[3]._channels.values())
            window.timer_toggle()
        dialog.spinBox_channelGridColumns.setValue(3)
        panels[3].settings_dialog.checkBox_rotated.setChecked(True)
    else:
        assert dialog.comboBox_inputDevice.currentIndex() == 1
        assert_selection(final_ids)
        assert GetStore().channel_grid_columns == 3
        assert panels[1].timerange == 600.
        assert panels[1].settings_dialog.doubleSpinBox_timerange.value() == 600.
        assert panels[3].view_model().rotated
        assert panels[3].settings_dialog.checkBox_rotated.isChecked()

    app.processEvents()
    assert not signal_errors, signal_errors
    assert not warnings, [warning.toString() for warning in warnings]
    window.slow_timer.stop()
    window.close()
    profile.sync()
    assert profile.value("AudioBackend/deviceName") == "USB interface"
    assert profile.value("AudioBackend/deviceHostApi") == "Synthetic API"
    assert tuple(int(value) for value in profile.value("AudioBackend/selectedChannels")) == final_ids
    assert profile.value("AudioBackend/channelGridColumns", type=int) == 3
    assert profile.value("Docks/Spectrogram/rotated", type=bool)
    # The application parents its external QML engine to the process Store.
    # Close and destroy the window and engine while Python and QApplication
    # are still alive, rather than leaving native teardown to finalization.
    engine = window.qml_engine
    sip.delete(window)
    sip.delete(engine)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
"""


def test_channel_selection_reaches_every_panel_and_survives_restart(tmp_path):
    # Each process owns its QML singleton, Qt registrations, exception hooks and
    # INI handles. Neither the registry nor installed Friture is consulted.
    environment = os.environ.copy()
    environment.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                       QT_QUICK_CONTROLS_STYLE="Basic")
    for phase in ("import", "restart"):
        result = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", WINDOW_SCRIPT, phase,
             str(tmp_path / "polyfriture.ini"), str(tmp_path / "friture.ini")],
            cwd=Path(__file__).resolve().parents[2], env=environment,
            capture_output=True, text=True, timeout=90,
        )
        assert result.returncode == 0, f"{phase}:\n{result.stdout}\n{result.stderr}"
