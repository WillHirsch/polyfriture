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

"""One synchronized time-frequency history per captured channel."""

from fractions import Fraction

import numpy as np
from PyQt6.QtCore import QObject

from polyfriture.audiobackend import SAMPLING_RATE, FRAMES_PER_BUFFER, AudioBackend
from polyfriture.audiobuffer import AudioBuffer
from polyfriture.audioproc import audioproc
from polyfriture.imageplot import ImagePlot
import polyfriture.plotting.frequency_scales as fscales
from polyfriture.signal.color_tranform import Color_Transform
from polyfriture.signal.frequency_resampler import Frequency_Resampler
from polyfriture.signal.online_linear_2D_resampler import Online_Linear_2D_resampler
from polyfriture.signal.transform_pipeline import Transform_Pipeline
from polyfriture.spectrogram_settings import (
    Spectrogram_Settings_Dialog, DEFAULT_FFT_SIZE, DEFAULT_FREQ_SCALE,
    DEFAULT_MAXFREQ, DEFAULT_MINFREQ, DEFAULT_SPEC_MIN, DEFAULT_SPEC_MAX,
    DEFAULT_TIMERANGE, DEFAULT_WEIGHTING,
)


class SpectrogramChannel:
    """The mutable resampling and image history belonging to one input row."""

    def __init__(self, image, panel):
        self.image = image
        self.frequency_resampler = Frequency_Resampler(
            panel.freqscale, panel.minfreq, panel.maxfreq)
        self.frequency_resampler.setfreq(panel.freq)
        self.screen_resampler = Online_Linear_2D_resampler()
        self.audio_pipeline = Transform_Pipeline([
            self.frequency_resampler,
            self.screen_resampler,
            Color_Transform(),
        ])

    def reset(self):
        self.screen_resampler.reset()
        self.image.reset()


