#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2009 Timoth?Lecomte
# Copyright (C) 2026 Will Hirsch

# This file is part of Friture.
#
# Friture is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as published by
# the Free Software Foundation.
#
# Friture is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Friture.  If not, see <http://www.gnu.org/licenses/>.

from PyQt6.QtCore import QObject
from numpy import log10, argmax, zeros, arange, floor, float64

from polyfriture.audioproc import audioproc
from polyfriture.spectrum_settings import (
    Spectrum_Settings_Dialog, DEFAULT_FFT_SIZE, DEFAULT_FREQ_SCALE,
    DEFAULT_MAXFREQ, DEFAULT_MINFREQ, DEFAULT_SPEC_MIN, DEFAULT_SPEC_MAX,
    DEFAULT_WEIGHTING, DEFAULT_RESPONSE_TIME, DEFAULT_SHOW_FREQ_LABELS,
    DEFAULT_SHOW_PITCH_LABELS,
)
import polyfriture.plotting.frequency_scales as fscales
from polyfriture.audiobackend import SAMPLING_RATE
from polyfriture.scope_data import Scope_Data
from polyfriture.spectrumPlotWidget import SpectrumPlotWidget
from polyfriture.pitch_tracker import format_frequency
from polyfriture.signal.exp_smoothing import exp_smoothed_value_2d


class SpectrumChannel(QObject):
    """Mutable smoothing, peaks and annotations for one capture row."""

    def __init__(self, panel, label):
        super().__init__(panel)
        self.plot = SpectrumPlotWidget(self, axes=panel._grid_data)
        self.plot.view_model().label = label
        self.dispbuffer = zeros(len(panel.freq))
        self.plot.setShowFreqLabel(panel.show_frequency_labels)
        self.plot.setShowPitchLabel(panel.show_pitch_labels)
        self.plot.paused = panel.paused
        self.plot.reset()


