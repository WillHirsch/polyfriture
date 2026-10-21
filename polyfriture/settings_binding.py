"""Bind Qt controls to the settings definitions that own their values."""

import logging
from typing import Any, Callable

from polyfriture.settings_model import ChoiceSetting, NumericSetting, SettingsModel, SettingsValueError


logger = logging.getLogger(__name__)


def _connect(signal: Any, widget: Any, model: SettingsModel, key: str,
             callback: Callable[[Any], Any], restore: Callable[[Any], Any]) -> None:
    def changed(value: Any) -> None:
        try:
            value = model.set(key, value)
        except SettingsValueError as error:
            logger.warning("Ignoring invalid setting assignment: %s", error)
            blocked = widget.blockSignals(True)
            try:
                restore(model.get(key))
            finally:
                widget.blockSignals(blocked)
            return
        callback(value)
    signal.connect(changed)


def bind_spinbox(widget: Any, model: SettingsModel, key: str,
                 callback: Callable[[Any], Any]) -> None:
    field = model.fields[key]
    if not isinstance(field, NumericSetting):
        raise TypeError(f"{key} requires a numeric setting")
    widget.setRange(field.minimum, field.maximum)
    widget.setValue(model.get(key))
    _connect(widget.valueChanged, widget, model, key, callback, widget.setValue)


def bind_combobox(widget: Any, model: SettingsModel, key: str,
                  callback: Callable[[Any], Any]) -> None:
    widget.clear()
    field = model.fields[key]
    if not isinstance(field, ChoiceSetting):
        raise TypeError(f"{key} requires an indexed choice setting")
    widget.addItems(list(field.labels))
    widget.setCurrentIndex(model.get(key))
    _connect(widget.currentIndexChanged, widget, model, key, callback, widget.setCurrentIndex)


def bind_checkbox(widget: Any, model: SettingsModel, key: str,
                  callback: Callable[[Any], Any]) -> None:
    widget.setChecked(model.get(key))
    _connect(widget.toggled, widget, model, key, callback, widget.setChecked)
