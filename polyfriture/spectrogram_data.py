#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2022 Timothée Lecomte
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

from polyfriture.scope_data import Scope_Data
from PyQt6.QtCore import pyqtProperty, pyqtSignal

class Spectrogram_Data(Scope_Data):
    rotated_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rotated = False

    @pyqtProperty(bool, notify=rotated_changed)
    def rotated(self):
        return self._rotated

    @rotated.setter
    def rotated(self, rotated):
        if self._rotated != rotated:
            self._rotated = rotated
            self.rotated_changed.emit(rotated)
