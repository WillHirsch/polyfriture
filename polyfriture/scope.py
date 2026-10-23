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

import logging

from PyQt6 import QtWidgets
from polyfriture.settings_model import FloatSetting, SettingsModel
from polyfriture.settings_binding import bind_spinbox
from PyQt6.QtCore import QObject

from numpy import where, arange, zeros
from PyQt6.QtGui import QColor

from polyfriture.audiobackend import SAMPLING_RATE
from polyfriture.scope_data import Scope_Data
from polyfriture.curve import Curve

SMOOTH_DISPLAY_TIMER_PERIOD_MS = 25
DEFAULT_TIMERANGE = 2 * SMOOTH_DISPLAY_TIMER_PERIOD_MS

SCROLLING_THRESHOLD_MS = 500.0


def channel_color(channel_id):
    """Keep a physical channel's color when its selection or row changes."""
    # A golden-angle hue sequence spreads adjacent IDs around the color wheel
    # without cycling through a short palette for larger channel selections.
    return QColor.fromHsvF((channel_id * 0.618033988749895) % 1., 0.8, 0.85).name()


class Scope_Widget(QObject):

    def __init__(self, parent):
        super().__init__(parent)

        self.logger = logging.getLogger(__name__)

        self.audiobuffer = None

        self._scope_data = Scope_Data(self)
        self._curves = {}

        self._scope_data.vertical_axis.name = "Signal"
        self._scope_data.vertical_axis.setTrackerFormatter(lambda x: "%#.3g" % (x))
        self._scope_data.horizontal_axis.name = "Time (ms)"
        self._scope_data.horizontal_axis.setTrackerFormatter(lambda x: "%#.3g ms" % (x))

        self.settings_dialog = Scope_Settings_Dialog(parent, self)

        self.set_timerange(DEFAULT_TIMERANGE)

        self.time = zeros(0)
        self.samples = zeros((0, 0))

    def qml_file_name(self):
        return "Scope.qml"

    def view_model(self):
        return self._scope_data

    # method
    def set_buffer(self, buffer):
        self.audiobuffer = buffer
        self.reset_channel_state(buffer.channel_configuration)

    def reset_channel_state(self, configuration):
        self.time = zeros(0)
        curves = {}
        if configuration is not None:
            for channel_id, label in zip(configuration.channel_ids, configuration.channel_labels):
                curve = self._curves.get(channel_id)
                if curve is None:
                    curve = Curve()
                    curve.color = channel_color(channel_id)
                curve.name = label
                curve.setData(zeros(0), zeros(0))
                curves[channel_id] = curve
        self._curves = curves
        self.samples = zeros((len(curves), 0))
        self._scope_data.set_plot_items(list(curves.values()))

    def handle_new_data(self, floatdata):
        if not self._curves:
            return

        time = self.timerange * 1e-3
        width = int(time * SAMPLING_RATE)

        if self.timerange > SCROLLING_THRESHOLD_MS:
            # Scrolling mode for long time windows: show the latest samples
            # without triggering, which causes missed updates on noisy signals.
            self.samples = self.audiobuffer.data(width)
        else:
            # Trigger mode: fetch 2x window and align on a rising edge.
            floatdata = self.audiobuffer.data(2 * width)
            # trigger on the first channel only
            triggerdata = floatdata[0, :]
            # trigger on half of the waveform
            trig_search_start = width // 2
            trig_search_stop = trig_search_start + width
            triggerdata = triggerdata[trig_search_start: trig_search_stop]

            trigger_level = triggerdata.max() * 2. / 3.
            trigger_pos = where((triggerdata[:-1] < trigger_level) * (triggerdata[1:] >= trigger_level))[0]

            if len(trigger_pos) == 0:
                return

            shift = trigger_pos[0] + trig_search_start
            start = shift - width // 2
            self.samples = floatdata[:, start: start + width]

        self.time = (arange(self.samples.shape[1]) - width // 2) / float(SAMPLING_RATE)

        scaled_t = (self.time * 1e3 + self.timerange/2.) / self.timerange
        for curve, samples in zip(self._curves.values(), self.samples):
            curve.setData(scaled_t, 1. - (samples + 1) / 2.)

    def cleanup(self):
        self.settings_dialog.close()
        self.settings_dialog.deleteLater()

    # method
    def canvasUpdate(self):
        return

    def pause(self):
        return

    def restart(self):
        return

    # slot
    def set_timerange(self, timerange):
        self.timerange = timerange
        self._scope_data.horizontal_axis.setRange(-self.timerange/2., self.timerange/2.)

    # slot
    def settings_called(self, checked):
        self.settings_dialog.show()

    # method
    def saveState(self, settings):
        self.settings_dialog.saveState(settings)

    # method
    def restoreState(self, settings):
        self.settings_dialog.restoreState(settings)


class ScopeSettings(SettingsModel):
    fields = {
        "timeRange": FloatSetting(DEFAULT_TIMERANGE, minimum=0.1, maximum=10000.0),
    }


class Scope_Settings_Dialog(QtWidgets.QDialog):

    def __init__(self, parent, view_model):
        super().__init__(parent)
        self.model = ScopeSettings()

        self.setWindowTitle("Scope settings")

        self.formLayout = QtWidgets.QFormLayout(self)

        self.doubleSpinBox_timerange = QtWidgets.QDoubleSpinBox(self)
        self.doubleSpinBox_timerange.setDecimals(1)
        self.doubleSpinBox_timerange.setObjectName("doubleSpinBox_timerange")
        self.doubleSpinBox_timerange.setSuffix(" ms")

        self.formLayout.addRow("Time range:", self.doubleSpinBox_timerange)

        self.setLayout(self.formLayout)

        bind_spinbox(self.doubleSpinBox_timerange, self.model, "timeRange", view_model.set_timerange)

    # method
    def saveState(self, settings):
        self.model.save(settings)

    def restoreState(self, settings):
        self.model.restore(settings)
        self.doubleSpinBox_timerange.setValue(self.model.get("timeRange"))
