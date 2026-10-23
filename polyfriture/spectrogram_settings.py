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
from polyfriture.settings_model import BoolSetting, ChoiceSetting, FloatSetting, IntSetting, SettingsModel
from polyfriture.settings_binding import bind_checkbox, bind_combobox, bind_spinbox
from polyfriture.audiobackend import SAMPLING_RATE
import polyfriture.plotting.frequency_scales as fscales

# shared with spectrogram.py
DEFAULT_FFT_SIZE = 7  # 4096 points
DEFAULT_FREQ_SCALE = 2  # Mel
DEFAULT_MAXFREQ = SAMPLING_RATE / 2
DEFAULT_MINFREQ = 20
DEFAULT_SPEC_MIN = -140
DEFAULT_SPEC_MAX = 0
DEFAULT_TIMERANGE = 10.
DEFAULT_WEIGHTING = 0  # None


class SpectrogramSettings(SettingsModel):
    fields = {
        "timeRange": FloatSetting(DEFAULT_TIMERANGE, minimum=0.1, maximum=1000.0),
        "fftSize": ChoiceSetting(DEFAULT_FFT_SIZE, labels=tuple(f"{2 ** exponent} points" for exponent in range(5, 15))),
        "freqScale": ChoiceSetting(DEFAULT_FREQ_SCALE, labels=tuple(scale.NAME for scale in fscales.ALL)),
        "freqMin": IntSetting(DEFAULT_MINFREQ, minimum=20, maximum=SAMPLING_RATE // 2),
        "freqMax": IntSetting(int(DEFAULT_MAXFREQ), minimum=20, maximum=SAMPLING_RATE // 2),
        "colorMin": IntSetting(DEFAULT_SPEC_MIN, minimum=-200, maximum=200),
        "colorMax": IntSetting(DEFAULT_SPEC_MAX, minimum=-200, maximum=200),
        "weighting": ChoiceSetting(DEFAULT_WEIGHTING, labels=("None", "A", "B", "C")),
        "rotated": BoolSetting(False),
    }


class Spectrogram_Settings_Dialog(QtWidgets.QDialog):

    def __init__(self, parent, view_model):
        super().__init__(parent)
        self.model = SpectrogramSettings()

        self.logger = logging.getLogger(__name__)

        self.view_model = view_model

        self.setWindowTitle("Spectrogram settings")

        self.formLayout = QtWidgets.QFormLayout(self)

        self.doubleSpinBox_timerange = QtWidgets.QDoubleSpinBox(self)
        self.doubleSpinBox_timerange.setDecimals(1)
        self.doubleSpinBox_timerange.setObjectName("doubleSpinBox_timerange")
        self.doubleSpinBox_timerange.setSuffix(" s")

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

        self.checkBox_rotated = QtWidgets.QCheckBox("Rotate 90\N{DEGREE SIGN} clockwise", self)
        self.checkBox_rotated.setObjectName("checkBox_rotated")
        self.checkBox_rotated.setToolTip(
            "Frequency increases rightward; newest audio appears at the bottom. "
            "The grid is transposed, so the global column count becomes the row count.")

        self.formLayout.addRow("Time range:", self.doubleSpinBox_timerange)
        self.formLayout.addRow("FFT Size:", self.comboBox_fftsize)
        self.formLayout.addRow("Frequency scale:", self.comboBox_freqscale)
        self.formLayout.addRow("Min frequency:", self.spinBox_minfreq)
        self.formLayout.addRow("Max frequency:", self.spinBox_maxfreq)
        self.formLayout.addRow("Min color:", self.spinBox_specmin)
        self.formLayout.addRow("Max color:", self.spinBox_specmax)
        self.formLayout.addRow("Middle-ear weighting:", self.comboBox_weighting)
        self.formLayout.addRow("Orientation:", self.checkBox_rotated)

        self.setLayout(self.formLayout)

        bind_combobox(self.comboBox_fftsize, self.model, "fftSize", self.fftsizechanged)
        bind_combobox(self.comboBox_freqscale, self.model, "freqScale", self.freqscalechanged)
        bind_spinbox(self.spinBox_minfreq, self.model, "freqMin", view_model.setminfreq)
        bind_spinbox(self.spinBox_maxfreq, self.model, "freqMax", view_model.setmaxfreq)
        bind_spinbox(self.spinBox_specmin, self.model, "colorMin", view_model.setmin)
        bind_spinbox(self.spinBox_specmax, self.model, "colorMax", view_model.setmax)
        bind_spinbox(self.doubleSpinBox_timerange, self.model, "timeRange", view_model.timerangechanged)
        bind_combobox(self.comboBox_weighting, self.model, "weighting", view_model.setweighting)
        bind_checkbox(self.checkBox_rotated, self.model, "rotated", view_model.setrotated)

    # slot
    def fftsizechanged(self, index):
        self.logger.info("fft_size_changed slot %d %d %f", index, 2 ** index * 32, 150000 / 2 ** index * 32)
        fft_size = 2 ** index * 32
        self.view_model.setfftsize(fft_size)

    # slot
    def freqscalechanged(self, index):
        self.logger.info("freq_scale slot %d %s", index, fscales.ALL[index])
        self.view_model.setfreqscale(fscales.ALL[index])

    # method
    def saveState(self, settings):
        self.model.save(settings)

    def restoreState(self, settings):
        self.model.restore(settings)
        self.doubleSpinBox_timerange.setValue(self.model.get("timeRange"))
        self.comboBox_fftsize.setCurrentIndex(self.model.get("fftSize"))
        self.comboBox_freqscale.setCurrentIndex(self.model.get("freqScale"))
        self.spinBox_minfreq.setValue(self.model.get("freqMin"))
        self.spinBox_maxfreq.setValue(self.model.get("freqMax"))
        self.spinBox_specmin.setValue(self.model.get("colorMin"))
        self.spinBox_specmax.setValue(self.model.get("colorMax"))
        self.comboBox_weighting.setCurrentIndex(self.model.get("weighting"))
        self.checkBox_rotated.setChecked(self.model.get("rotated"))
