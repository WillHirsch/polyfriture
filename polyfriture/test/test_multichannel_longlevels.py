"""Independent long-level filters and histories on one shared channel grid."""

import numpy as np
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QSettings
from PyQt6.QtQml import QQmlComponent, QQmlEngine
from PyQt6.QtWidgets import QWidget

from polyfriture.audiobuffer import AudioBuffer
from polyfriture.channel_configuration import ChannelConfiguration
from polyfriture.longlevels import LongLevelWidget
from polyfriture.qml_tools import qml_url
from polyfriture.test.test_channel_grid import assert_equal_data_geometry, named_items, settle
from polyfriture.test.test_qml_integration import _register_qml_types


@pytest.fixture
def levels_factory(qt_application):
    parents = []
    def create(ids):
        parent = QWidget()
        parents.append(parent)
        panel = LongLevelWidget(parent)
        buffer = AudioBuffer()
        buffer.handle_configuration_changed(ChannelConfiguration(0, ids, max(ids) + 1, 1))
        panel.set_buffer(buffer)
        panel.setresptime(0.5)
        panel.setduration(10.)
        buffer.configuration_changed.connect(panel.reset_channel_state)
        buffer.new_data_available.connect(panel.handle_new_data)
        return panel, buffer
    yield create
    for parent in parents:
        for panel in parent.findChildren(LongLevelWidget):
            panel.cleanup()
        sip.delete(parent)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def push(buffer, data):
    buffer.handle_new_data(data, 1., None, buffer.channel_configuration.generation)


def test_each_channel_matches_mono_history_filter_memory_and_shared_time(levels_factory):
    panel, buffer = levels_factory((1, 4, 9))
    samples = np.array([np.full(8192, 0.1), np.full(8192, 0.5), np.zeros(8192)])
    # Uneven callbacks exercise the shared pending-sample cursor.
    for start, end in ((0, 333), (333, 1200), (1200, 8192)):
        push(buffer, samples[:, start:end])
    channels = list(panel._channels.values())
    assert [channel.label for channel in channels] == ["Channel 2", "Channel 5", "Channel 10"]
    for row, channel in enumerate(channels):
        mono, mono_buffer = levels_factory((0,))
        for start, end in ((0, 333), (333, 1200), (1200, 8192)):
            push(mono_buffer, samples[row:row + 1, start:end])
        reference = mono._channels[0]
        assert channel.ringbuffer.offset == reference.ringbuffer.offset
        np.testing.assert_allclose(channel.ringbuffer.data(channel.ringbuffer.offset),
                                   reference.ringbuffer.data(reference.ringbuffer.offset))
        np.testing.assert_allclose(channel.zf, reference.zf)
        np.testing.assert_allclose(channel.curve.y_array(), reference.curve.y_array())
        for actual, expected in zip(channel.subsampler.zfs, reference.subsampler.zfs):
            np.testing.assert_allclose(actual, expected)
        assert channel.level_rms == reference.level_rms
        assert channel.vertical_axis is panel.view_model().vertical_axis
    assert all(channel.curve.x_array() is channels[0].curve.x_array() for channel in channels)
    assert channels[1].level_rms - channels[0].level_rms == pytest.approx(20 * np.log10(5.))
    assert channels[2].level_rms == -1500.
    assert len({channel.ringbuffer for channel in channels}) == 3


def test_shared_settings_broadcast_persist_and_reset_response_dependent_history(levels_factory, tmp_path):
    panel, buffer = levels_factory((0, 3, 6))
    push(buffer, np.ones((3, 4096)))
    old = tuple(panel._channels.values())
    dialog = panel.settings_dialog
    dialog.spinBox_specmin.setValue(-90)
    dialog.spinBox_specmax.setValue(-10)
    dialog.spinBox_timemax.setValue(40)
    dialog.spinBox_resptime.setValue(2)
    assert panel.response_time == 2
    assert all(channel.ringbuffer.offset == 0 for channel in panel._channels.values())
    assert all(not np.any(channel.zf) for channel in panel._channels.values())
    settings = QSettings(str(tmp_path / "levels.ini"), QSettings.Format.IniFormat)
    panel.saveState(settings)
    restored, other_buffer = levels_factory((2, 5))
    restored.restoreState(settings)
    assert (restored.level_min, restored.level_max, restored.length_seconds, restored.response_time) == (-90, -10, 40, 2)
    assert len(restored.parent().findChildren(type(restored.settings_dialog))) == 1
    other_buffer.handle_configuration_changed(ChannelConfiguration(0, (1, 4, 8, 10), 11, 2))
    assert len(restored._channels) == 4
    assert all(channel.subsampler.Ndec == restored.Ndec for channel in restored._channels.values())
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert all(sip.isdeleted(channel) for channel in old)


def test_replacement_clears_all_histories_filter_tails_and_curves(levels_factory):
    panel, buffer = levels_factory((1, 4))
    push(buffer, np.ones((2, 8192)))
    previous = tuple(panel._channels.values())
    assert all(channel.ringbuffer.offset for channel in previous)
    buffer.handle_configuration_changed(ChannelConfiguration(0, (2, 7), 8, 2))
    assert panel.old_index == 0
    assert tuple(panel._channels) == (2, 7)
    for channel in panel._channels.values():
        assert channel.ringbuffer.offset == 0
        assert not np.any(channel.zf)
        assert all(not np.any(state) for state in channel.subsampler.zfs)
        assert channel.curve.y_array().size == 0
        assert channel.level_rms == -200.
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert all(sip.isdeleted(channel) and sip.isdeleted(channel.curve) for channel in previous)
    push(buffer, np.zeros((2, 4096)))
    assert all(not np.any(channel.zf) for channel in panel._channels.values())


def test_real_history_qml_uses_shared_axes_equal_rectangles_and_live_channels(levels_factory, qt_application):
    _register_qml_types()
    panel, buffer = levels_factory((0, 2, 4, 6, 8))
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("viewModel", panel.view_model())
    warnings = []
    engine.warnings.connect(warnings.extend)
    component = QQmlComponent(engine, qml_url(panel.qml_file_name()))
    assert component.status() == QQmlComponent.Status.Ready, [e.toString() for e in component.errors()]
    root = component.createWithInitialProperties({"width": 960., "height": 640., "configuredColumns": 3})
    assert root is not None
    try:
        settle(qt_application)
        assert_equal_data_geometry(root, 5)
        assert len(named_items(root, "channel-grid-x-scale-")) == 3
        assert len(named_items(root, "channel-grid-y-scale-")) == 2
        assert not named_items(root, "channel-grid-color-scale")
        push(buffer, np.ones((5, 4096)))
        buffer.handle_configuration_changed(ChannelConfiguration(0, (1, 7), 9, 2))
        settle(qt_application)
        assert_equal_data_geometry(root, 2)
        assert len(named_items(root, "channel-grid-cell-")) == 2
        assert not warnings, [warning.toString() for warning in warnings]
    finally:
        sip.delete(root)
        sip.delete(engine)
