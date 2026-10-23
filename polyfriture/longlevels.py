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

"""Level widget that displays RMS level history."""


import logging
from PyQt6.QtCore import QObject
import numpy as np
from polyfriture.longlevels_settings import (LongLevels_Settings_Dialog,
                                         DEFAULT_LEVEL_MIN,
                                         DEFAULT_LEVEL_MAX,
                                         DEFAULT_MAXTIME,
                                         DEFAULT_RESPONSE_TIME)
from .signal.decimate import decimate
from .ringbuffer import RingBuffer
from polyfriture.signal.lfilter import lfilter_float64_1D
from polyfriture.scope_data import Scope_Data
from polyfriture.curve import Curve

from polyfriture.audiobackend import SAMPLING_RATE

# signal > square > low-pass filter > filter for screen > log

SMOOTH_DISPLAY_TIMER_PERIOD_MS = 25
LEVEL_TEXT_LABEL_PERIOD_MS = 1000

LEVEL_TEXT_LABEL_STEPS = LEVEL_TEXT_LABEL_PERIOD_MS / SMOOTH_DISPLAY_TIMER_PERIOD_MS


def gauss(n=11, sigma=1):
    r = range(-int(n/2), int(n/2)+1)
    return [1 / (sigma * np.sqrt(2*np.pi)) * np.exp(-float(x)**2/(2*sigma**2)) for x in r]


class Subsampler:
    def __init__(self, Ndec):
        self.Ndec = Ndec

        # to maintain non-negativeness of the subsampled signal, we use a gaussian filter here
        # (IIR ringing produces negative values)
        #[self.bdec, self.adec] = generated_filters.PARAMS['dec']
        self.bdec = np.array(gauss(11, 2.))
        self.adec = np.zeros(self.bdec.shape)
        self.adec[0] = 1.

        # build a proper array of zero initial conditions to start the subsampler
        self.zfs = []
        for i in range(self.Ndec):
            l = max(len(self.bdec), len(self.adec)) - 1
            self.zfs += [np.zeros(l)]

    def push(self, x):
        # FIXME problems when x is smaller than filter coeff

        # do not run on empty arrays, otherwise bad artefacts on the output !!
        if x.size == 0:
            return x

        x_dec = x

        # if we do not have enough samples, we need to buffer until we have enough
        # we need 2**self.Ndec samples in input for one in output

        zfs = []
        for i, zi in zip(list(range(self.Ndec)), self.zfs):
            x_dec, zf = decimate(self.bdec, self.adec, x_dec, zi=zi)
            # zf can be reused to restart the filter
            zfs.append(zf)

        self.zfs = zfs

        return x_dec


class LongLevelChannel(Scope_Data):
    """Independent filter memory and level history for one capture row."""

    def __init__(self, parent, axes, label, decimations, filter_length):
        super().__init__(parent, axes=axes)
        self.label = label
        self.curve = Curve()
        self.curve.name = label
        self.curve.setData(np.zeros(0), np.zeros(0))
        self.add_plot_item(self.curve)
        self.subsampler = Subsampler(decimations)
        self.zf = np.zeros(filter_length - 1)
        self.ringbuffer = RingBuffer()
        self.level_rms = -200.

    def process(self, samples, numerator, denominator):
        squared = self.subsampler.push(samples ** 2)
        levels, self.zf = lfilter_float64_1D(numerator, denominator, squared, self.zf)
        levels_db = 10. * np.log10(np.maximum(levels, 1e-150))
        self.level_rms = float(levels_db[-1])
        self.ringbuffer.push(levels_db.reshape(1, -1), 0.)


