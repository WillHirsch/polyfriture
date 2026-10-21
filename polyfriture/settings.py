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

import sys
import logging
import re

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import pyqtSignal  # type: ignore
from polyfriture.audiobackend import AudioBackend
from polyfriture.application import APPLICATION_DISPLAY_NAME
from polyfriture.main_toolbar_view_model import MainToolbarViewModel
from polyfriture.ui_settings import Ui_Settings_Dialog
from polyfriture.settings_model import IntSetting, SettingsModel, ValueSetting
from polyfriture.theme_manager import THEME_LABELS, THEME_SETTING


# These IDs are persisted by older settings dialogs as well as this one.
INPUT_TYPE_IDS = {"Single channel": -2, "Two channels": -3}


def _input_type(value):
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value):
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("input type must be an integer")
    if value == 0:  # Historical default before an input type was saved.
        return INPUT_TYPE_IDS["Single channel"]
    if value not in INPUT_TYPE_IDS.values():
        raise ValueError("unknown input type")
    return value


class GlobalSettings(SettingsModel):
    """Audio preferences and the settings dialog's theme."""

    fields = {
        "deviceName": ValueSetting(""),
        "firstChannel": IntSetting(0, minimum=0),
        "secondChannel": IntSetting(0, minimum=0),
        "duoInput": ValueSetting(INPUT_TYPE_IDS["Single channel"], decode=_input_type),
        "themePreference": THEME_SETTING,
    }

no_input_device_title = "No audio input device found"

no_input_device_message = f"""No audio input device has been found.

{APPLICATION_DISPLAY_NAME} needs at least one input device. Please check your audio configuration.

{APPLICATION_DISPLAY_NAME} will now exit.
"""


