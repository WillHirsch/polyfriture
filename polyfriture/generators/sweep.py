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
from typing import Any, Mapping

import numpy as np
from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal  # type: ignore
from polyfriture.settings_model import FloatSetting, SettingsModel, SettingsValueError

DEFAULT_SWEEP_STARTFREQUENCY = 20.
DEFAULT_SWEEP_STOPFREQUENCY = 22000.
DEFAULT_SWEEP_PERIOD_S = 1.


class SweepSettings(SettingsModel):
    fields = {
        "sweep start frequency": FloatSetting(DEFAULT_SWEEP_STARTFREQUENCY, minimum=20., maximum=22000.),
        "sweep stop frequency": FloatSetting(DEFAULT_SWEEP_STOPFREQUENCY, minimum=20., maximum=22000.),
        "sweep period": FloatSetting(DEFAULT_SWEEP_PERIOD_S, minimum=0.01, maximum=60.),
    }

    def validate(self, values: Mapping[str, Any]) -> None:
        if values["sweep start frequency"] == values["sweep stop frequency"]:
            raise SettingsValueError(
                "sweep endpoints must differ",
                keys=("sweep start frequency", "sweep stop frequency"))


class SweepGenerator:
    name = "Sweep"

    def __init__(self, parent):
        self._view_model = Sweep_Generator_Settings_View_Model(parent)
    
        self._view_model.start_frequency_changed.connect(self.updateParams)
        self._view_model.stop_frequency_changed.connect(self.updateParams)
        self._view_model.peiod_changed.connect(self.updateParams)
    
        self.updateParams()
        [self.L, self.K, self.T] = self.nextParams
        self.nextParams = None
        self.timeoffset = 0.

    def view_model(self):
        return self._view_model

    def qml_file_name(self) -> str:
        return "SweepSettings.qml"
    
    def updateParams(self):
        self.nextParams = self.computeParams(
            self._view_model.start_frequency,
            self._view_model.stop_frequency,
            self._view_model.period)

    def computeParams(self, f1, f2, T):
        # adjust T so that we have an integer number of periods
        # we want phase_max to be a multiple of 2*np.pi
        # phase_max = 2*np.pi*f1*T/np.log(f2/f1)*(f2/f1 - 1.)
        # phase_max = N*2*np.pi
        # N = f1*T/np.log(f2/f1)*(f2/f1 - 1.)
        Tmult = np.log(f2 / f1) / (f1 * (f2 / f1 - 1.))
        if T >= Tmult:
            T = np.round(T / Tmult) * Tmult
        else:
            T = np.ceil(T / Tmult) * Tmult

        w1 = 2 * np.pi * f1
        w2 = 2 * np.pi * f2
        K = w1 * T / np.log(w2 / w1)
        L = T / np.log(w2 / w1)
        return [L, K, T]

    def signal(self, t):
        # https://ccrma.stanford.edu/realsimple/imp_meas/Sine_Sweep_Measurement_Theory.html

        # f = (self.f2 - self.f1)*(1. + np.sin(2*np.pi*t/self.T))/2. + self.f1
        # return np.sin(2*np.pi*t*f)

        result = np.cos(self.K * (np.exp((t - self.timeoffset) % self.T / self.L) - 1.))

        if self.nextParams is not None:
            # we have new params to put in place
            # do it at the first max

            diff = result[1:] - result[:-1]
            maxdetection = 0. * diff[:-1] + (diff[1:] < 0.) * (diff[:-1] > 0.) * 1.

            maxdetections = np.argwhere(maxdetection != 0.)

            if len(maxdetections) > 0:
                firstmaxpos = np.argwhere(maxdetection != 0.)[0][0] + 1

                # the first samples use the previous parameters
                # the next samples use the new parameters
                [self.L, self.K, self.T] = self.nextParams
                self.nextParams = None
                self.timeoffset = t[firstmaxpos]
                result[firstmaxpos:] = np.cos(self.K * (np.exp((t[firstmaxpos:] - self.timeoffset) % self.T / self.L) - 1.))

        return result

class Sweep_Generator_Settings_View_Model(QObject):
    start_frequency_changed = pyqtSignal(float)
    stop_frequency_changed = pyqtSignal(float)
    peiod_changed = pyqtSignal(float)

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.settings = SweepSettings()

    @pyqtProperty(float, notify=start_frequency_changed)
    def start_frequency(self) -> float:
        return self.settings.get("sweep start frequency")

    @start_frequency.setter # type: ignore
    def start_frequency(self, frequency: float):
        self._set("sweep start frequency", frequency, self.start_frequency_changed)

    @pyqtProperty(float, notify=stop_frequency_changed)
    def stop_frequency(self) -> float:
        return self.settings.get("sweep stop frequency")
    
    @stop_frequency.setter # type: ignore
    def stop_frequency(self, frequency: float):
        self._set("sweep stop frequency", frequency, self.stop_frequency_changed)

    @pyqtProperty(float, notify=peiod_changed)
    def period(self) -> float:
        return self.settings.get("sweep period")
    
    @period.setter # type: ignore
    def period(self, period: float):
        self._set("sweep period", period, self.peiod_changed)

    def _set(self, key, value, signal):
        previous = self.settings.get(key)
        try:
            self.settings.set(key, value)
        except SettingsValueError as error:
            logging.getLogger(__name__).warning("Ignoring invalid sweep setting: %s", error)
            return
        current = self.settings.get(key)
        if previous != current:
            signal.emit(current)

    @pyqtProperty(float, constant=True)
    def startFrequencyMinimum(self):
        return self.settings.fields["sweep start frequency"].minimum

    @pyqtProperty(float, constant=True)
    def startFrequencyMaximum(self):
        return self.settings.fields["sweep start frequency"].maximum

    @pyqtProperty(float, constant=True)
    def stopFrequencyMinimum(self):
        return self.settings.fields["sweep stop frequency"].minimum

    @pyqtProperty(float, constant=True)
    def stopFrequencyMaximum(self):
        return self.settings.fields["sweep stop frequency"].maximum

    @pyqtProperty(float, constant=True)
    def periodMinimum(self):
        return self.settings.fields["sweep period"].minimum

    @pyqtProperty(float, constant=True)
    def periodMaximum(self):
        return self.settings.fields["sweep period"].maximum

    def saveState(self, settings):
        self.settings.save(settings)

    def restoreState(self, settings):
        changes = (
            ("sweep start frequency", self.start_frequency_changed),
            ("sweep stop frequency", self.stop_frequency_changed),
            ("sweep period", self.peiod_changed),
        )
        previous = {key: self.settings.get(key) for key, _ in changes}
        # Commit the complete validated candidate before any observer can
        # recompute DSP parameters from a partially restored profile.
        self.settings.restore(settings)
        for key, signal in changes:
            current = self.settings.get(key)
            if previous[key] != current:
                signal.emit(current)
