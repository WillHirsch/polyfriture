"""Input identity changes clear analysis and display history without changing settings."""

from types import SimpleNamespace

import numpy as np
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QWidget

from polyfriture.audiobuffer import AudioBuffer
from polyfriture.channel_configuration import ChannelConfiguration
from polyfriture.dock import Dock
from polyfriture.generator import Generator_Widget
from polyfriture.levels import Levels_Widget
from polyfriture.longlevels import LongLevelWidget
from polyfriture.octavespectrum import OctaveSpectrum_Widget
from polyfriture.pitch_tracker import PitchTrackerWidget
from polyfriture.scope import Scope_Widget
from polyfriture.spectrogram import Spectrogram_Widget
from polyfriture.spectrum import Spectrum_Widget


@pytest.fixture
def panel_parent(qt_application):
    parent = QWidget()
    yield parent
    parent.deleteLater()


@pytest.fixture
def configured_buffer():
    buffer = AudioBuffer()
    buffer.handle_configuration_changed(ChannelConfiguration(0, (0, 1), 4, 1))
    return buffer


def replace_channels(buffer):
    # The row count is deliberately unchanged: shape alone cannot detect this.
    buffer.handle_configuration_changed(ChannelConfiguration(0, (2, 3), 4, 2))


def attach(panel, buffer):
    panel.set_buffer(buffer)
    buffer.configuration_changed.connect(panel.reset_channel_state)


def test_scope_clears_curves_on_same_count_replacement(panel_parent, configured_buffer):
    panel = Scope_Widget(panel_parent)
    attach(panel, configured_buffer)
    panel.set_timerange(600.)
    configured_buffer.ringbuffer.push(np.ones((2, 32)), 1.)
    panel.handle_new_data(np.ones((2, 32)))
    assert all(curve.y_array().size for curve in panel._curves.values())

    replace_channels(configured_buffer)

    assert tuple(panel._curves) == (2, 3)
    assert all(curve.x_array().size == 0 for curve in panel._curves.values())
    assert panel.timerange == 600.


def test_spectrum_clears_smoothing_peaks_and_labels_while_paused(panel_parent, configured_buffer):
    panel = Spectrum_Widget(panel_parent)
    attach(panel, configured_buffer)
    panel.setresponsetime(1.)
    configured_buffer.ringbuffer.push(np.ones((2, panel.fft_size * 2)), 1.)
    panel.handle_new_data(np.ones((2, panel.fft_size * 2)))
    previous = list(panel._channels.values())
    assert all(np.any(state.dispbuffer) for state in previous)
    assert all(state.plot.peak.size for state in previous)
    panel.pause()

    replace_channels(configured_buffer)

    assert panel.old_index == 0
    assert tuple(panel._channels) == (2, 3)
    for state in panel._channels.values():
        assert not np.any(state.dispbuffer)
        assert state.plot.peak.size == 0
        assert state.plot._curve_signal.y_array().size == 0
        assert state.plot.view_model().fmaxValue == ""
        assert state.plot.view_model().fpitchDisplayText == ""
        assert state.plot.paused
    assert panel.response_time == 1.


def test_octave_clears_filter_tails_smoothing_peaks_and_labels(panel_parent, configured_buffer):
    panel = OctaveSpectrum_Widget(panel_parent)
    attach(panel, configured_buffer)
    panel.setbandsperoctave(3)
    panel.handle_new_data(np.ones((2, 1024)))
    previous = list(panel._channels.values())
    assert all(np.any(state.dispbuffers) for state in previous)
    assert all(any(np.any(overlap) for overlap in state.filters._overlaps_oct) for state in previous)
    previous_labels = [label for state in previous for label in state.plot.view_model()._bar_labels]
    assert previous_labels
    panel.pause()

    replace_channels(configured_buffer)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    assert tuple(panel._channels) == (2, 3)
    assert all(sip.isdeleted(label) for label in previous_labels)
    for state in panel._channels.values():
        assert not np.any(state.dispbuffers)
        assert all(not np.any(overlap) for overlap in state.filters._overlaps_oct + state.filters._overlaps_dec)
        assert state.plot.peak.size == 0
        assert not state.plot.view_model()._bar_labels
        assert state.plot.paused
        assert state.filters.bandsperoctave == 3
    panel.handle_new_data(np.zeros((2, 1024)))
    assert all(not np.any(state.dispbuffers) for state in panel._channels.values())


def test_long_levels_clears_filter_and_history(panel_parent, configured_buffer):
    panel = LongLevelWidget(panel_parent)
    attach(panel, configured_buffer)
    panel.setduration(30.)
    panel.setresptime(0.5)
    configured_buffer.ringbuffer.push(np.ones((2, 2048)), 1.)
    panel.handle_new_data(np.ones((2, 2048)))
    previous = tuple(panel._channels.values())
    assert all(channel.ringbuffer.offset for channel in previous)
    assert all(np.any(channel.zf) for channel in previous)

    replace_channels(configured_buffer)

    assert panel.old_index == 0
    assert tuple(panel._channels) == (2, 3)
    for channel in panel._channels.values():
        assert channel.ringbuffer.offset == 0
        assert not np.any(channel.zf)
        assert all(not np.any(state) for state in channel.subsampler.zfs)
        assert channel.curve.y_array().size == 0
    assert panel.length_seconds == 30.
    assert panel.response_time == 0.5


