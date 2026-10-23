#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2025 Timothée Lecomte
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

from PyQt6 import QtCore
from PyQt6.QtCore import QObject, pyqtProperty  # type: ignore

from polyfriture.main_toolbar_view_model import MainToolbarViewModel

class MainWindowViewModel(QtCore.QObject):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._toolbar_view_model = MainToolbarViewModel(self)

    @pyqtProperty(QObject, constant=True) # type: ignore
    def toolbar_view_model(self):
        return self._toolbar_view_model
