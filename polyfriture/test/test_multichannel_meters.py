"""Meter DSP, ordinary-dock lifecycle, and undecorated shared-scale geometry."""

import numpy as np
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtQuick import QQuickView
from PyQt6.QtWidgets import QWidget

from polyfriture.audiobuffer import AudioBuffer
from polyfriture.channel_configuration import ChannelConfiguration
from polyfriture.iec import IECScale, dB_to_IEC
from polyfriture.levels import Levels_Widget, LEVEL_TEXT_LABEL_STEPS
from polyfriture.qml_tools import qml_url
from polyfriture.signal.exp_smoothing import exp_smoothed_value
from polyfriture.test.test_channel_grid import named_items
from polyfriture.test.test_qml_integration import _register_qml_types


@pytest.fixture
def meters(qt_application):
    _register_qml_types()
    parent = QWidget()
    parent.show()
    instances = []

    def create(ids=(1, 4, 8), generation=1):
        panel = Levels_Widget(parent)
        buffer = AudioBuffer()
        buffer.handle_configuration_changed(ChannelConfiguration(0, ids, max(ids) + 1, generation))
        panel.set_buffer(buffer)
        buffer.configuration_changed.connect(panel.reset_channel_state)
        instances.append(panel)
        return panel, buffer

    yield create
    for panel in instances:
        panel.cleanup()
    parent.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_each_meter_matches_mono_and_preserves_response(meters):
    panel, _ = meters()
    monos = [meters((channel_id,))[0] for channel_id in panel._channels]
    rng = np.random.default_rng(17)
    rms = [1e-30] * 3
    peaks = [1e-30] * 3
    for length in (17, 1024, 5, 4096, 256):
        samples = rng.normal(size=(3, length)) * np.array([.7, .1, 0.])[:, None]
        panel.handle_new_data(samples)
        for index, (mono, state) in enumerate(zip(monos, panel._channels.values())):
            mono.handle_new_data(samples[index:index + 1])
            reference = next(iter(mono._channels.values()))
            rms[index] = exp_smoothed_value(panel.kernel, panel.alpha, samples[index] ** 2, rms[index])
            peaks[index] = max(abs(samples[index]).max(), peaks[index] * (1 - panel.alpha2))
            assert state.old_rms == pytest.approx(rms[index])
            assert state.old_max == pytest.approx(peaks[index])
            assert state.view.level_data.level_rms == reference.view.level_data.level_rms
            assert state.view.level_data.level_max == reference.view.level_data.level_max
            assert state.view.level_data_ballistic.peak_iec == reference.view.level_data_ballistic.peak_iec
    assert len({id(state.view.level_data_ballistic) for state in panel._channels.values()}) == 3
    assert all(state.view.vertical_axis is panel.view_model().vertical_axis for state in panel._channels.values())


def test_slow_text_and_peak_hold_are_local_and_reset_on_generation(meters):
    panel, buffer = meters()
    samples = np.zeros((3, 1024))
    samples[1] = 1.
    panel.handle_new_data(samples)
    states = list(panel._channels.values())
    assert states[1].view.level_data_ballistic.peak_iec == 1.
    assert states[0].view.level_data_ballistic.peak_iec == states[2].view.level_data_ballistic.peak_iec == 0.
    for _ in range(LEVEL_TEXT_LABEL_STEPS - 1):
        panel.canvasUpdate()
    assert states[1].view.level_data_slow.level_max == -600.
    panel.canvasUpdate()
    for state in states:
        assert state.view.level_data_slow.level_rms == state.view.level_data.level_rms
        assert state.view.level_data_slow.level_max == state.view.level_data.level_max
    buffer.handle_configuration_changed(ChannelConfiguration(0, (1, 4, 8), 9, 2))
    assert panel.i == 0
    assert all(state.view.level_data_slow.level_rms == -300. for state in panel._channels.values())
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert all(sip.isdeleted(state.view) for state in states)


