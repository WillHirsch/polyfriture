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

from PyQt6 import QtWidgets
from polyfriture.settings_model import IntSetting, SettingsModel
from polyfriture.settings_binding import bind_spinbox

DEFAULT_MAXTIME = 600
#DEFAULT_MINTIME = 20
DEFAULT_LEVEL_MIN = -70
DEFAULT_LEVEL_MAX = -20
DEFAULT_RESPONSE_TIME = 20
#DEFAULT_RESPONSE_TIME_INDEX = 0


class LongLevelsSettings(SettingsModel):
    fields = {
        "Min": IntSetting(DEFAULT_LEVEL_MIN, minimum=-200, maximum=200),
        "Max": IntSetting(DEFAULT_LEVEL_MAX, minimum=-200, maximum=200),
        "RespTime": IntSetting(DEFAULT_RESPONSE_TIME, minimum=1, maximum=20),
        "TimeMax": IntSetting(DEFAULT_MAXTIME, minimum=5, maximum=3600),
    }


class LongLevels_Settings_Dialog(QtWidgets.QDialog):

    def __init__(self, parent, view_model):
        super().__init__(parent)
        self.model = LongLevelsSettings()

        self.setWindowTitle("Long levels settings")

        self.formLayout = QtWidgets.QFormLayout(self)

        self.spinBox_specmin = QtWidgets.QSpinBox(self)
        self.spinBox_specmin.setKeyboardTracking(False)
        self.spinBox_specmin.setObjectName("longlevels_specmin")
        self.spinBox_specmin.setSuffix(" dB")

        self.spinBox_specmax = QtWidgets.QSpinBox(self)
        self.spinBox_specmax.setKeyboardTracking(False)
        self.spinBox_specmax.setObjectName("longlevels_specmax")
        self.spinBox_specmax.setSuffix(" dB")

        self.spinBox_resptime = QtWidgets.QSpinBox(self)
        self.spinBox_resptime.setKeyboardTracking(False)
        self.spinBox_resptime.setObjectName("longlevels_resptime")
        self.spinBox_resptime.setSuffix(" sec")

        self.spinBox_timemax = QtWidgets.QSpinBox(self)
        self.spinBox_timemax.setKeyboardTracking(False)
        self.spinBox_timemax.setObjectName("longlevels_timemax")
        self.spinBox_timemax.setSuffix(" sec")


        self.formLayout.addRow("Max:", self.spinBox_specmax)
        self.formLayout.addRow("Min:", self.spinBox_specmin)
        self.formLayout.addRow("Response Time", self.spinBox_resptime)
        self.formLayout.addRow("Time Range:", self.spinBox_timemax)

        self.setLayout(self.formLayout)

        bind_spinbox(self.spinBox_specmin, self.model, "Min", view_model.setmin)
        bind_spinbox(self.spinBox_specmax, self.model, "Max", view_model.setmax)
        bind_spinbox(self.spinBox_resptime, self.model, "RespTime", view_model.setresptime)
        bind_spinbox(self.spinBox_timemax, self.model, "TimeMax", view_model.setduration)

    # method
    def saveState(self, settings):
        self.model.save(settings)

    def restoreState(self, settings):
        self.model.restore(settings)
        self.spinBox_specmin.setValue(self.model.get("Min"))
        self.spinBox_specmax.setValue(self.model.get("Max"))
        self.spinBox_resptime.setValue(self.model.get("RespTime"))
        self.spinBox_timemax.setValue(self.model.get("TimeMax"))
