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

import numpy as np
from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal  # type: ignore
from polyfriture.settings_model import FloatSetting, SettingsModel, SettingsValueError

DEFAULT_SINE_FREQUENCY = 440.


class SineSettings(SettingsModel):
    fields = {
        "sine frequency": FloatSetting(DEFAULT_SINE_FREQUENCY, minimum=20., maximum=22000.),
    }


class SineGenerator:

    name = "Sine"

    def __init__(self, parent):
        self._view_model = Sine_Generator_Settings_View_Model(parent)

    def view_model(self):
        return self._view_model

    def qml_file_name(self) -> str:
        return "SineSettings.qml"

    def signal(self, t):
        self._view_model.lastt = t[-1]
        return np.sin(2. * np.pi * t * self._view_model.frequency + self._view_model.offset)

class Sine_Generator_Settings_View_Model(QObject):
    frequency_changed = pyqtSignal(float)

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.settings = SineSettings()
        self.offset = 0
        self.lastt = 0

    @pyqtProperty(float, notify=frequency_changed)
    def frequency(self) -> float:
        return self.settings.get("sine frequency")

    @frequency.setter # type: ignore
    def frequency(self, frequency: float):
        previous = self.frequency
        try:
            self.settings.set("sine frequency", frequency)
        except SettingsValueError as error:
            logging.getLogger(__name__).warning("Ignoring invalid sine frequency: %s", error)
            return
        self._frequency_updated(previous)

    def _frequency_updated(self, previous):
        if previous != self.frequency:
            # Adapt the offset to avoid a phase break.
            self.offset += 2. * np.pi * self.lastt * (previous - self.frequency)
            self.offset %= 2. * np.pi
            self.frequency_changed.emit(self.frequency)

    @pyqtProperty(float, constant=True)
    def frequencyMinimum(self):
        return self.settings.fields["sine frequency"].minimum

    @pyqtProperty(float, constant=True)
    def frequencyMaximum(self):
        return self.settings.fields["sine frequency"].maximum

    def saveState(self, settings):
        self.settings.save(settings)

    def restoreState(self, settings):
        previous = self.frequency
        self.settings.restore(settings)
        self._frequency_updated(previous)
