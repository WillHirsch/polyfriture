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

"""Dockable meters with independent DSP and one shared IEC scale."""

from dataclasses import dataclass

import numpy as np
from PyQt6.QtCore import QObject

from polyfriture.audiobackend import SAMPLING_RATE
from polyfriture.iec import IECScale, dB_to_IEC
from polyfriture.level_view_model import LevelViewModel
from polyfriture.levels_settings import Levels_Settings_Dialog
from polyfriture.scope_data import Scope_Data
from polyfriture.signal.exp_smoothing import exp_smoothed_value

SMOOTH_DISPLAY_TIMER_PERIOD_MS = 25
LEVEL_TEXT_LABEL_PERIOD_MS = 250
LEVEL_TEXT_LABEL_STEPS = LEVEL_TEXT_LABEL_PERIOD_MS // SMOOTH_DISPLAY_TIMER_PERIOD_MS


@dataclass
class MeterChannelState:
    view: LevelViewModel
    old_rms: float = 1e-30
    old_max: float = 1e-30


class Levels_Widget(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self._parent = parent
        self.audiobuffer = None
        self._data = Scope_Data(self)
        self._data.show_legend = False
        self._data.vertical_axis.name = "Level (dB FS)"
        self._data.vertical_axis.setScale(IECScale)
        self._data.vertical_axis.setRange(-70., 0.)
        self.settings_dialog = Levels_Settings_Dialog(parent)
        self._channels = {}
        # Preserve the existing 300 ms RMS response and 25 ms peak response.
        self.response_time = 0.300
        w = 0.65
        n = self.response_time * SAMPLING_RATE
        self.alpha = 1. - (1. - w) ** (1. / (n + 1))
        self.kernel = (1. - self.alpha) ** np.arange(0, 5 * n)[::-1]
        n2 = 0.025 / (SMOOTH_DISPLAY_TIMER_PERIOD_MS / 1000.)
        self.alpha2 = 1. - (1. - w) ** (1. / (n2 + 1))
        self.i = 0

    def qml_file_name(self):
        return "Levels.qml"

    def view_model(self):
        return self._data

    def set_buffer(self, buffer):
        self.audiobuffer = buffer
        self.reset_channel_state(buffer.channel_configuration)

    def reset_channel_state(self, configuration):
        previous = self._channels
        self._channels = {}
        if configuration is not None:
            for channel_id, label in zip(configuration.channel_ids, configuration.channel_labels):
                view = LevelViewModel(self, axes=self._data)
                view.label = label
                self._channels[channel_id] = MeterChannelState(view)
        self._data.set_channels([state.view for state in self._channels.values()])
        for state in previous.values():
            state.view.deleteLater()
        self.i = 0

    def handle_new_data(self, floatdata):
        for samples, state in zip(floatdata, self._channels.values()):
            if not samples.size:
                continue
            value_max = np.abs(samples).max()
            state.old_max = max(value_max, state.old_max * (1. - self.alpha2))
            state.old_rms = exp_smoothed_value(self.kernel, self.alpha, samples ** 2, state.old_rms)
            data = state.view.level_data
            with np.errstate(divide="ignore"):
                data.level_rms = 10. * np.log10(state.old_rms)
                data.level_max = 20. * np.log10(state.old_max)
            state.view.level_data_ballistic.peak_iec = dB_to_IEC(max(data.level_max, data.level_rms))

    def canvasUpdate(self):
        if not self._parent.isVisible():
            return
        self.i += 1
        if self.i == LEVEL_TEXT_LABEL_STEPS:
            for state in self._channels.values():
                state.view.level_data_slow.level_rms = state.view.level_data.level_rms
                state.view.level_data_slow.level_max = state.view.level_data.level_max
        self.i %= LEVEL_TEXT_LABEL_STEPS

    def pause(self):
        pass

    def restart(self):
        pass

    def settings_called(self, checked):
        self.settings_dialog.show()

    def saveState(self, settings):
        self.settings_dialog.saveState(settings)

    def restoreState(self, settings):
        self.settings_dialog.restoreState(settings)

    def cleanup(self):
        self.reset_channel_state(None)
        self.settings_dialog.close()
        self.settings_dialog.deleteLater()
