#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2009 Timoth�e Lecomte

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

import sys
from PyQt6 import QtGui, QtCore, QtWidgets
import sounddevice
import numpy
import friture_monitor.friture_rc
import friture_monitor
from friture_monitor.statisticswidget import StatisticsWidget
from friture_monitor.application import APPLICATION_NAME, ISSUES_URL, PROJECT_URL

aboutText = f"""
<p><b>{APPLICATION_NAME} %s</b></p>
<p>A fork of Friture for monitoring audio sources.</p>
<p>Based on the Friture release dated %s. Licensed under GPLv3.</p>
<p>Project: <a href="{PROJECT_URL}">{APPLICATION_NAME} on GitHub</a>.</p>
<p>Submit ideas and bug reports as <a href="{ISSUES_URL}">Issues</a>.</p>
<p>Upstream: <a href="https://friture.org">Friture homepage</a> and
<a href="https://github.com/tlecomte/friture">Friture source code</a>.</p>
<p>Splash screen photo credit: <a href="https://www.flickr.com/photos/visual_dichotomy/3623619145/">visual.dichotomy</a> (CC BY 2.0)</p>
<p>This application runs thanks to the following external projects:</p>

<ul>
        <li>Python %s</li>
        <li>PyQt %s (Qt %s)</li>
        <li>Python-sounddevice %s (%s)</li>
        <li>Numpy %s</li>
</ul>
""" % (friture_monitor.__version__,
       friture_monitor.__releasedate__,
       "%d.%d" % (sys.version_info.major, sys.version_info.minor),
       QtCore.PYQT_VERSION_STR,
       QtCore.qVersion(),
       sounddevice.__version__,
       sounddevice.get_portaudio_version()[1],
       numpy.__version__)


class About_Dialog(QtWidgets.QDialog):

    def __init__(self, parent, timer):
        super().__init__(parent)

        self.setObjectName("About_Dialog")
        self.resize(400, 300)
        self.setWindowTitle("About " + APPLICATION_NAME)

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/images-src/window-icon.svg"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
        self.setWindowIcon(icon)
        self.verticalLayout = QtWidgets.QVBoxLayout(self)
        self.verticalLayout.setObjectName("verticalLayout")

        self.tabWidget = QtWidgets.QTabWidget(self)
        self.tabWidget.setObjectName("tabWidget")
        self.aboutTab = QtWidgets.QWidget()
        self.aboutTab.setObjectName("aboutTab")
        self.horizontalLayout = QtWidgets.QHBoxLayout(self.aboutTab)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label_2 = QtWidgets.QLabel(self.aboutTab)
        self.label_2.setMinimumSize(QtCore.QSize(128, 128))
        self.label_2.setMaximumSize(QtCore.QSize(128, 128))
        self.label_2.setPixmap(QtGui.QPixmap(":/images-src/window-icon.svg"))
        self.label_2.setScaledContents(True)
        self.label_2.setObjectName("label_2")
        self.horizontalLayout.addWidget(self.label_2)
        self.label = QtWidgets.QLabel(self.aboutTab)
        self.label.setOpenExternalLinks(True)
        self.label.setObjectName("label")
        self.label.setText(aboutText)

        self.horizontalLayout.addWidget(self.label)
        self.tabWidget.addTab(self.aboutTab, "About")

        self.tab_stats = StatisticsWidget(self, timer)
        self.tabWidget.addTab(self.tab_stats, "Statistics")

        self.tabWidget.setCurrentIndex(0)

        self.buttonBox = QtWidgets.QDialogButtonBox(self)
        self.buttonBox.setOrientation(QtCore.Qt.Orientation.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.StandardButton.Close)
        self.buttonBox.setObjectName("buttonBox")

        self.verticalLayout.addWidget(self.tabWidget)
        self.verticalLayout.addWidget(self.buttonBox)

        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        QtCore.QMetaObject.connectSlotsByName(self)
