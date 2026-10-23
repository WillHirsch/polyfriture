#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2024 Timothée Lecomte
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

from PyQt6.QtCore import QObject, pyqtSignal, pyqtProperty, QRectF  # type: ignore
from PyQt6.QtQuick import QQuickPaintedItem
from PyQt6.QtGui import QPainter
from polyfriture.spectrogram_item_data import SpectrogramImageData

class SpectrogramItem(QQuickPaintedItem):
    curveChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAntialiasing(True)

        self._curve = None
        self.widthChanged.connect(self.updateScreenSize)
        self.heightChanged.connect(self.updateScreenSize)

    @pyqtProperty(QObject, notify=curveChanged)
    def curve(self) -> SpectrogramImageData | None:
        return self._curve

    @curve.setter
    def curve(self, curve: SpectrogramImageData | None) -> None:
        if self._curve != curve:
            if self._curve is not None:
                self._curve.data_changed.disconnect(self.update)
            self._curve = curve
            if curve is not None:
                curve.data_changed.connect(self.update)
                self.updateScreenSize()
            self.curveChanged.emit()
            if self.window():
                self.window().update()

    def updateScreenSize(self) -> None:
        if self._curve is not None:
            self._curve.update_screen_size(self.width(), self.height())

    def paint(self, painter: QPainter | None) -> None:  # type: ignore
        if self._curve is None or painter is None:
            return
        pixmap_source_rect = self._curve.pixmap_source_rect(self._curve.paint_time)
        painter.drawPixmap(
            QRectF(0, 0, self.width(), self.height()),
            self._curve.pixmap(),
            pixmap_source_rect)
