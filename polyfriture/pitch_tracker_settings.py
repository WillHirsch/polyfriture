#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2024 Celeste Sinéad
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
from polyfriture.settings_model import FloatSetting, IntSetting, SettingsModel
from polyfriture.settings_binding import bind_spinbox
from PyQt6.QtCore import QSettings
from typing import Any

from polyfriture.audiobackend import SAMPLING_RATE

# Pitch tracker defaults:
DEFAULT_FFT_SIZE = 4096
DEFAULT_MIN_FREQ = 65
DEFAULT_MAX_FREQ = 1047
DEFAULT_DURATION = 10
DEFAULT_MIN_DB = -50.0
DEFAULT_C_RES = 10      # Pitch resolution in cents. Default of 10 produces 120 kernels per octave.
DEFAULT_P_CONF = 0.50   # Confidence threshold for pitch estimation. Unitless.
DEFAULT_P_DELTA = 2     # Maximum pitch jump between frames in semitones.

class PitchTrackerSettings(SettingsModel):
    fields = {
        "min_freq": IntSetting(DEFAULT_MIN_FREQ, minimum=10, maximum=SAMPLING_RATE // 2),
        "max_freq": IntSetting(DEFAULT_MAX_FREQ, minimum=10, maximum=SAMPLING_RATE // 2),
        "duration": IntSetting(DEFAULT_DURATION, minimum=5, maximum=60),
        "conf": FloatSetting(DEFAULT_P_CONF, minimum=0, maximum=1),
        "min_db": FloatSetting(DEFAULT_MIN_DB, minimum=-100, maximum=0),
    }


class PitchTrackerSettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget, view_model: Any) -> None:
        super().__init__(parent)
        self.model = PitchTrackerSettings()
        self.setWindowTitle("Pitch Tracker Settings")
        self.form_layout = QtWidgets.QFormLayout(self)

        self.min_freq = QtWidgets.QSpinBox(self)
        self.min_freq.setSingleStep(10)
        self.min_freq.setSuffix(" Hz")
        self.min_freq.setObjectName("min_freq")
        bind_spinbox(self.min_freq, self.model, "min_freq", view_model.set_min_freq)
        self.form_layout.addRow("Min:", self.min_freq)

        self.max_freq = QtWidgets.QSpinBox(self)
        self.max_freq.setSingleStep(10)
        self.max_freq.setSuffix(" Hz")
        self.max_freq.setObjectName("max_freq")
        bind_spinbox(self.max_freq, self.model, "max_freq", view_model.set_max_freq)
        self.form_layout.addRow("Max:", self.max_freq)

        self.duration = QtWidgets.QSpinBox(self)
        self.duration.setSingleStep(1)
        self.duration.setSuffix(" s")
        self.duration.setObjectName("duration")
        bind_spinbox(self.duration, self.model, "duration", view_model.set_duration)
        self.form_layout.addRow("Duration:", self.duration)

        self.conf = QtWidgets.QDoubleSpinBox(self)
        self.conf.setSingleStep(0.01)
        self.conf.setSuffix("")
        self.conf.setObjectName("conf")
        bind_spinbox(self.conf, self.model, "conf", view_model.set_conf)
        self.form_layout.addRow("Conf. Cut:", self.conf)

        self.min_db = QtWidgets.QDoubleSpinBox(self)
        self.min_db.setSingleStep(1)
        self.min_db.setSuffix(" dB")
        self.min_db.setObjectName("min_db")
        bind_spinbox(self.min_db, self.model, "min_db", view_model.set_min_db)
        self.form_layout.addRow("Min Amplitude:", self.min_db)

        self.setLayout(self.form_layout)

    def save_state(self, settings: QSettings) -> None:
        self.model.save(settings)

    def restore_state(self, settings: QSettings) -> None:
        self.model.restore(settings)
        self.min_freq.setValue(self.model.get("min_freq"))
        self.max_freq.setValue(self.model.get("max_freq"))
        self.duration.setValue(self.model.get("duration"))
        self.conf.setValue(self.model.get("conf"))
        self.min_db.setValue(self.model.get("min_db"))
