"""Verify dock, QML and input lifetimes together without accessing audio devices."""

import os
from pathlib import Path
import subprocess
import sys


LIFECYCLE_SCRIPT = r"""
import sys
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QSettings, QSignalBlocker, Qt
from PyQt6.QtQml import QQmlContext, QQmlEngine, QQmlExpression
from PyQt6.QtQuick import QQuickItem
from PyQt6.QtWidgets import QApplication

from polyfriture import (
    analyzer, audiobackend, generator, settings as settings_module,
    spectrogram, statisticswidget, theme_manager,
)
from polyfriture.dock import Dock
from polyfriture.settings_initialization import initialize_settings
from polyfriture.store import GetStore
from polyfriture.widgetdict import getWidgetById, widgetIds, widgets
from polyfriture.test.test_channel_configuration import SyntheticCaptureRing, SyntheticStream
from polyfriture.test.test_channel_grid import assert_equal_data_geometry, named_items

app = QApplication([])
profile = QSettings(sys.argv[1], QSettings.Format.IniFormat)
source = QSettings(sys.argv[2], QSettings.Format.IniFormat)
profile.setFallbacksEnabled(False)
source.setFallbacksEnabled(False)
initialize_settings(profile, source)
profile.setValue("Docks/dockNames", ["Active"])
profile.setValue("Docks/Active/type", 1)
profile.setValue("AudioBackend/deviceName", "Synthetic interface")
profile.setValue("AudioBackend/deviceHostApi", "Synthetic API")
profile.setValue("AudioBackend/selectedChannels", [1, 4, 8])
device = {"name": "Synthetic interface", "index": 3, "hostapi": 0, "max_input_channels": 9}
backend_type = getattr(audiobackend, "__AudioBackend")


def open_stream(self, device):
    action = SimpleNamespace(stats=SimpleNamespace(input_overflows=0))
    return SyntheticStream(device["index"]), SyntheticCaptureRing(9), action, 9


with (
    patch.object(backend_type, "get_input_devices", lambda self: [device]),
    patch.object(backend_type, "get_output_devices", lambda self: []),
    patch.object(backend_type, "open_stream", open_stream),
):
    backend = backend_type()
backend.get_readable_output_devices_list = lambda: []
for module in (analyzer, audiobackend, generator, settings_module, spectrogram, statisticswidget):
    module.AudioBackend = lambda: backend
analyzer.application_settings = lambda: profile
theme_manager.application_settings = lambda: profile

with patch.object(audiobackend.sounddevice, "query_hostapis", lambda index: {"name": "Synthetic API"}):
    window = analyzer.Friture()
window.resize(1280, 900)
window.show()
window.timer_toggle()
window.slow_timer.stop()
assert not window.display_timer.isActive() and not backend.running
errors = []
warnings = []
def exception_hook(kind, value, traceback):
    errors.append(str(value))
    sys.__excepthook__(kind, value, traceback)
sys.excepthook = exception_hook
window.qml_engine.warnings.connect(warnings.extend)


def settle():
    # Retire deferred roots before measuring ownership, while their models,
    # QApplication and the external QML engine are all still alive.
    for _ in range(3):
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def choose_channels(ids):
    items = window.settings_dialog.listWidget_channels
    with QSignalBlocker(items):
        for index in range(items.count()):
            items.item(index).setCheckState(Qt.CheckState.Checked if index in ids else Qt.CheckState.Unchecked)
    items.itemChanged.emit(items.item(ids[0]))
    assert backend.channel_configuration.channel_ids == ids


def choose_panel(dock, identifier):
    # Exercise the real selector: its displayed names and index-to-ID mapping
    # must both follow the registry, including the meter after the removed ID.
    selector = dock.dock_qml.findChild(QQuickItem, "widgetSelector")
    assert selector is not None
    assert selector.property("count") == len(widgets)
    labels = QQmlExpression(QQmlEngine.contextForObject(selector), selector,
        "(function() { var names = []; for (var i = 0; i < count; ++i) names.push(textAt(i)); return names.join('|'); })()")
    result, undefined = labels.evaluate()
    assert not labels.hasError(), labels.error().toString()
    assert not undefined
    assert result == "|".join(widget["Name"] for widget in widgets)
    selector.setProperty("currentIndex", widgetIds().index(identifier))
    assert dock.widgetId == identifier
    assert selector.property("currentText") == getWidgetById(identifier)["Name"]


def verify_panel(dock, ids, columns):
    panel = dock.audiowidget
    assert panel.audiobuffer is window.audiobuffer
    assert panel.audiobuffer.channel_configuration is backend.channel_configuration
    if dock.widgetId == 5:
        # Generator settings describe output, so they do not gain input cells.
        assert panel.stream is None
        assert not hasattr(panel.view_model(), "channels")
        return
    expected_labels = backend.channel_configuration.channel_labels
    if dock.widgetId == 1:
        assert tuple(panel._curves) == ids
        assert tuple(curve.name for curve in panel.view_model().plot_items) == expected_labels
        return
    assert tuple(panel._channels) == ids
    assert tuple(view.label for view in panel.view_model().channels) == expected_labels
    root = dock.audio_widget_qml
    if dock.widgetId == 3:
        root = named_items(root.parentItem(), "spectrogram-channel-grid")[0]
    assert root.property("configuredColumns") == columns
    assert_equal_data_geometry(root, len(ids))
    ordinary_columns = min(columns, len(ids))
    ordinary_rows = (len(ids) + ordinary_columns - 1) // ordinary_columns
    rotated = dock.widgetId == 3 and panel.view_model().rotated
    expected_columns, expected_rows = ((ordinary_rows, ordinary_columns) if rotated
                                       else (ordinary_columns, ordinary_rows))
    assert (root.property("columnCount"), root.property("rowCount")) == (expected_columns, expected_rows)
    assert len(named_items(root, "channel-grid-y-scale-")) == expected_rows
    assert len(named_items(root, "channel-grid-x-scale-")) == (0 if dock.widgetId == 9 else expected_columns)
    assert len(named_items(root, "channel-grid-color-scale")) == (1 if dock.widgetId == 3 else 0)


manager = window.dockmanager
assert len(manager.docks) == 1
dock = manager.docks[0]
# QML creates a few shared engine contexts lazily on first use of a component.
# Warm each registry type before measuring repeated dock ownership, then return
# to the same scope used at the end of the test.
for identifier in (2, 3, 4, 5, 7, 8, 9, 1):
    choose_panel(dock, identifier)
    settle()
settle()
initial = {"docks": len(window.findChildren(Dock)),
           "contexts": len(window.qml_engine.findChildren(QQmlContext)) + len(window.findChildren(QQmlContext)),
           "store_models": len(GetStore()._dock_states)}
retained = []
for cycle, identifier in enumerate((1, 2, 3, 4, 5, 7, 8, 9, 1)):
    old_panel = dock.audiowidget
    old_contexts = dock.audio_widget_qml.findChildren(QQmlContext)
    if dock.widgetId != identifier:
        choose_panel(dock, identifier)
        settle()
        assert sip.isdeleted(old_panel)
        assert all(sip.isdeleted(context) for context in old_contexts)
    else:
        choose_panel(dock, identifier)
    panel = dock.audiowidget
    if identifier == 5:
        panel.view_model().sineGenerator.frequency = 1234.
        output_state = (panel.state, panel.stream, panel.device, panel.t)
    ids = (1, 4, 8) if cycle % 2 == 0 else (0, 2, 5, 8)
    choose_channels(ids)
    columns = 2 if cycle % 2 == 0 else 3
    window.settings_dialog.spinBox_channelGridColumns.setValue(columns)
    if identifier == 3:
        panel.settings_dialog.checkBox_rotated.setChecked(True)
        panel.settings_dialog.doubleSpinBox_timerange.setValue(20.)
    settle()
    verify_panel(dock, ids, columns)
    window.timer_toggle()
    for packet in range(8):
        t = (packet * audiobackend.FRAMES_PER_BUFFER + np.arange(audiobackend.FRAMES_PER_BUFFER)) / audiobackend.SAMPLING_RATE
        samples = np.stack([.02 * (channel + 1) * np.sin(2 * np.pi * (300 + 100 * channel) * t)
                            for channel in range(9)], axis=1).astype(np.float32)
        backend.ringBuffer.load(samples)
        backend.fetchAudioData()
    window.timer_toggle()
    np.testing.assert_array_equal(window.audiobuffer.data(len(samples)), samples[:, ids].T)
    if identifier == 5:
        assert (panel.state, panel.stream, panel.device, panel.t) == output_state
        assert panel.view_model().sineGenerator.frequency == 1234.
    old_model, old_dialog, old_qml = panel.view_model(), panel.settings_dialog, dock.audio_widget_qml
    generator_models = [item.view_model() for item in panel.generators] if identifier == 5 else []
    old_contexts = dock.findChildren(QQmlContext)
    manager.close_dock(dock)
    settle()
    assert not manager.docks
    assert all(sip.isdeleted(obj) for obj in (dock, panel, old_model, old_dialog, old_qml))
    assert all(sip.isdeleted(model) for model in generator_models)
    assert all(sip.isdeleted(context) for context in old_contexts)
    assert not window.findChildren(Dock)
    # Reconfiguration and audio delivery must not call a disposed dock.
    choose_channels((0, 4, 8))
    window.timer_toggle()
    backend.ringBuffer.load(samples)
    backend.fetchAudioData()
    window.timer_toggle()
    manager.new_dock()
    dock = manager.docks[-1]
    assert dock.widgetId == identifier
    settle()
    verify_panel(dock, (0, 4, 8), columns)
    if identifier == 3:
        assert dock.audiowidget.view_model().rotated
        assert dock.audiowidget.settings_dialog.doubleSpinBox_timerange.value() == 20.
    if identifier == 5:
        assert dock.audiowidget.view_model().sineGenerator.frequency == 1234.
    retained.append({"docks": len(window.findChildren(Dock)),
                     "contexts": len(window.qml_engine.findChildren(QQmlContext)) + len(window.findChildren(QQmlContext)),
                     "store_models": len(GetStore()._dock_states)})
assert not errors, errors
assert not warnings, list(dict.fromkeys(warning.toString() for warning in warnings))
# The same scope is active at both ends. Closed docks and contexts must not
# accumulate even when every other visualization was created in between.
assert retained[-1] == initial, (initial, retained)
window.close()
engine = window.qml_engine
sip.delete(window)
sip.delete(engine)
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
"""


def test_repeated_dock_replacement_close_and_reopen_share_current_input_and_layout(tmp_path):
    # Friture's QML registrations and Store have process lifetimes. A child
    # process gives this complete window its own engine and explicit teardown.
    environment = os.environ.copy()
    environment.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                       QT_QUICK_CONTROLS_STYLE="Basic")
    result = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", LIFECYCLE_SCRIPT,
         str(tmp_path / "profile.ini"), str(tmp_path / "source.ini")],
        cwd=Path(__file__).resolve().parents[2], env=environment,
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
