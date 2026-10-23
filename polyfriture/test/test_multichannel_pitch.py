"""Channel-isolated SWIPE histories, shared settings and real QML layout."""

import numpy as np
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QSettings
from PyQt6.QtQml import QQmlComponent, QQmlEngine
from PyQt6.QtWidgets import QWidget

from polyfriture.audiobackend import SAMPLING_RATE
from polyfriture.audiobuffer import AudioBuffer
from polyfriture.channel_configuration import ChannelConfiguration
from polyfriture.pitch_tracker import PitchTrackerWidget
from polyfriture.qml_tools import qml_url
from polyfriture.test.test_channel_grid import assert_equal_data_geometry, named_item, named_items, settle
from polyfriture.test.test_qml_integration import _register_qml_types


@pytest.fixture
def pitch_factory(qt_application):
    parents = []
    def create(ids):
        parent = QWidget()
        parents.append(parent)
        panel = PitchTrackerWidget(parent)
        buffer = AudioBuffer()
        buffer.handle_configuration_changed(ChannelConfiguration(0, ids, max(ids) + 1, 1))
        panel.set_buffer(buffer)
        buffer.configuration_changed.connect(panel.reset_channel_state)
        buffer.new_data_available.connect(panel.handle_new_data)
        return panel, buffer
    yield create
    for parent in parents:
        for panel in parent.findChildren(PitchTrackerWidget):
            panel.cleanup()
        sip.delete(parent)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def voiced(frequency, count=8192, amplitude=0.3):
    phase = 2 * np.pi * frequency * np.arange(count) / SAMPLING_RATE
    return amplitude * (np.sin(phase) + 0.7 * np.sin(2 * phase) + 0.4 * np.sin(3 * phase))


def push(buffer, data):
    buffer.handle_new_data(data, 1., None, buffer.channel_configuration.generation)


def test_every_channel_matches_independent_mono_analysis_and_history(pitch_factory):
    panel, buffer = pitch_factory((1, 4, 7))
    samples = np.array([voiced(220.), voiced(440.), voiced(659.25)])
    push(buffer, samples)
    channels = list(panel._channels.values())
    assert [channel.label for channel in channels] == ["Channel 2", "Channel 5", "Channel 8"]
    for row, channel in enumerate(channels):
        mono, mono_buffer = pitch_factory((0,))
        push(mono_buffer, samples[row:row + 1])
        reference = mono._channels[0]
        np.testing.assert_allclose(channel.tracker.out_buf.data(channel.tracker.out_offset),
                                   reference.tracker.out_buf.data(reference.tracker.out_offset), equal_nan=True)
        np.testing.assert_allclose(channel.curve.y_array(), reference.curve.y_array(), equal_nan=True)
        assert channel.pitch == reference.pitch
        assert channel.note == reference.note
        assert channel.tracker.prev_f0 == reference.tracker.prev_f0
    assert len({channel.tracker.input_buf for channel in channels}) == 3
    assert len({channel.tracker.out_buf for channel in channels}) == 3
    assert all(channel.vertical_axis is panel.view_model().vertical_axis for channel in channels)


def test_loud_neighbour_cannot_make_quiet_channel_voiced(pitch_factory):
    panel, buffer = pitch_factory((2, 8, 11))
    push(buffer, np.array([voiced(220., amplitude=0.00001), voiced(440.), np.zeros(8192)]))
    quiet, loud, silent = panel._channels.values()
    assert quiet.pitch == silent.pitch == "--"
    assert quiet.tracker.prev_f0 is silent.tracker.prev_f0 is None
    assert np.isnan(quiet.tracker.get_latest_estimate())
    assert np.isnan(silent.tracker.get_latest_estimate())
    assert np.isfinite(loud.tracker.get_latest_estimate())


def test_shared_settings_are_broadcast_persisted_and_used_for_later_channels(pitch_factory, tmp_path):
    panel, buffer = pitch_factory((0, 3))
    dialog = panel.settings_dialog
    dialog.min_freq.setValue(100)
    dialog.max_freq.setValue(900)
    dialog.duration.setValue(25)
    dialog.min_db.setValue(-35.)
    dialog.conf.setValue(0.7)
    settings = QSettings(str(tmp_path / "pitch.ini"), QSettings.Format.IniFormat)
    panel.saveState(settings)
    restored, other_buffer = pitch_factory((1, 4, 8))
    restored.restoreState(settings)
    for candidate in (panel, restored):
        assert candidate.duration == 25
        for channel in candidate._channels.values():
            assert (channel.tracker.min_freq, channel.tracker.max_freq) == (100, 900)
            assert (channel.tracker.min_db, channel.tracker.conf) == (-35., 0.7)
            assert channel.vertical_axis is candidate.view_model().vertical_axis
    other_buffer.handle_configuration_changed(ChannelConfiguration(0, (2, 5, 9, 12), 13, 2))
    assert len(restored._channels) == 4
    assert all(channel.tracker.conf == 0.7 for channel in restored._channels.values())
    assert len(restored.findChildren(type(restored.settings_dialog))) == 0  # dialog belongs to panel's host
    assert len(restored.parent().findChildren(type(restored.settings_dialog))) == 1


def test_generation_replacement_drops_history_continuity_and_qobjects(pitch_factory):
    panel, buffer = pitch_factory((1, 4))
    push(buffer, np.array([voiced(220.), voiced(440.)]))
    old = tuple(panel._channels.values())
    assert all(channel.tracker.out_offset for channel in old)
    buffer.handle_configuration_changed(ChannelConfiguration(0, (2, 7), 8, 2))
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert all(sip.isdeleted(channel) and sip.isdeleted(channel.curve) for channel in old)
    assert tuple(panel._channels) == (2, 7)
    for channel in panel._channels.values():
        assert channel.tracker.prev_f0 is None
        assert channel.tracker.next_in_offset == channel.tracker.out_offset == 0
        assert channel.pitch == channel.note == "--"
        assert channel.curve.y_array().size == 0
    push(buffer, np.zeros((2, 4096)))
    assert all(channel.pitch == "--" for channel in panel._channels.values())


def test_pitch_readouts_keep_equal_grid_geometry_and_replace_live(pitch_factory, qt_application):
    _register_qml_types()
    panel, buffer = pitch_factory((0, 2, 4, 6, 8))
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
        before = [(item.width(), item.height()) for item in assert_equal_data_geometry(root, 5)]
        for index, channel in enumerate(panel._channels.values()):
            channel.pitch = [65.4, 440., 1046.5, 12345.6, np.nan][index]
            channel.label = "Long channel label " * (index + 1)
        settle(qt_application)
        assert [(item.width(), item.height()) for item in assert_equal_data_geometry(root, 5)] == before
        assert len(named_items(root, "channel-grid-x-scale-")) == 3
        assert len(named_items(root, "channel-grid-y-scale-")) == 2
        assert not named_items(root, "channel-grid-color-scale")
        for index in range(5):
            assert named_item(root, f"pitch-channel-header-{index}").property("text")
        buffer.handle_configuration_changed(ChannelConfiguration(0, (3, 7), 9, 2))
        settle(qt_application)
        assert_equal_data_geometry(root, 2)
        assert len(named_items(root, "pitch-channel-header-")) == 2
        assert not warnings, [warning.toString() for warning in warnings]
    finally:
        sip.delete(root)
        sip.delete(engine)