class Settings_Dialog(QtWidgets.QDialog, Ui_Settings_Dialog):
    theme_preference_changed = pyqtSignal(int)

    def __init__(self, parent, toolbar_view_model: MainToolbarViewModel):
        QtWidgets.QDialog.__init__(self, parent)
        Ui_Settings_Dialog.__init__(self)

        self.logger = logging.getLogger(__name__)
        self.settings_model = GlobalSettings()

        self._toolbar_view_model = toolbar_view_model

        # Setup the user interface
        self.setupUi(self)

        for button, scheme in (
                (self.radioButton_themeSystem, QtCore.Qt.ColorScheme.Unknown),
                (self.radioButton_themeLight, QtCore.Qt.ColorScheme.Light),
                (self.radioButton_themeDark, QtCore.Qt.ColorScheme.Dark)):
            self.themeButtonGroup.setId(button, scheme.value)
            button.setText(THEME_LABELS[scheme])
        for button, (label, identifier) in zip((self.radioButton_single, self.radioButton_duo),
                                              INPUT_TYPE_IDS.items()):
            self.inputTypeButtonGroup.setId(button, identifier)
            button.setText(label)

        # Theme controls work even when no audio hardware is available.
        self.themeButtonGroup.idToggled.connect(self.theme_preference_toggled)

        devices = AudioBackend().get_readable_devices_list()

        if devices == []:
            # no audio input device
            application = QtWidgets.QApplication.instance()
            assert isinstance(application, QtWidgets.QApplication)
            if application.platformName() == "offscreen":
                # Headless (e.g. the CI smoke test).
                # Log and continue with an empty device set instead of exiting,
                # for validation purposes.
                self.logger.warning("No audio input device available; continuing in headless mode")
                return
            # display a message and exit
            QtWidgets.QMessageBox.critical(self, no_input_device_title, no_input_device_message)
            QtCore.QTimer.singleShot(0, self.exitOnInit)
            sys.exit(1)
            return

        for device in devices:
            self.comboBox_inputDevice.addItem(device)

        channels = AudioBackend().get_readable_current_channels()
        for channel in channels:
            self.comboBox_firstChannel.addItem(channel)
            self.comboBox_secondChannel.addItem(channel)

        current_device = AudioBackend().get_readable_current_device()
        self.comboBox_inputDevice.setCurrentIndex(current_device)

        first_channel = AudioBackend().get_current_first_channel()
        self.comboBox_firstChannel.setCurrentIndex(first_channel)
        second_channel = AudioBackend().get_current_second_channel()
        self.comboBox_secondChannel.setCurrentIndex(second_channel)

        # signals
        self.comboBox_inputDevice.currentIndexChanged.connect(self.input_device_changed)
        self.comboBox_firstChannel.activated.connect(self.first_channel_changed)
        self.comboBox_secondChannel.activated.connect(self.second_channel_changed)
        self.radioButton_single.toggled.connect(self.single_input_type_selected)
        self.radioButton_duo.toggled.connect(self.duo_input_type_selected)

    # slot
    # used when no audio input device has been found, to exit immediately
    def exitOnInit(self):
        QtWidgets.QApplication.instance().quit()

    # slot
    def input_device_changed(self, index):
        if index < 0:
            return
        self._toolbar_view_model.recording = False

        success, index = AudioBackend().select_input_device(index)

        self.comboBox_inputDevice.setCurrentIndex(index)
        self.settings_model.set("deviceName", self.comboBox_inputDevice.currentText())

        if not success:
            # Note: the error message is a child of the settings dialog, so that
            # that dialog remains on top when the error message is closed
            error_message = QtWidgets.QErrorMessage(self)
            error_message.setWindowTitle("Input device error")
            error_message.showMessage("Impossible to use the selected input device, reverting to the previous one")

        # reset the channels
        channels = AudioBackend().get_readable_current_channels()

        self.comboBox_firstChannel.clear()
        self.comboBox_secondChannel.clear()

        for channel in channels:
            self.comboBox_firstChannel.addItem(channel)
            self.comboBox_secondChannel.addItem(channel)

        first_channel = AudioBackend().get_current_first_channel()
        self.comboBox_firstChannel.setCurrentIndex(first_channel)
        second_channel = AudioBackend().get_current_second_channel()
        self.comboBox_secondChannel.setCurrentIndex(second_channel)

        self._toolbar_view_model.recording = True

    # slot
    def first_channel_changed(self, index):
        if index < 0:
            return
        self.settings_model.set("firstChannel", index)
        self._toolbar_view_model.recording = False

        success, index = AudioBackend().select_first_channel(index)

        self.comboBox_firstChannel.setCurrentIndex(index)
        self.settings_model.set("firstChannel", index)

        if not success:
            # Note: the error message is a child of the settings dialog, so that
            # that dialog remains on top when the error message is closed
            error_message = QtWidgets.QErrorMessage(self)
            error_message.setWindowTitle("Input device error")
            error_message.showMessage("Impossible to use the selected channel as the first channel, reverting to the previous one")

        self._toolbar_view_model.recording = True

    # slot
    def second_channel_changed(self, index):
        if index < 0:
            return
        self.settings_model.set("secondChannel", index)
        self._toolbar_view_model.recording = False

        success, index = AudioBackend().select_second_channel(index)

        self.comboBox_secondChannel.setCurrentIndex(index)
        self.settings_model.set("secondChannel", index)

        if not success:
            # Note: the error message is a child of the settings dialog, so that
            # that dialog remains on top when the error message is closed
            error_message = QtWidgets.QErrorMessage(self)
            error_message.setWindowTitle("Input device error")
            error_message.showMessage("Impossible to use the selected channel as the second channel, reverting to the previous one")

        self._toolbar_view_model.recording = True

    # slot
    def single_input_type_selected(self, checked):
        if checked:
            self.settings_model.set("duoInput", INPUT_TYPE_IDS["Single channel"])
            self.groupBox_second.setEnabled(False)
            AudioBackend().set_single_input()
            self.logger.info("Switching to single input")

    # slot
    def duo_input_type_selected(self, checked):
        if checked:
            self.settings_model.set("duoInput", INPUT_TYPE_IDS["Two channels"])
            self.groupBox_second.setEnabled(True)
            AudioBackend().set_duo_input()
            self.logger.info("Switching to difference between two inputs")

    # slot
    def theme_preference_toggled(self, button_id: int, checked: bool) -> None:
        if checked:
            button_id = self.settings_model.set("themePreference", button_id)
            self.theme_preference_changed.emit(button_id)
            self.logger.info("Theme preference changed to: %d", button_id)

    # method
    def saveState(self, settings):
        # for the input device, we search by name instead of index, since
        # we do not know if the device order stays the same between sessions
        values = {
            "duoInput": self.inputTypeButtonGroup.checkedId(),
            "themePreference": self.themeButtonGroup.checkedId(),
        }
        if self.comboBox_inputDevice.currentIndex() >= 0:
            values.update(deviceName=self.comboBox_inputDevice.currentText(),
                          firstChannel=self.comboBox_firstChannel.currentIndex(),
                          secondChannel=self.comboBox_secondChannel.currentIndex())
        self.settings_model.update(values)
        self.settings_model.save(settings)

    # method
    def restoreState(self, settings):
        self.settings_model.restore(settings)
        device_name = self.settings_model.get("deviceName")
        device_index = self.comboBox_inputDevice.findText(device_name)
        # change the device only if it exists in the device list
        if device_index >= 0:
            self.comboBox_inputDevice.setCurrentIndex(device_index)
            # The backend decides whether a valid channel/device is available.
            self.first_channel_changed(self.settings_model.get("firstChannel"))
            self.second_channel_changed(self.settings_model.get("secondChannel"))
        duo_input_id = self.settings_model.get("duoInput")
        self.inputTypeButtonGroup.button(duo_input_id).setChecked(True)
        theme_preference_id = self.settings_model.get("themePreference")
        self.themeButtonGroup.button(theme_preference_id).setChecked(True)
