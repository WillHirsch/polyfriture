#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2013 Timothée Lecomte
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
import re

from PyQt6 import QtCore
from PyQt6.QtWidgets import QMainWindow
from polyfriture.application import temporary_settings
from polyfriture.defaults import DEFAULT_DOCKS
from polyfriture.dock import Dock, DockSettings, parse_widget_id
from polyfriture.settings_model import SettingsModel, SettingsValueError, ValueSetting
from polyfriture.tilelayout import TileLayout

from typing import Dict, List, Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from polyfriture.analyzer import Friture


def _dock_names(value):
    # Qt reloads an empty INI list as None, and a single name may be a string.
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("dock names must be a list")
    if any(not isinstance(name, str) or not name or "/" in name or "\\" in name
           or "\0" in name or name in {"lastSettings", "dockNames", "widgetIdStack"} for name in value):
        raise ValueError("dock names must be nonempty settings group names")
    if len(set(value)) != len(value):
        raise ValueError("dock names must be unique")
    return value


def _widget_stack(value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("panel history must be a list")
    return [parse_widget_id(identifier) for identifier in value]


class DockLayoutSettings(SettingsModel):
    fields = {
        "dockNames": ValueSetting(["Dock %d" % i for i in range(len(DEFAULT_DOCKS))],
                                  decode=_dock_names),
        "widgetIdStack": ValueSetting([], decode=_widget_stack),
    }


class DockManager(QtCore.QObject):

    def __init__(self, parent: 'Friture', dock_layout: TileLayout) -> None:
        super().__init__(parent)
        self._parent = parent

        self.logger = logging.getLogger(__name__)
        self.settings_model = DockLayoutSettings()

        # the parent must of the QMainWindow so that docks are created as children of it
        assert isinstance(parent, QMainWindow)

        self.docks: List[Dock] = []
        self.last_settings: Dict[int, QtCore.QSettings] = {}
        self.last_widget_stack: List[int] = []

        self.dock_layout = dock_layout

    # slot
    def new_dock(self) -> None:
        # the dock objectName is unique
        docknames = [dock.objectName() for dock in self.docks]
        dockindexes = [int(match.group(1)) for name in docknames
                       if (match := re.fullmatch(r"Dock (\d+)", name))]
        if len(dockindexes) == 0:
            index = 1
        else:
            index = max(dockindexes) + 1
        name = "Dock %d" % index

        widget_id: Optional[int] = None
        settings: Optional[QtCore.QSettings] = None
        if self.last_widget_stack:
            widget_id = self.last_widget_stack.pop()
            settings = self.last_settings.get(widget_id)

        new_dock = Dock(self._parent, name, self._parent.qml_engine, widget_id)
        if settings is not None:
            new_dock.restoreState(settings)

        self.docks += [new_dock]

    # slot
    def close_dock(self, dock: Dock) -> None:
        settings = temporary_settings()
        dock.saveState(settings)
        assert dock.widgetId is not None # true but mypy can't prove it
        self.last_settings[dock.widgetId] = settings
        self.last_widget_stack.append(dock.widgetId)

        self.docks.remove(dock)
        dock.cleanup()
    
    def movePrevious(self, dock):
        i = self.docks.index(dock)
        if i > 0:
            self.dock_layout.movePrevious(i)
            self.docks.insert(i-1, self.docks.pop(i))

    def moveNext(self, dock):
        i = self.docks.index(dock)
        if i < len(self.docks) - 1:
            self.dock_layout.moveNext(i)
            self.docks.insert(i+1, self.docks.pop(i))

    def saveState(self, settings):
        docknames = [dock.objectName() for dock in self.docks]
        self.settings_model.update({"dockNames": docknames, "widgetIdStack": self.last_widget_stack})
        self.settings_model.save(settings)
        for dock in self.docks:
            settings.beginGroup(dock.objectName())
            dock.saveState(settings)
            settings.endGroup()

        settings.beginGroup("lastSettings")
        for widgetId, widgetSettings in self.last_settings.items():
            settings.beginGroup(str(widgetId))
            for key in widgetSettings.allKeys():
                settings.setValue(key, widgetSettings.value(key))
            settings.endGroup()
        settings.endGroup()

    def restoreState(self, settings):
        recovered = self.settings_model.restore(settings)
        if settings.contains("dockNames") and "dockNames" not in recovered:
            docknames = self.settings_model.get("dockNames")
            # list of docks
            self.docks = []
            for name in docknames:
                settings.beginGroup(name)
                dock_settings = DockSettings()
                dock_settings.restore(settings)
                widgetId = dock_settings.get("type")
                dock = Dock(self.parent(), name, self.parent().qml_engine, widgetId)
                dock.restoreState(settings)
                settings.endGroup()
                self.docks.append(dock)
        else:
            self.logger.info("Display the default set of docks")
            self.docks = [Dock(self.parent(), "Dock %d" % (i), self.parent().qml_engine, widgetId=widget_type) for i, widget_type in enumerate(DEFAULT_DOCKS)]

        self.last_widget_stack = self.settings_model.get("widgetIdStack")
        self.last_settings = {}
        settings.beginGroup("lastSettings")
        for strId in settings.childGroups():
            try:
                widget_id = parse_widget_id(strId)
            except (SettingsValueError, ValueError):
                self.logger.warning("Ignoring invalid cached panel type: %r", strId)
                continue
            settings.beginGroup(strId)
            widgetSettings = temporary_settings()
            for key in settings.allKeys():
                widgetSettings.setValue(key, settings.value(key))
            self.last_settings[widget_id] = widgetSettings
            settings.endGroup()
        settings.endGroup()

    def canvasUpdate(self):
        if self._parent.isVisible():
            for dock in self.docks:
                dock.canvasUpdate()

    def pause(self):
        for dock in self.docks:
            try:
                dock.pause()
            except AttributeError:
                pass

    def restart(self):
        for dock in self.docks:
            try:
                dock.restart()
            except AttributeError:
                pass
