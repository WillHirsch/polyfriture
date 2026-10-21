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
from polyfriture.settings_model import ChoiceSetting, IntSetting, SettingsModel
from polyfriture.settings_binding import bind_combobox, bind_spinbox

# shared with octavespectrum.py
DEFAULT_SPEC_MIN = -80
DEFAULT_SPEC_MAX = -20
DEFAULT_WEIGHTING = 0  # None
DEFAULT_BANDSPEROCTAVE = 3
DEFAULT_BANDSPEROCTAVE_INDEX = 1
DEFAULT_RESPONSE_TIME = 1.
DEFAULT_RESPONSE_TIME_INDEX = 3


class OctaveSpectrumSettings(SettingsModel):
    fields = {
        "bandsPerOctave": ChoiceSetting(DEFAULT_BANDSPEROCTAVE_INDEX, labels=("1", "3", "6", "12", "24")),
        "Min": IntSetting(DEFAULT_SPEC_MIN, minimum=-200, maximum=200),
        "Max": IntSetting(DEFAULT_SPEC_MAX, minimum=-200, maximum=200),
        "weighting": ChoiceSetting(DEFAULT_WEIGHTING, labels=("None", "A", "B", "C")),
        "response_time": ChoiceSetting(DEFAULT_RESPONSE_TIME_INDEX, labels=("25 ms (Impulse)", "125 ms (Fast)", "300 ms", "1s (Slow)", "5s (Very Slow)")),
    }


class OctaveSpectrum_Settings_Dialog(QtWidgets.QDialog):

    def __init__(self, parent, view_model):
        super().__init__(parent)
        self.model = OctaveSpectrumSettings()

        self.view_model = view_model

        self.logger = logging.getLogger(__name__)

        self.setWindowTitle("Octave Spectrum settings")

        self.formLayout = QtWidgets.QFormLayout(self)

        self.comboBox_bandsperoctave = QtWidgets.QComboBox(self)
        self.comboBox_bandsperoctave.setObjectName("comboBox_bandsperoctave")

        self.spinBox_specmin = QtWidgets.QSpinBox(self)
        self.spinBox_specmin.setKeyboardTracking(False)
        self.spinBox_specmin.setObjectName("spinBox_specmin")
        self.spinBox_specmin.setSuffix(" dB")

        self.spinBox_specmax = QtWidgets.QSpinBox(self)
        self.spinBox_specmax.setKeyboardTracking(False)
        self.spinBox_specmax.setObjectName("spinBox_specmax")
        self.spinBox_specmax.setSuffix(" dB")

        self.comboBox_weighting = QtWidgets.QComboBox(self)
        self.comboBox_weighting.setObjectName("weighting")

        self.comboBox_response_time = QtWidgets.QComboBox(self)
        self.comboBox_response_time.setObjectName("response_time")

        self.formLayout.addRow("Bands per octave:", self.comboBox_bandsperoctave)
        self.formLayout.addRow("Min:", self.spinBox_specmin)
        self.formLayout.addRow("Max:", self.spinBox_specmax)
        self.formLayout.addRow("Middle-ear weighting:", self.comboBox_weighting)
        self.formLayout.addRow("Response time:", self.comboBox_response_time)

        self.setLayout(self.formLayout)

        bind_combobox(self.comboBox_bandsperoctave, self.model, "bandsPerOctave", self.bandsperoctavechanged)
        bind_spinbox(self.spinBox_specmin, self.model, "Min", view_model.setmin)
        bind_spinbox(self.spinBox_specmax, self.model, "Max", view_model.setmax)
        bind_combobox(self.comboBox_weighting, self.model, "weighting", view_model.setweighting)
        bind_combobox(self.comboBox_response_time, self.model, "response_time", self.responsetimechanged)

    # slot
    def bandsperoctavechanged(self, index):
        bandsperoctave = 3 * 2 ** (index - 1) if index >= 1 else 1
        self.logger.info("bandsperoctavechanged slot %d %d", index, bandsperoctave)
        self.view_model.setbandsperoctave(bandsperoctave)

    # slot
    def responsetimechanged(self, index):
        if index == 0:
            response_time = 0.025
        elif index == 1:
            response_time = 0.125
        elif index == 2:
            response_time = 0.3
        elif index == 3:
            response_time = 1.
        elif index == 4:
            response_time = 5.
        self.logger.info("responsetimechanged slot %d %d", index, response_time)
        self.view_model.setresponsetime(response_time)

    # method
    def saveState(self, settings):
        self.model.save(settings)

    def restoreState(self, settings):
        self.model.restore(settings)
        self.comboBox_bandsperoctave.setCurrentIndex(self.model.get("bandsPerOctave"))
        self.spinBox_specmin.setValue(self.model.get("Min"))
        self.spinBox_specmax.setValue(self.model.get("Max"))
        self.comboBox_weighting.setCurrentIndex(self.model.get("weighting"))
        self.comboBox_response_time.setCurrentIndex(self.model.get("response_time"))