class LongLevelWidget(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self._long_levels_data = Scope_Data(self)
        self._long_levels_data.vertical_axis.name = "Level (dB FS RMS)"
        self._long_levels_data.vertical_axis.setTrackerFormatter(lambda x: "%#.3g dB" % x)
        self._long_levels_data.horizontal_axis.name = "Time (sec)"
        self._long_levels_data.horizontal_axis.setTrackerFormatter(lambda x: "%#.3g sec" % x)
        self.level_min = DEFAULT_LEVEL_MIN
        self.level_max = DEFAULT_LEVEL_MAX
        self._long_levels_data.vertical_axis.setRange(self.level_min, self.level_max)
        self.audiobuffer = None
        self._channels = {}
        self.old_index = 0
        self.length_seconds = DEFAULT_MAXTIME
        self.setresptime(DEFAULT_RESPONSE_TIME)
        self.settings_dialog = LongLevels_Settings_Dialog(parent, self)

    def qml_file_name(self):
        return "LongLevels.qml"

    def view_model(self):
        return self._long_levels_data

    def set_buffer(self, buffer):
        self.audiobuffer = buffer
        self.reset_channel_state(buffer.channel_configuration)

    def reset_channel_state(self, configuration):
        previous = self._channels
        self._channels = {}
        if configuration is not None:
            for channel_id, label in zip(configuration.channel_ids, configuration.channel_labels):
                self._channels[channel_id] = LongLevelChannel(
                    self, self._long_levels_data, label, self.Ndec, len(self.b))
        self.old_index = self.audiobuffer.ringbuffer.offset if self.audiobuffer is not None else 0
        self._long_levels_data.set_channels(self._channels.values())
        for channel in previous.values():
            channel.deleteLater()

    def handle_new_data(self, floatdata):
        if self.audiobuffer is None or not self._channels:
            return
        index = self.audiobuffer.ringbuffer.offset
        available = index - self.old_index
        if available < 0:
            self.reset_channel_state(self.audiobuffer.channel_configuration)
            return
        needed = 2 ** self.Ndec
        realizable = available // needed
        for _ in range(realizable):
            # Keep the existing history alignment for every capture row.
            end = self.old_index + needed
            samples = self.audiobuffer.data_indexed(self.old_index, needed)
            for row, channel in enumerate(self._channels.values()):
                channel.process(samples[row], self.b, self.a)
            self.old_index = end
        if realizable:
            self.update_curves()

    def update_curves(self):
        time = np.arange(self.length_samples) / self.subsampled_sampling_rate
        scaled_t = time / self.length_seconds
        for channel in self._channels.values():
            if not channel.ringbuffer.offset:
                continue
            levels = channel.ringbuffer.data(self.length_samples)[0]
            scaled_y = np.clip(1. - (levels - self.level_min) /
                               (self.level_max - self.level_min), 0., 1.)
            channel.curve.setData(scaled_t, scaled_y)

    def canvasUpdate(self):
        pass

    def setmin(self, value):
        self.level_min = value
        self._long_levels_data.vertical_axis.setRange(self.level_min, self.level_max)
        self.update_curves()

    def setmax(self, value):
        self.level_max = value
        self._long_levels_data.vertical_axis.setRange(self.level_min, self.level_max)
        self.update_curves()

    def setduration(self, value):
        self.length_seconds = value
        self.length_samples = int(self.length_seconds * self.subsampled_sampling_rate)
        self._long_levels_data.horizontal_axis.setRange(0., self.length_seconds)
        self.update_curves()

    def setresptime(self, value):
        self.response_time = value
        self.Ndec = int(max(0, np.floor(np.log2(self.response_time * SAMPLING_RATE / 100.))))
        self.b = np.array(gauss(41, 8.))
        self.a = np.zeros(self.b.shape)
        self.a[0] = 1.
        self.subsampled_sampling_rate = SAMPLING_RATE / 2 ** self.Ndec
        # A different sample interval cannot share the old history or filter tail.
        configuration = self.audiobuffer.channel_configuration if self.audiobuffer is not None else None
        self.reset_channel_state(configuration)
        self.setduration(self.length_seconds)

    def settings_called(self, checked):
        self.settings_dialog.show()

    def saveState(self, settings):
        self.settings_dialog.saveState(settings)

    def restoreState(self, settings):
        self.settings_dialog.restoreState(settings)

    def cleanup(self):
        self._long_levels_data.set_channels([])
        self.settings_dialog.deleteLater()