class Spectrogram_Widget(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.PlotZoneImage = ImagePlot(self)
        self.audiobuffer = None
        self._channels = {}
        self.old_index = 0
        self.mustRestart = False
        self.overlap_frac = Fraction(3, 4)
        self.overlap = float(self.overlap_frac)
        self.proc = audioproc()
        self.minfreq = DEFAULT_MINFREQ
        self.maxfreq = DEFAULT_MAXFREQ
        self.fft_size = 2 ** (DEFAULT_FFT_SIZE + 5)
        self.spec_min = DEFAULT_SPEC_MIN
        self.spec_max = DEFAULT_SPEC_MAX
        self.weighting = DEFAULT_WEIGHTING
        self.timerange_s = DEFAULT_TIMERANGE
        self.freqscale = fscales.ALL[DEFAULT_FREQ_SCALE]
        self.proc.set_maxfreq(self.maxfreq)
        self.proc.set_fftsize(self.fft_size)
        self._update_fft_parameters()
        self.PlotZoneImage.setfreqrange(self.minfreq, self.maxfreq)
        self.PlotZoneImage.setspecrange(self.spec_min, self.spec_max)
        self.PlotZoneImage.setweighting(self.weighting)
        self.PlotZoneImage.setfreqscale(self.freqscale)
        self.settings_dialog = Spectrogram_Settings_Dialog(parent, self)

    def qml_file_name(self):
        return self.PlotZoneImage.qml_file_name()

    def view_model(self):
        return self.PlotZoneImage.view_model()

    def set_buffer(self, buffer: AudioBuffer) -> None:
        self.audiobuffer = buffer
        self.reset_channel_state(buffer.channel_configuration)

    def reset_channel_state(self, configuration) -> None:
        self.old_index = self.audiobuffer.ringbuffer.offset
        images = self.PlotZoneImage.set_channels(configuration)
        self._channels = {} if configuration is None else {
            channel_id: SpectrogramChannel(image, self)
            for channel_id, image in zip(configuration.channel_ids, images)
        }

    def _clear_history(self):
        """Never mix pixels made with different analysis/display parameters.

        The raster is the history cache; raw FFT history is not retained. A
        settings change therefore starts fresh at the current audio cursor.
        Geometry-only changes are handled by scaling the existing raster.
        """
        if self.audiobuffer is not None:
            self.old_index = self.audiobuffer.ringbuffer.offset
        for channel in self._channels.values():
            channel.reset()

    def log_spectrogram(self, spectrum):
        return 10. * np.log10(spectrum + 1e-30)

    def scale_spectrogram(self, spectrum):
        return (spectrum - self.spec_min) / (self.spec_max - self.spec_min)

    def handle_new_data(self, floatdata: np.ndarray) -> None:
        if not self._channels:
            return
        index = self.audiobuffer.ringbuffer.offset
        available = index - self.old_index
        if available < 0:
            self._clear_history()
            return
        hop = self.fft_size // 4
        realizable = available // hop
        if realizable == 0:
            return

        spectra = np.zeros((len(self._channels), len(self.freq), realizable))
        for frame in range(realizable):
            samples = self.audiobuffer.data_indexed(self.old_index, self.fft_size)
            data_time = self.audiobuffer.data_time(self.old_index)
            for row in range(len(self._channels)):
                spectra[row, :, frame] = self.proc.analyzelive(samples[row])
            # All channels consume exactly the same audio windows and clocks.
            self.old_index += hop

        for channel, spectrum in zip(self._channels.values(), spectra):
            image = channel.image
            height = image.screen_height()
            channel.screen_resampler.set_height(height)
            screen_rate = Fraction(image.screen_width(), 1) / Fraction(str(self.timerange_s * 1000))
            channel.screen_resampler.set_ratio(self.sfft_rate_frac, screen_rate)
            channel.frequency_resampler.setnsamples(height)
            normalized = self.scale_spectrogram(self.log_spectrogram(spectrum) + self.w)
            image.push(channel.audio_pipeline.push(normalized), data_time)

        if self.mustRestart:
            self.PlotZoneImage.restart()
            self.mustRestart = False

    def canvasUpdate(self):
        # Read the stream clock once, rather than once per asynchronously
        # painted cell. Paused images retain their previous display clock.
        if self._channels and not self.PlotZoneImage.paused:
            self.PlotZoneImage.draw(AudioBackend().get_stream_time())

    def cleanup(self):
        self.PlotZoneImage.set_channels(None)
        self._channels.clear()
        self.audiobuffer = None
        self.settings_dialog.close()
        self.settings_dialog.deleteLater()

    def update_jitter(self):
        audio_jitter = 2 * float(FRAMES_PER_BUFFER) / SAMPLING_RATE
        self.PlotZoneImage.set_jitter(audio_jitter + self.dT_s)

    def pause(self):
        self.PlotZoneImage.pause()

    def restart(self):
        # Keep frozen until new audio has supplied a fresh shared timestamp.
        self.mustRestart = True

    def setminfreq(self, freq):
        if freq == self.minfreq:
            return
        self.minfreq = freq
        self._update_frequency_range()

    def setmaxfreq(self, freq):
        if freq == self.maxfreq:
            return
        self.maxfreq = freq
        self.proc.set_maxfreq(freq)
        self._update_frequency_range()

    def _update_frequency_range(self):
        self.PlotZoneImage.setfreqrange(self.minfreq, self.maxfreq)
        self.update_weighting()
        self.freq = self.proc.get_freq_scale()
        for channel in self._channels.values():
            channel.frequency_resampler.setfreqrange(self.minfreq, self.maxfreq)
            channel.frequency_resampler.setfreq(self.freq)
        self._clear_history()

    def setfreqscale(self, freqscale):
        if freqscale == self.freqscale:
            return
        self.freqscale = freqscale
        self.PlotZoneImage.setfreqscale(freqscale)
        for channel in self._channels.values():
            channel.frequency_resampler.setfreqscale(freqscale)
        self._clear_history()

    def _update_fft_parameters(self):
        self.update_weighting()
        self.freq = self.proc.get_freq_scale()
        self.dT_s = self.fft_size * (1. - self.overlap) / float(SAMPLING_RATE)
        self.sfft_rate_frac = Fraction(SAMPLING_RATE, self.fft_size) / (1 - self.overlap_frac) / 1000
        self.PlotZoneImage.settimerange(self.timerange_s, self.dT_s)
        for channel in self._channels.values():
            channel.frequency_resampler.setfreq(self.freq)
        self.update_jitter()

    def setfftsize(self, fft_size):
        if fft_size == self.fft_size:
            return
        self.fft_size = fft_size
        self.proc.set_fftsize(fft_size)
        self._update_fft_parameters()
        self._clear_history()

    def setmin(self, value):
        if value == self.spec_min:
            return
        self.spec_min = value
        self.PlotZoneImage.setspecrange(self.spec_min, self.spec_max)
        self._clear_history()

    def setmax(self, value):
        if value == self.spec_max:
            return
        self.spec_max = value
        self.PlotZoneImage.setspecrange(self.spec_min, self.spec_max)
        self._clear_history()

    def setweighting(self, weighting):
        if weighting == self.weighting:
            return
        self.weighting = weighting
        self.PlotZoneImage.setweighting(weighting)
        self.update_weighting()
        self._clear_history()

    def update_weighting(self):
        weightings = (np.array([0.]), *self.proc.get_freq_weighting())
        self.w = weightings[self.weighting].reshape((-1, 1))

    def settings_called(self, checked):
        self.settings_dialog.show()

    def saveState(self, settings):
        self.settings_dialog.saveState(settings)

    def restoreState(self, settings):
        self.settings_dialog.restoreState(settings)

    def timerangechanged(self, value):
        if value == self.timerange_s:
            return
        self.timerange_s = value
        self.PlotZoneImage.settimerange(self.timerange_s, self.dT_s)
        self._clear_history()