def test_meter_grid_has_equal_cells_shared_iec_rows_and_no_x_axis(meters, qt_application):
    panel, buffer = meters((0, 2, 4, 6, 8))
    view = QQuickView()
    warnings = []
    view.engine().warnings.connect(warnings.extend)
    view.rootContext().setContextProperty("viewModel", panel.view_model())
    view.setInitialProperties({"configuredColumns": 3})
    view.setSource(qml_url("Levels.qml"))
    assert view.status() == QQuickView.Status.Ready, [e.toString() for e in view.errors()]
    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    view.resize(950, 640)
    view.show()
    for _ in range(3):
        qt_application.processEvents()
    root = view.rootObject()
    cells = named_items(root, "channel-grid-data-")
    assert len(cells) == 5
    assert len({(cell.width(), cell.height()) for cell in cells}) == 1
    assert len(named_items(root, "channel-grid-y-scale-")) == 2
    assert not named_items(root, "channel-grid-x-scale-")
    assert not named_items(root, "channel-grid-color-scale")
    assert all(not cell.property("decorationsVisible") for cell in cells)
    texts = [item.property("text") for item in named_items(root, "")]
    assert texts.count("Peak -Inf dB FS") == 5
    assert texts.count("RMS  -Inf dB FS") == 5
    panel.handle_new_data(np.ones((5, 1024)))
    for _ in range(LEVEL_TEXT_LABEL_STEPS):
        panel.canvasUpdate()
    qt_application.processEvents()
    assert len({(cell.width(), cell.height()) for cell in cells}) == 1
    buffer.handle_configuration_changed(ChannelConfiguration(0, (7,), 9, 2))
    qt_application.processEvents()
    assert len(named_items(root, "channel-grid-data-")) == 1
    assert not warnings, [warning.toString() for warning in warnings]
    view.hide()
    sip.delete(view)


def test_iec_axis_positions_match_meter_height():
    values = np.array([-70., -60., -50., -40., -30., -20., -10., -6., -3., 0.])
    expected = np.array([dB_to_IEC(value) for value in values])
    np.testing.assert_allclose(IECScale.transform(values), expected)
    np.testing.assert_allclose(IECScale.inverse(expected), values)


def test_meter_can_switch_close_and_restore_as_an_ordinary_dock(tmp_path):
    # Friture registers process-global QML types and a single-engine Store.
    # Keep this real-window test separate from other tests' QQmlEngines.
    import os
    import subprocess
    import sys
    script = r"""
import sys
from unittest.mock import Mock
import numpy as np
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication
from polyfriture import analyzer, settings as settings_module, theme_manager
from polyfriture.channel_configuration import ChannelConfiguration
from polyfriture.settings_initialization import initialize_settings
app = QApplication([])
profile = QSettings(sys.argv[1], QSettings.Format.IniFormat)
source = QSettings(sys.argv[2], QSettings.Format.IniFormat)
profile.setFallbacksEnabled(False)
source.setFallbacksEnabled(False)
profile.setValue('Docks/dockNames', [])
initialize_settings(profile, source)
analyzer.application_settings = lambda: profile
theme_manager.application_settings = lambda: profile
backend = Mock()
backend.channel_configuration = ChannelConfiguration(0, (1, 4, 8), 9, 1)
backend.get_readable_devices_list.return_value = []
analyzer.AudioBackend = lambda: backend
settings_module.AudioBackend = lambda: backend
window = analyzer.Friture()
assert not hasattr(window, 'level_widget')
assert len(window.dockmanager.docks) == 1
dock = window.dockmanager.docks[0]
assert dock.widgetId == 9
assert tuple(dock.audiowidget._channels) == (1, 4, 8)
old_meter = dock.audiowidget
assert len(list(old_meter.view_model().channels)) == 3
dock.widget_select(1)
assert list(old_meter.view_model().channels) == []
dock.widget_select(9)
assert tuple(dock.audiowidget._channels) == (1, 4, 8)
window.dockmanager.new_dock()
second = window.dockmanager.docks[-1]
second.widget_select(9)
assert len(window.dockmanager.docks) == 2
assert second.audiowidget is not dock.audiowidget
assert second.audiowidget._channels[1].view is not dock.audiowidget._channels[1].view
window.audiobuffer.handle_new_data(np.ones((3, 1024)), 1., None, 1)
assert second.audiowidget._channels[1].old_max == 1.
retired_meter = second.audiowidget
window.dockmanager.close_dock(second)
window.audiobuffer.handle_new_data(np.full((3, 1024), .25), 2., None, 1)
assert not retired_meter._channels
window.saveAppState()
assert profile.value('Docks/' + dock.objectName() + '/type', type=int) == 9
window.dockmanager.close_dock(dock)
assert not window.dockmanager.docks
window.close()
profile.sync()
initialize_settings(profile, source)
assert not profile.value('Docks/dockNames')
"""
    result = subprocess.run([sys.executable, "-c", script,
                             str(tmp_path / "profile.ini"), str(tmp_path / "source.ini")],
                            text=True, capture_output=True, timeout=60, env=os.environ.copy())
    assert result.returncode == 0, result.stdout + result.stderr
