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
from numpy import log10, array, arange

from polyfriture.histplot import HistPlot
from polyfriture.octavefilters import Octave_Filters, octave_decimations
from polyfriture.octavespectrum_settings import (
    OctaveSpectrum_Settings_Dialog, DEFAULT_SPEC_MIN, DEFAULT_SPEC_MAX,
    DEFAULT_WEIGHTING, DEFAULT_BANDSPEROCTAVE, DEFAULT_RESPONSE_TIME,
)
from polyfriture.scope_data import Scope_Data
from polyfriture.pitch_tracker import format_frequency
import polyfriture.plotting.frequency_scales as fscales
from polyfriture.signal.exp_smoothing import exp_smoothed_value
from polyfriture.audiobackend import SAMPLING_RATE


class OctaveSpectrumChannel(QObject):
    """Independent filter tails, smoothing and held peaks for one row."""

    def __init__(self, panel, label):
        super().__init__(panel)
        self.filters = Octave_Filters(panel.bandsperoctave)
        self.dispbuffers = [0.] * self.filters.nbands
        self.plot = HistPlot(self, axes=panel._grid_data)
        self.plot.view_model().label = label
        self.plot.paused = panel.paused
        self.plot.reset()


class OctaveSpectrum_Widget(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.audiobuffer = None
        self._grid_data = Scope_Data(self)
        self._channels = {}
        self.paused = False
        self.spec_min = DEFAULT_SPEC_MIN
        self.spec_max = DEFAULT_SPEC_MAX
        self.weighting = DEFAULT_WEIGHTING
        self.response_time = DEFAULT_RESPONSE_TIME
        self.bandsperoctave = DEFAULT_BANDSPEROCTAVE
        self._grid_data.vertical_axis.setTrackerFormatter(lambda x: "%.1f dB" % x)
        self._grid_data.horizontal_axis.name = "Frequency (Hz)"
        self._grid_data.horizontal_axis.setTrackerFormatter(format_frequency)
        self._grid_data.horizontal_axis.show_minor_grid_lines = True
        self._grid_data.horizontal_axis.setScale(fscales.Logarithmic)
        self._grid_data.horizontal_axis.setRange(44, 22000)
        self._grid_data.vertical_axis.setRange(self.spec_min, self.spec_max)
        self.setweighting(self.weighting)
        self.setresponsetime(self.response_time)
        self.settings_dialog = OctaveSpectrum_Settings_Dialog(parent, self)

    def qml_file_name(self):
        return "HistPlot.qml"

    def view_model(self):
        return self._grid_data

    def set_buffer(self, buffer):
        self.audiobuffer = buffer
        self.reset_channel_state(buffer.channel_configuration)

    def reset_channel_state(self, configuration):
        previous = self._channels
        self._channels = {} if configuration is None else {
            channel_id: OctaveSpectrumChannel(self, label)
            for channel_id, label in zip(configuration.channel_ids, configuration.channel_labels)
        }
        self._grid_data.set_channels([state.plot.view_model() for state in self._channels.values()])
        for state in previous.values():
            state.deleteLater()

    def handle_new_data(self, floatdata):
        if floatdata.shape[1] == 0:
            return
        for state, samples in zip(self._channels.values(), floatdata):
            outputs, _ = state.filters.filter(samples)
            state.dispbuffers = [
                exp_smoothed_value(kernel, alpha, output ** 2, previous)
                for output, kernel, alpha, previous in zip(outputs, self.kernels, self.alphas, state.dispbuffers)
            ]
            weights = (0., state.filters.A, state.filters.B, state.filters.C)[self.weighting]
            levels = 10. * log10(array(state.dispbuffers) + 1e-30) + weights
            state.plot.setdata(state.filters.flow, state.filters.fhigh, state.filters.f_nominal, levels)

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

    def setmin(self, value):
        self.spec_min = value
        self._grid_data.vertical_axis.setRange(min(self.spec_min, self.spec_max), max(self.spec_min, self.spec_max))

    def setmax(self, value):
        self.spec_max = value
        self._grid_data.vertical_axis.setRange(min(self.spec_min, self.spec_max), max(self.spec_min, self.spec_max))

    def setweighting(self, weighting):
        self.weighting = weighting
        self._grid_data.vertical_axis.name = "PSD (dB%s)" % ("", " A", " B", " C")[weighting]

    def setresponsetime(self, response_time):
        self.response_time = response_time
        decimations = octave_decimations(self.bandsperoctave)
        ns = [response_time * SAMPLING_RATE / decimation for decimation in decimations]
        self.alphas = [1. - (1. - 0.65) ** (1. / (n + 1)) for n in ns]
        self.kernels = [(1. - alpha) ** arange(8192 / decimation - 1, -1, -1)
                        for alpha, decimation in zip(self.alphas, decimations)]

    def setbandsperoctave(self, bandsperoctave):
        self.bandsperoctave = bandsperoctave
        for state in self._channels.values():
            state.filters.setbandsperoctave(bandsperoctave)
            state.dispbuffers = [0.] * state.filters.nbands
            state.plot.reset()
        self.setresponsetime(self.response_time)

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