def test_pitch_clears_estimates_continuity_and_display(panel_parent, configured_buffer):
    panel = PitchTrackerWidget(panel_parent)
    attach(panel, configured_buffer)
    panel.set_conf(0.75)
    previous = tuple(panel._channels.values())
    for channel in previous:
        channel.tracker.prev_f0 = 440.
        channel.tracker.out_buf.push(np.array([[440., 441.]]), 1.)
        channel.tracker.out_offset = 2
        channel.pitch = 441.
        panel.update_curve(channel)

    replace_channels(configured_buffer)

    assert tuple(panel._channels) == (2, 3)
    for channel in panel._channels.values():
        assert channel.tracker.next_in_offset == 0
        assert channel.tracker.prev_f0 is None
        assert channel.tracker.out_buf.offset == channel.tracker.out_offset == 0
        assert channel.curve.y_array().size == 0
        assert channel.pitch == "--"
        assert channel.tracker.conf == 0.75
    configured_buffer.handle_new_data(np.zeros((2, 4096)), 2., None, 2)
    panel.handle_new_data(np.zeros((2, 4096)))
    assert all(channel.tracker.out_offset == 1 for channel in panel._channels.values())


def test_spectrogram_clears_image_clock_and_resampler_while_paused(panel_parent, configured_buffer):
    panel = Spectrogram_Widget(panel_parent)
    attach(panel, configured_buffer)
    panel.timerangechanged(20.)
    previous = list(panel._channels.values())
    for channel in previous:
        channel.screen_resampler.set_height(3)
        channel.screen_resampler.push(np.ones((3, 8)))
        channel.image.push(np.full((3, 2), 0xFFFFFFFF, dtype=np.uint32), 12.)
    panel.pause()
    assert all(channel.image.canvasscaledspectrogram.write_offset for channel in previous)

    replace_channels(configured_buffer)

    assert panel.old_index == 0
    assert tuple(panel._channels) == (2, 3)
    for channel in panel._channels.values():
        assert channel not in previous
        assert channel.screen_resampler.orig_index == channel.screen_resampler.resampled_index == 0
        assert not np.any(channel.screen_resampler.old_data)
        assert not np.any(channel.screen_resampler.resampled_data)
        image_data = channel.image
        assert image_data.canvasscaledspectrogram.write_offset == 0
        assert image_data.last_data_time == image_data.canvasscaledspectrogram.last_write_time == 0.
        assert image_data.pixmap().toImage().pixelColor(0, 0).name() == "#000000"
        assert not image_data.is_playing
    assert panel.timerange_s == 20.


def test_meter_clears_rms_peak_hold_and_slow_labels(panel_parent, configured_buffer):
    panel = Levels_Widget(panel_parent)
    attach(panel, configured_buffer)
    panel.handle_new_data(np.ones((2, 1024)))
    previous = tuple(panel._channels.values())
    assert all(state.view.level_data_ballistic.peak_iec > 0. for state in previous)
    previous[0].view.level_data_slow.level_rms = -1.

    replace_channels(configured_buffer)

    assert tuple(panel._channels) == (2, 3)
    for state in panel._channels.values():
        assert state.old_rms == state.old_max == 1e-30
        assert state.view.level_data_ballistic.peak_iec == 0.
        assert state.view.level_data_slow.level_rms == -300.
    configured_buffer.handle_configuration_changed(ChannelConfiguration(0, (0,), 4, 3))
    assert tuple(panel._channels) == (0,)


def test_generator_input_reset_leaves_output_alone():
    # No generator constructor: the output stream must never be opened by tests.
    output = SimpleNamespace(state="playing", stream=object(), t=4.)
    before = vars(output).copy()
    Generator_Widget.reset_channel_state(output, ChannelConfiguration(0, (0,), 1, 1))
    assert vars(output) == before


def test_disposed_dock_disconnects_data_and_configuration(configured_buffer):
    calls = []
    panel = SimpleNamespace(
        handle_new_data=lambda data: calls.append("data"),
        reset_channel_state=lambda config: calls.append("reset"),
    )
    configured_buffer.new_data_available.connect(panel.handle_new_data)
    configured_buffer.configuration_changed.connect(panel.reset_channel_state)
    dock = SimpleNamespace(audiobuffer=configured_buffer, audiowidget=panel)

    Dock.disconnect_audio_widget(dock)
    replace_channels(configured_buffer)
    configured_buffer.new_data_available.emit(np.zeros((2, 1)))

    assert not calls
