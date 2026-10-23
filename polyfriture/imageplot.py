#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2009 Timothée Lecomte
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

import logging
from PyQt6.QtCore import QObject
from polyfriture.spectrogram_data import Spectrogram_Data
from polyfriture.spectrogram_item_data import SpectrogramImageData
from polyfriture.scope_data import Scope_Data
from polyfriture.pitch_tracker import format_frequency
import polyfriture.plotting.frequency_scales as fscales

class ImagePlot(QObject):

    def __init__(self, parent):
        super(ImagePlot, self).__init__(parent)

        self.logger = logging.getLogger(__name__)

        self._spectrogram_data = Spectrogram_Data(self)
        self._spectrogram_items = []
        self._channels = []
        self.timerange = 10.
        self.jitter_seconds = 0.
        self.paused = False
        self.frequency_range = (20, 20000)
        self.frequency_scale = fscales.Linear

        self._spectrogram_data.show_legend = False
        self._spectrogram_data.color_axis.name = "PSD (dB A)"

        self._update_axes()
        self._spectrogram_data.color_axis.setRange(-140, 0)
        self._spectrogram_data.show_color_axis = True

    def qml_file_name(self):
        return "ImagePlot.qml"
    
    def view_model(self):
        return self._spectrogram_data

    def set_channels(self, configuration):
        channels = []
        images = []
        if configuration is not None:
            for label in configuration.channel_labels:
                channel = Scope_Data(self._spectrogram_data, axes=self._spectrogram_data)
                channel.label = label
                image = SpectrogramImageData()
                image.settimerange(self.timerange)
                image.set_jitter(self.jitter_seconds)
                if self.paused:
                    image.pause()
                channel.add_plot_item(image)
                channels.append(channel)
                images.append(image)
        self._spectrogram_items = images
        previous = self._channels
        self._channels = channels
        self._spectrogram_data.set_channels(channels)
        for channel in previous:
            channel.deleteLater()
        return images

    def reset(self):
        for image in self._spectrogram_items:
            image.reset()

    def draw(self, paint_time):
        for image in self._spectrogram_items:
            image.draw(paint_time)

    def pause(self):
        self.paused = True
        for image in self._spectrogram_items:
            image.pause()

    def restart(self):
        self.paused = False
        for image in self._spectrogram_items:
            image.restart()

    def set_jitter(self, jitter_seconds: float) -> None:
        self.jitter_seconds = jitter_seconds
        for image in self._spectrogram_items:
            image.set_jitter(jitter_seconds)

    def setfreqscale(self, scale):        
        self.frequency_scale = scale
        self._update_axes()

    def setrotated(self, rotated):
        if rotated != self._spectrogram_data.rotated:
            self._update_axes(rotated)
            self._spectrogram_data.rotated = rotated

    def _update_axes(self, rotated=None):
        # Retain logical frequency/time parameters independently of their
        # current physical axis. Both scales and tracker transforms follow the
        # clockwise image rotation; the vertical time range runs downward.
        if rotated is None:
            rotated = self._spectrogram_data.rotated
        horizontal = self._spectrogram_data.horizontal_axis
        vertical = self._spectrogram_data.vertical_axis
        frequency_axis, time_axis = (horizontal, vertical) if rotated else (vertical, horizontal)
        frequency_axis.name = "Frequency (Hz)"
        frequency_axis.setTrackerFormatter(format_frequency)
        frequency_axis.setScale(self.frequency_scale)
        frequency_axis.setRange(*self.frequency_range)
        time_axis.name = "Time (s)"
        time_axis.setTrackerFormatter(lambda x: "%.2f s" % x)
        time_axis.setScale(fscales.Linear)
        time_range = (self.timerange, 0.) if rotated else (0., self.timerange)
        time_axis.setRange(*time_range)

    def settimerange(self, timerange_seconds, dT_seconds):
        self.timerange = timerange_seconds
        self._update_axes()
        for image in self._spectrogram_items:
            image.settimerange(timerange_seconds)
            image.set_jitter(self.jitter_seconds)

    def setfreqrange(self, minfreq, maxfreq):
        if minfreq > maxfreq:
            minfreq, maxfreq = maxfreq, minfreq

        self.frequency_range = (minfreq, maxfreq)
        self._update_axes()

    def setspecrange(self, spec_min, spec_max):
        if spec_min > spec_max:
            spec_min, spec_max = spec_max, spec_min

        self._spectrogram_data.color_axis.setRange(spec_min, spec_max)

    def setweighting(self, weighting):
        if weighting == 0:
            title = "PSD (dB)"
        elif weighting == 1:
            title = "PSD (dB A)"
        elif weighting == 2:
            title = "PSD (dB B)"
        else:
            title = "PSD (dB C)"

        self._spectrogram_data.color_axis.name = title
