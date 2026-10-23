"""Restore legitimate Qt INI representations of empty docks and cached widgets."""

from types import SimpleNamespace
import logging

from PyQt6 import sip
from PyQt6.QtCore import QObject, QSettings

from polyfriture.dockmanager import DockLayoutSettings, DockManager
from polyfriture.generators.sweep import Sweep_Generator_Settings_View_Model


def test_restore_empty_docks_and_multiple_cached_widget_ids(tmp_path):
    settings_file = tmp_path / "settings.ini"
    settings_file.write_text(
        "[Docks]\n"
        "dockNames=@Invalid()\n"
        "widgetIdStack=1, 2\n"
        "lastSettings\\1\\timeRange=25\n"
        "lastSettings\\2\\fftSize=8\n",
        encoding="utf-8",
    )
    settings = QSettings(str(settings_file), QSettings.Format.IniFormat)
    settings.beginGroup("Docks")
    manager = SimpleNamespace(last_settings={}, settings_model=DockLayoutSettings(),
                              logger=logging.getLogger(__name__))

    try:
        DockManager.restoreState(manager, settings)

        assert manager.docks == []
        assert manager.last_widget_stack == [1, 2]
        assert all(type(widget_id) is int for widget_id in manager.last_widget_stack)
        assert manager.last_settings[1].value("timeRange", type=float) == 25.0
        assert manager.last_settings[2].value("fftSize", type=int) == 8
    finally:
        for cache in manager.last_settings.values():
            sip.delete(cache)
        settings.endGroup()


def test_restore_fractional_sweep_frequencies_from_ini(tmp_path):
    settings_file = tmp_path / "sweep.ini"
    settings_file.write_text(
        "[General]\n"
        "sweep%20start%20frequency=20.5\n"
        "sweep%20stop%20frequency=21999.5\n",
        encoding="utf-8",
    )
    settings = QSettings(str(settings_file), QSettings.Format.IniFormat)
    parent = QObject()
    model = Sweep_Generator_Settings_View_Model(parent)

    model.restoreState(settings)

    assert model.start_frequency == 20.5
    assert model.stop_frequency == 21999.5