class Spectrum_Widget(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.audiobuffer = None
        self._grid_data = Scope_Data(self)
        self._channels = {}
        self.paused = False
        self.old_index = 0
        self.overlap = 3. / 4.
        self.maxfreq = DEFAULT_MAXFREQ
        self.minfreq = DEFAULT_MINFREQ
        self.fft_size = 2 ** DEFAULT_FFT_SIZE * 32
        self.spec_min = DEFAULT_SPEC_MIN
        self.spec_max = DEFAULT_SPEC_MAX
        self.weighting = DEFAULT_WEIGHTING
        self.response_time = DEFAULT_RESPONSE_TIME
        self.show_frequency_labels = DEFAULT_SHOW_FREQ_LABELS
        self.show_pitch_labels = DEFAULT_SHOW_PITCH_LABELS

        # audioproc only caches the shared window, frequency bins and weights;
        # analyzelive does not retain samples or any channel history.
        self.proc = audioproc()
        self.proc.set_maxfreq(self.maxfreq)
        self.proc.set_fftsize(self.fft_size)
        self.freq = self.proc.get_freq_scale()
        self.update_weighting()
        self.setresponsetime(self.response_time)

        self._grid_data.vertical_axis.setTrackerFormatter(lambda x: "%.1f dB" % x)
        self._grid_data.horizontal_axis.name = "Frequency (Hz)"
        self._grid_data.horizontal_axis.setTrackerFormatter(format_frequency)
        self._grid_data.horizontal_axis.show_minor_grid_lines = True
        self.setfreqscale(fscales.ALL[DEFAULT_FREQ_SCALE])
        self._grid_data.horizontal_axis.setRange(self.minfreq, self.maxfreq)
        self._grid_data.vertical_axis.setRange(self.spec_min, self.spec_max)
        self.setweighting(self.weighting)
        self.settings_dialog = Spectrum_Settings_Dialog(parent, self)

    def qml_file_name(self):
        return "Spectrum.qml"

    def view_model(self):
        return self._grid_data

    def set_buffer(self, buffer):
        self.audiobuffer = buffer
        self.reset_channel_state(buffer.channel_configuration)

    def reset_channel_state(self, configuration):
        self.old_index = self.audiobuffer.ringbuffer.offset
        previous = self._channels
        self._channels = {} if configuration is None else {
            channel_id: SpectrumChannel(self, label)
            for channel_id, label in zip(configuration.channel_ids, configuration.channel_labels)
        }
        self._grid_data.set_channels([state.plot.view_model() for state in self._channels.values()])
        for state in previous.values():
            state.deleteLater()

    def log_spectrogram(self, sp):
        return 10. * log10(sp + 1e-30)

    def harmonic_product_spectrum(self, sp):
        harmonic_length = sp.shape[0] // 3
        return (sp[:harmonic_length] * sp[::2][:harmonic_length] * sp[::3][:harmonic_length])

    def handle_new_data(self, floatdata):
        if not self._channels:
            return
        index = self.audiobuffer.ringbuffer.offset
        available = index - self.old_index
        if available < 0:
            available = 0
            self.old_index = index
        needed = int(self.fft_size * (1. - self.overlap))
        realizable = int(floor(available / needed))
        if not realizable:
            return

        # Read each frame once; every channel uses identical FFT and hop timing.
        spectra = zeros((len(self._channels), len(self.freq), realizable), dtype=float64)
        for frame in range(realizable):
            samples = self.audiobuffer.data_indexed(self.old_index, self.fft_size)
            for row in range(len(self._channels)):
                spectra[row, :, frame] = self.proc.analyzelive(samples[row, :])
            self.old_index += needed
        for state, channel_spectra in zip(self._channels.values(), spectra):
            spectrum = exp_smoothed_value_2d(self.kernel, self.alpha, channel_spectra, state.dispbuffer)
            state.dispbuffer = spectrum
            levels = self.log_spectrogram(spectrum) + self.w
            fmax = self.freq[argmax(levels)]
            fpitch = max(self.freq[argmax(self.harmonic_product_spectrum(spectrum))], 1e-20)
            state.plot.setdata(self.freq, levels, fmax, fpitch)

    def canvasUpdate(self):
        for state in self._channels.values():
            state.plot.canvasUpdate()

    def pause(self):
        self.paused = True
        for state in self._channels.values():
            state.plot.pause()

    def restart(self):
        self.paused = False
        for state in self._channels.values():
            state.plot.restart()

    def setresponsetime(self, response_time):
        self.response_time = response_time
        n = response_time * SAMPLING_RATE / (self.fft_size * (1. - self.overlap))
        self.alpha = 1. - (1. - 0.65) ** (1. / (n + 1))
        self.kernel = (1. - self.alpha) ** arange(8191, -1, -1)

    def update_display_buffers(self):
        for state in self._channels.values():
            state.dispbuffer = zeros(len(self.freq))
            state.plot.reset()

    def setminfreq(self, minfreq):
        self.setMinMaxFreq(minfreq, self.maxfreq)

    def setmaxfreq(self, maxfreq):
        self.setMinMaxFreq(self.minfreq, maxfreq)

    def setMinMaxFreq(self, minfreq, maxfreq):
        self.minfreq, self.maxfreq = minfreq, maxfreq
        self.proc.set_maxfreq(max(minfreq, maxfreq))
        self.freq = self.proc.get_freq_scale()
        self.update_display_buffers()
        self.update_weighting()
        self.setresponsetime(self.response_time)
        self._grid_data.horizontal_axis.setRange(min(minfreq, maxfreq), max(minfreq, maxfreq))

    def setfreqscale(self, scale):
        self._grid_data.horizontal_axis.setScale(scale)

    def setfftsize(self, fft_size):
        self.fft_size = fft_size
        self.proc.set_fftsize(fft_size)
        self.freq = self.proc.get_freq_scale()
        self.update_display_buffers()
        self.update_weighting()
        self.setresponsetime(self.response_time)

    def setmin(self, value):
        self.spec_min = value
        self._grid_data.vertical_axis.setRange(min(self.spec_min, self.spec_max), max(self.spec_min, self.spec_max))

    def setmax(self, value):
        self.spec_max = value
        self._grid_data.vertical_axis.setRange(min(self.spec_min, self.spec_max), max(self.spec_min, self.spec_max))

    def setweighting(self, weighting):
        self.weighting = weighting
        suffix = ("", " A", " B", " C")[weighting]
        self._grid_data.vertical_axis.name = "PSD (dB%s)" % suffix
        self.update_weighting()

    def update_weighting(self):
        weights = self.proc.get_freq_weighting()
        self.w = zeros(weights[0].shape) if self.weighting == 0 else weights[self.weighting - 1]

    def setShowFreqLabel(self, show):
        self.show_frequency_labels = show
        for state in self._channels.values():
            state.plot.setShowFreqLabel(show)

    def setShowPitchLabel(self, show):
        self.show_pitch_labels = show
        for state in self._channels.values():
            state.plot.setShowPitchLabel(show)

    def settings_called(self, checked):
        self.settings_dialog.show()

    def saveState(self, settings):
        self.settings_dialog.saveState(settings)

    def restoreState(self, settings):
        self.settings_dialog.restoreState(settings)

    def cleanup(self):
        self._grid_data.set_channels([])
        self.settings_dialog.close()
        self.settings_dialog.deleteLater()
