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
from polyfriture.settings_model import BoolSetting, ChoiceSetting, IntSetting, SettingsModel
from polyfriture.settings_binding import bind_checkbox, bind_combobox, bind_spinbox
from polyfriture.audiobackend import SAMPLING_RATE
import polyfriture.plotting.frequency_scales as fscales

# shared with spectrum_settings.py
DEFAULT_FFT_SIZE = 8  # 8192 points
DEFAULT_FREQ_SCALE = 2  # Mel
DEFAULT_MAXFREQ = 20000
DEFAULT_MINFREQ = 20
DEFAULT_SPEC_MIN = -100
DEFAULT_SPEC_MAX = -20
DEFAULT_WEIGHTING = 1  # A
DEFAULT_SHOW_FREQ_LABELS = True
DEFAULT_SHOW_PITCH_LABELS = True
DEFAULT_RESPONSE_TIME = 0.025
DEFAULT_RESPONSE_TIME_INDEX = 0


class SpectrumSettings(SettingsModel):
    fields = {
        "fftSize": ChoiceSetting(DEFAULT_FFT_SIZE, labels=tuple(f"{2 ** exponent} points" for exponent in range(5, 15))),
        "freqScale": ChoiceSetting(DEFAULT_FREQ_SCALE, labels=tuple(scale.NAME for scale in fscales.ALL)),
        "freqMin": IntSetting(DEFAULT_MINFREQ, minimum=20, maximum=SAMPLING_RATE // 2),
        "freqMax": IntSetting(DEFAULT_MAXFREQ, minimum=20, maximum=SAMPLING_RATE // 2),
        "Min": IntSetting(DEFAULT_SPEC_MIN, minimum=-200, maximum=200),
        "Max": IntSetting(DEFAULT_SPEC_MAX, minimum=-200, maximum=200),
        "weighting": ChoiceSetting(DEFAULT_WEIGHTING, labels=("None", "A", "B", "C")),
        "responseTime": ChoiceSetting(DEFAULT_RESPONSE_TIME_INDEX, labels=("25 ms (Impulse)", "125 ms (Fast)", "300 ms", "1s (Slow)", "5s (Very Slow)")),
        "showFreqLabels": BoolSetting(DEFAULT_SHOW_FREQ_LABELS),
        "showPitchLabel": BoolSetting(DEFAULT_SHOW_PITCH_LABELS),
    }


class Spectrum_Settings_Dialog(QtWidgets.QDialog):

    def __init__(self, parent, view_model):
        super().__init__(parent)
        self.model = SpectrumSettings()

        self.view_model = view_model

        self.logger = logging.getLogger(__name__)

        self.setWindowTitle("Spectrum settings")

        self.formLayout = QtWidgets.QFormLayout(self)

        self.comboBox_fftsize = QtWidgets.QComboBox(self)
        self.comboBox_fftsize.setObjectName("comboBox_fftsize")

        self.comboBox_freqscale = QtWidgets.QComboBox(self)
        self.comboBox_freqscale.setObjectName("comboBox_freqscale")

        self.spinBox_minfreq = QtWidgets.QSpinBox(self)
        self.spinBox_minfreq.setSingleStep(10)
        self.spinBox_minfreq.setObjectName("spinBox_minfreq")
        self.spinBox_minfreq.setSuffix(" Hz")

        self.spinBox_maxfreq = QtWidgets.QSpinBox(self)
        self.spinBox_maxfreq.setSingleStep(1000)
        self.spinBox_maxfreq.setObjectName("spinBox_maxfreq")
        self.spinBox_maxfreq.setSuffix(" Hz")

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

        self.checkBox_showFreqLabels = QtWidgets.QCheckBox(self)
        self.checkBox_showFreqLabels.setObjectName("showFreqLabels")

        self.checkBox_showPitchLabel = QtWidgets.QCheckBox(self)
        self.checkBox_showPitchLabel.setObjectName("showPitchLabels")

        self.formLayout.addRow("FFT Size:", self.comboBox_fftsize)
        self.formLayout.addRow("Frequency scale:", self.comboBox_freqscale)
        self.formLayout.addRow("Min frequency:", self.spinBox_minfreq)
        self.formLayout.addRow("Max frequency:", self.spinBox_maxfreq)
        self.formLayout.addRow("Min:", self.spinBox_specmin)
        self.formLayout.addRow("Max:", self.spinBox_specmax)
        self.formLayout.addRow("Middle-ear weighting:", self.comboBox_weighting)
        self.formLayout.addRow("Response time:", self.comboBox_response_time)
        self.formLayout.addRow("Display max-frequency label:", self.checkBox_showFreqLabels)
        self.formLayout.addRow("Display pitch label:", self.checkBox_showPitchLabel)

        self.setLayout(self.formLayout)

        bind_combobox(self.comboBox_fftsize, self.model, "fftSize", self.fftsizechanged)
        bind_combobox(self.comboBox_freqscale, self.model, "freqScale", self.freqscalechanged)
        bind_spinbox(self.spinBox_minfreq, self.model, "freqMin", self.view_model.setminfreq)
        bind_spinbox(self.spinBox_maxfreq, self.model, "freqMax", self.view_model.setmaxfreq)
        bind_spinbox(self.spinBox_specmin, self.model, "Min", self.view_model.setmin)
        bind_spinbox(self.spinBox_specmax, self.model, "Max", self.view_model.setmax)
        bind_combobox(self.comboBox_weighting, self.model, "weighting", self.view_model.setweighting)
        bind_combobox(self.comboBox_response_time, self.model, "responseTime", self.responsetimechanged)
        bind_checkbox(self.checkBox_showFreqLabels, self.model, "showFreqLabels", self.view_model.setShowFreqLabel)
        bind_checkbox(self.checkBox_showPitchLabel, self.model, "showPitchLabel", self.view_model.setShowPitchLabel)

    # slot
    def fftsizechanged(self, index):
        self.logger.info("fft_size_changed slot %d %d %f", index, 2 ** index * 32, 150000 / 2 ** index * 32)
        # FIXME the size should not be found from the index, but attached as item data
        fft_size = 2 ** index * 32
        self.view_model.setfftsize(fft_size)

    # slot
    def freqscalechanged(self, index):
        self.logger.info("freq_scale slot %d %s", index, fscales.ALL[index].NAME)
        self.view_model.PlotZoneSpect.setfreqscale(fscales.ALL[index])

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
        self.logger.info("responsetimechanged slot %d %f", index, response_time)
        self.view_model.setresponsetime(response_time)

    # method
    def saveState(self, settings):
        self.model.save(settings)

    def restoreState(self, settings):
        self.model.restore(settings)
        self.comboBox_fftsize.setCurrentIndex(self.model.get("fftSize"))
        self.comboBox_freqscale.setCurrentIndex(self.model.get("freqScale"))
        self.spinBox_minfreq.setValue(self.model.get("freqMin"))
        self.spinBox_maxfreq.setValue(self.model.get("freqMax"))
        self.spinBox_specmin.setValue(self.model.get("Min"))
        self.spinBox_specmax.setValue(self.model.get("Max"))
        self.comboBox_weighting.setCurrentIndex(self.model.get("weighting"))
        self.comboBox_response_time.setCurrentIndex(self.model.get("responseTime"))
        self.checkBox_showFreqLabels.setChecked(self.model.get("showFreqLabels"))
        self.checkBox_showPitchLabel.setChecked(self.model.get("showPitchLabel"))
