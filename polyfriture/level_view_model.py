#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2021 Timothée Lecomte
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

from PyQt6.QtCore import QObject, pyqtProperty

from polyfriture.ballistic_peak import BallisticPeak
from polyfriture.level_data import LevelData
from polyfriture.scope_data import Scope_Data


class LevelViewModel(Scope_Data):
    """One meter's live, slow-label and peak-hold state; axes belong to the panel."""

    def __init__(self, parent=None, *, axes=None):
        super().__init__(parent, axes=axes)
        self._level_data = LevelData(self)
        self._level_data_slow = LevelData(self)
        self._level_data_ballistic = BallisticPeak(self)
        for data in (self._level_data, self._level_data_slow):
            data.level_rms = -300.
            data.level_max = -600.

    @pyqtProperty(QObject, constant=True)
    def level_data(self):
        return self._level_data

    @pyqtProperty(QObject, constant=True)
    def level_data_slow(self):
        return self._level_data_slow

    @pyqtProperty(QObject, constant=True)
    def level_data_ballistic(self):
        return self._level_data_ballistic
