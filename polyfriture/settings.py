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

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import pyqtSignal
from polyfriture.audiobackend import AudioBackend
from polyfriture.channel_grid_settings import CHANNEL_GRID_COLUMNS
from polyfriture.ui_settings import Ui_Settings_Dialog
from polyfriture.settings_binding import bind_spinbox
from polyfriture.settings_model import IntSetting, SettingsModel, ValueSetting
from polyfriture.theme_manager import THEME_LABELS, THEME_SETTING


def _selected_channels(value):
    # QSettings INI files can reload a singleton list as an integer/string.
    if isinstance(value, (int, str)) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("select at least one channel")
    channel = IntSetting(0, minimum=0)
    return sorted({channel.coerce(identifier) for identifier in value})


class GlobalSettings(SettingsModel):
    """Requested audio selection and the dialog's display preferences."""

    fields = {
        "deviceName": ValueSetting(""),
        "deviceHostApi": ValueSetting(""),
        "selectedChannels": ValueSetting([0], decode=_selected_channels),
        "themePreference": THEME_SETTING,
        "channelGridColumns": CHANNEL_GRID_COLUMNS,
    }


NO_INPUT_STATUS = "No usable audio input is active. Choose an input device, or reconnect it and restart."


class Settings_Dialog(QtWidgets.QDialog, Ui_Settings_Dialog):
    theme_preference_changed = pyqtSignal(int)
    channel_grid_columns_changed = pyqtSignal(int)

    def __init__(self, parent):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.settings_model = GlobalSettings()
        self.setupUi(self)
        for button, scheme in (
                (self.radioButton_themeSystem, QtCore.Qt.ColorScheme.Unknown),
                (self.radioButton_themeLight, QtCore.Qt.ColorScheme.Light),
                (self.radioButton_themeDark, QtCore.Qt.ColorScheme.Dark)):
            self.themeButtonGroup.setId(button, scheme.value)
            button.setText(THEME_LABELS[scheme])
        self.themeButtonGroup.idToggled.connect(self.theme_preference_toggled)
        bind_spinbox(self.spinBox_channelGridColumns, self.settings_model,
                     "channelGridColumns", self.channel_grid_columns_changed.emit)

        backend = AudioBackend()
        devices = backend.get_readable_devices_list()
        self._input_identities = backend.get_input_device_identities() if devices else []
        self.comboBox_inputDevice.addItems(devices)
        self._refresh_input_ui()
        self._adopt_current_input()
        self._set_input_status(NO_INPUT_STATUS if backend.channel_configuration is None else "")
        self.comboBox_inputDevice.activated.connect(self.input_device_changed)
        self.listWidget_channels.itemChanged.connect(self.channels_changed)
        backend.configuration_changed.connect(self._input_configuration_changed)

    def _set_input_status(self, message):
        self.label_inputStatus.setText(message)
        self.label_inputStatus.setVisible(bool(message))

    def _active_input_description(self):
        if AudioBackend().channel_configuration is None:
            return "No audio input is active."
        return f"Using {self.comboBox_inputDevice.currentText()}."

    def _input_configuration_changed(self, configuration):
        self._refresh_input_ui()

    def _refresh_input_ui(self):
        backend = AudioBackend()
        configuration = backend.channel_configuration
        index = backend.get_readable_current_device() if configuration is not None else -1
        with QtCore.QSignalBlocker(self.comboBox_inputDevice):
            self.comboBox_inputDevice.setCurrentIndex(index)
        with QtCore.QSignalBlocker(self.listWidget_channels):
            count = configuration.device_channel_count if configuration is not None else 0
            if self.listWidget_channels.count() != count:
                self.listWidget_channels.clear()
                for channel_id in range(count):
                    item = QtWidgets.QListWidgetItem(f"Channel {channel_id + 1}")
                    item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, channel_id)
                    self.listWidget_channels.addItem(item)
            selected = set(configuration.channel_ids) if configuration is not None else set()
            for row in range(count):
                item = self.listWidget_channels.item(row)
                item.setCheckState(QtCore.Qt.CheckState.Checked if row in selected else QtCore.Qt.CheckState.Unchecked)
            self.listWidget_channels.setEnabled(configuration is not None)

    def _adopt_current_input(self):
        """An explicit user choice replaces any unavailable saved preference."""
        backend = AudioBackend()
        configuration = backend.channel_configuration
        if configuration is not None:
            name, api = self._input_identities[backend.get_readable_current_device()]
            self.settings_model.update({"deviceName": name, "deviceHostApi": api,
                                        "selectedChannels": list(configuration.channel_ids)})

    def input_device_changed(self, index):
        if index < 0:
            return
        requested = self.comboBox_inputDevice.itemText(index)
        success, _ = AudioBackend().select_input_device(index)
        self._refresh_input_ui()
        if success:
            self._adopt_current_input()
            self._set_input_status("")
        else:
            self._set_input_status(f"Could not open {requested}. {self._active_input_description()} "
                                   "The previous input selection is retained.")

    def channels_changed(self, item):
        channels = [self.listWidget_channels.item(row).data(QtCore.Qt.ItemDataRole.UserRole)
                    for row in range(self.listWidget_channels.count())
                    if self.listWidget_channels.item(row).checkState() == QtCore.Qt.CheckState.Checked]
        if not channels:
            self._refresh_input_ui()
            self._set_input_status("Select at least one channel.")
            return
        try:
            channels = self.settings_model.fields["selectedChannels"].coerce(channels)
            AudioBackend().select_channels(channels)
        except Exception:
            self.logger.exception("Failed to change input channels")
            self._refresh_input_ui()
            self._set_input_status("Could not change channels. The previous input selection is retained.")
            return
        self._adopt_current_input()
        self._set_input_status("")

    def theme_preference_toggled(self, button_id: int, checked: bool) -> None:
        if checked:
            button_id = self.settings_model.set("themePreference", button_id)
            self.theme_preference_changed.emit(button_id)

    def saveState(self, settings):
        # Keep unavailable preferences until the user explicitly edits audio
        # selection; silently substituting a fallback would lose their profile.
        self.settings_model.update({"themePreference": self.themeButtonGroup.checkedId(),
                                    "channelGridColumns": self.spinBox_channelGridColumns.value()})
        self.settings_model.save(settings)

    def restoreState(self, settings):
        self.settings_model.restore(settings)
        columns = self.settings_model.get("channelGridColumns")
        with QtCore.QSignalBlocker(self.spinBox_channelGridColumns):
            self.spinBox_channelGridColumns.setValue(columns)
        self.channel_grid_columns_changed.emit(columns)
        self.themeButtonGroup.button(self.settings_model.get("themePreference")).setChecked(True)
        self._restore_input()

    def _restore_input(self):
        name = self.settings_model.get("deviceName")
        api = self.settings_model.get("deviceHostApi")
        if not name:
            self._adopt_current_input()
            self._refresh_input_ui()
            self._set_input_status(NO_INPUT_STATUS if AudioBackend().channel_configuration is None else "")
            return
        matches = [index for index, (candidate, host_api) in enumerate(self._input_identities)
                   if candidate == name and (not api or host_api == api)]
        if len(matches) != 1:
            reason = "unavailable" if not matches else "ambiguous"
            self._refresh_input_ui()
            self._set_input_status(f"Saved input {name} is {reason}. {self._active_input_description()} "
                                   "Its selection is retained for a later start. Choose a device to replace the saved preference.")
            return
        index = matches[0]
        backend = AudioBackend()
        wanted = self.settings_model.get("selectedChannels")
        count = backend.get_input_device_channel_count(index)
        channels = [channel for channel in wanted if channel < count] or [0]
        success, _ = backend.select_input_device(index, channel_ids=channels)
        self._refresh_input_ui()
        if not success:
            self._set_input_status(f"Could not open saved input {name}. {self._active_input_description()} "
                                   "Its selection is retained for a later start.")
        elif channels != wanted:
            self._set_input_status("Some saved channels are unavailable. The active channels are checked; "
                                   "the saved selection is retained until you edit it.")
        else:
            self._set_input_status("")
