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
from polyfriture.level_view_model import LevelViewModel
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
    assert np.any(panel.dispbuffer)
    assert panel.PlotZoneSpect.peak.size
    panel.pause()

    replace_channels(configured_buffer)

    assert panel.old_index == 0
    assert not np.any(panel.dispbuffer)
    assert panel.PlotZoneSpect.peak.size == 0
    assert panel.PlotZoneSpect._curve_signal.y_array().size == 0
    assert panel.PlotZoneSpect.view_model().fmaxValue == ""
    assert panel.PlotZoneSpect.view_model().fpitchDisplayText == ""
    assert panel.PlotZoneSpect.paused
    assert panel.response_time == 1.


def test_octave_clears_filter_tails_smoothing_peaks_and_labels(panel_parent, configured_buffer):
    panel = OctaveSpectrum_Widget(panel_parent)
    attach(panel, configured_buffer)
    panel.setbandsperoctave(3)
    panel.handle_new_data(np.ones((2, 1024)))
    assert np.any(panel.dispbuffers)
    assert any(np.any(state) for state in panel.filters._overlaps_oct)
    previous_labels = tuple(panel.PlotZoneSpect.view_model()._bar_labels)
    assert previous_labels
    panel.PlotZoneSpect.pause()

    replace_channels(configured_buffer)

    assert not np.any(panel.dispbuffers)
    assert all(not np.any(state) for state in panel.filters._overlaps_oct + panel.filters._overlaps_dec)
    assert panel.PlotZoneSpect.peak.size == 0
    assert not panel.PlotZoneSpect.view_model()._bar_labels
    for label in previous_labels:
        QCoreApplication.sendPostedEvents(label, QEvent.Type.DeferredDelete)
        assert sip.isdeleted(label)
    assert panel.PlotZoneSpect.paused
    assert panel.filters.bandsperoctave == 3
    panel.handle_new_data(np.zeros((2, 1024)))
    assert not np.any(panel.dispbuffers)


def test_long_levels_clears_filter_and_history(panel_parent, configured_buffer):
    panel = LongLevelWidget(panel_parent)
    attach(panel, configured_buffer)
    panel.setduration(30.)
    panel.setresptime(0.5)
    configured_buffer.ringbuffer.push(np.ones((2, 2048)), 1.)
    panel.handle_new_data(np.ones((2, 2048)))
    assert panel.ringbuffer.offset
    assert np.any(panel.zf)

    replace_channels(configured_buffer)

    assert panel.old_index == panel.ringbuffer.offset == 0
    assert not np.any(panel.zf)
    assert all(not np.any(state) for state in panel.subsampler.zfs)
    assert panel._curve.y_array().size == 0
    assert panel.length_seconds == 30.
    assert panel.response_time == 0.5


def test_pitch_clears_estimates_continuity_and_display(panel_parent, configured_buffer):
    panel = PitchTrackerWidget(panel_parent)
    attach(panel, configured_buffer)
    panel.tracker.prev_f0 = 440.
    panel.tracker.out_buf.push(np.array([[440., 441.]]), 1.)
    panel.tracker.out_offset = 2
    panel._pitch_tracker_data.pitch = 441.
    panel.tracker.conf = 0.75
    panel.update_curve()

    replace_channels(configured_buffer)

    assert panel.tracker.next_in_offset == 0
    assert panel.tracker.prev_f0 is None
    assert panel.tracker.out_buf.offset == panel.tracker.out_offset == 0
    assert panel._curve.y_array().size == 0
    assert panel._pitch_tracker_data.pitch == "--"
    assert panel.tracker.conf == 0.75
    configured_buffer.ringbuffer.push(np.zeros((2, panel.tracker.fft_size)), 2.)
    assert len(list(panel.tracker.new_frames())) == 1


def test_spectrogram_clears_image_clock_and_resampler_while_paused(panel_parent, configured_buffer):
    panel = Spectrogram_Widget(panel_parent)
    attach(panel, configured_buffer)
    panel.timerangechanged(20.)
    panel.screen_resampler.set_height(3)
    panel.screen_resampler.push(np.ones((3, 8)))
    panel.PlotZoneImage.push(np.full((3, 2), 0xFFFFFFFF, dtype=np.uint32), 12.)
    panel.pause()
    image_data = panel.PlotZoneImage._spectrogram_item
    assert image_data.canvasscaledspectrogram.write_offset

    replace_channels(configured_buffer)

    assert panel.old_index == 0
    assert panel.screen_resampler.orig_index == panel.screen_resampler.resampled_index == 0
    assert not np.any(panel.screen_resampler.old_data)
    assert not np.any(panel.screen_resampler.resampled_data)
    assert image_data.canvasscaledspectrogram.write_offset == 0
    assert image_data.last_data_time == image_data.canvasscaledspectrogram.last_write_time == 0.
    assert image_data.pixmap().toImage().pixelColor(0, 0).name() == "#000000"
    assert not image_data.is_playing
    assert panel.timerange_s == 20.


def test_meter_clears_rms_peak_hold_and_slow_labels(panel_parent, configured_buffer):
    view_model = LevelViewModel()
    panel = Levels_Widget(panel_parent, view_model)
    attach(panel, configured_buffer)
    panel.handle_new_data(np.ones((2, 1024)))
    view_model.level_data_slow.level_rms = -1.
    view_model.level_data_slow_2.level_rms = -2.
    assert view_model.level_data_ballistic.peak_iec > 0.

    replace_channels(configured_buffer)

    assert panel.old_rms == panel.old_rms_2 == panel.old_max == panel.old_max_2 == 1e-30
    assert view_model.level_data_ballistic.peak_iec == view_model.level_data_ballistic_2.peak_iec == 0.
    assert view_model.level_data_slow.level_rms == view_model.level_data_slow_2.level_rms == -300.
    assert view_model.two_channels
    configured_buffer.handle_configuration_changed(ChannelConfiguration(0, (0,), 4, 3))
    assert not view_model.two_channels


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
