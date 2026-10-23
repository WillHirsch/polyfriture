"""Global preferences and panel structure validate before touching the UI."""

from types import SimpleNamespace

from PyQt6.QtCore import QByteArray, QObject, QSettings, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMainWindow
import pytest

from polyfriture import dockmanager, settings as settings_module, theme_manager
from polyfriture.channel_configuration import ChannelConfiguration
from polyfriture.dock import DockSettings
from polyfriture.defaults import DEFAULT_DOCKS
from polyfriture.dockmanager import DockLayoutSettings, DockManager
from polyfriture.settings import GlobalSettings, Settings_Dialog
from polyfriture.settings_initialization import initialize_settings
from polyfriture.settings_model import SettingsValueError
from polyfriture.theme_manager import ThemeManager


@pytest.fixture(scope="module")
def application():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def profile(tmp_path):
    return QSettings(str(tmp_path / "profile.ini"), QSettings.Format.IniFormat)


class Audio(QObject):
    """Hardware availability remains the backend's responsibility."""
    configuration_changed = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.channel_configuration = ChannelConfiguration(3, (0,), 8, 1)

    def get_readable_devices_list(self):
        return ["Available device"]

    def get_input_device_identities(self):
        return [("Available device", "Test API")]

    def get_input_device_channel_count(self, index):
        return 8

    def get_readable_current_device(self):
        return 0 if self.channel_configuration is not None else -1

    def select_input_device(self, index, channel_ids=None):
        if channel_ids is not None:
            self.select_channels(channel_ids)
        return True, index

    def select_channels(self, channel_ids):
        previous = self.channel_configuration
        self.channel_configuration = ChannelConfiguration(3, channel_ids, 8, previous.generation + 1)
        self.configuration_changed.emit(self.channel_configuration)
        return self.channel_configuration


@pytest.mark.parametrize("key,value", [
    ("themePreference", 100), ("selectedChannels", []),
    ("selectedChannels", [-1]), ("selectedChannels", [1.5]), ("deviceHostApi", 1),
])
def test_global_restore_recovers_one_invalid_preference(profile, key, value):
    model = GlobalSettings()
    profile.setValue(key, value)
    profile.setValue("deviceName", "A currently unavailable device")
    profile.setValue("future/opaque", QByteArray(b"\x00opaque\xff"))
    with pytest.raises(SettingsValueError):
        model.set(key, value)
    model.restore(profile)
    assert model.get(key) == model.fields[key].default
    assert model.get("deviceName") == "A currently unavailable device"
    assert profile.value(key) == value
    model.save(profile)
    assert profile.value("future/opaque") == QByteArray(b"\x00opaque\xff")


def test_global_dialog_recovers_invalid_theme_but_keeps_valid_channels(
        application, profile, monkeypatch):
    audio = Audio()
    monkeypatch.setattr(settings_module, "AudioBackend", lambda: audio)
    dialog = Settings_Dialog(None)
    try:
        profile.setValue("deviceName", "Available device")
        profile.setValue("deviceHostApi", "Test API")
        profile.setValue("themePreference", "unknown")
        profile.setValue("selectedChannels", [1, 4, 6])
        dialog.restoreState(profile)
        assert dialog.themeButtonGroup.checkedId() == 0
        assert audio.channel_configuration.channel_ids == (1, 4, 6)
        dialog.listWidget_channels.item(2).setCheckState(Qt.CheckState.Checked)
        assert dialog.settings_model.get("selectedChannels") == [1, 2, 4, 6]
    finally:
        dialog.close()
        dialog.deleteLater()


def test_theme_buttons_use_qt_color_scheme_ids(application, monkeypatch):
    monkeypatch.setattr(settings_module, "AudioBackend", Audio)
    dialog = Settings_Dialog(None)
    try:
        for member, button, label in (
            (Qt.ColorScheme.Unknown, dialog.radioButton_themeSystem, "System"),
            (Qt.ColorScheme.Light, dialog.radioButton_themeLight, "Light"),
            (Qt.ColorScheme.Dark, dialog.radioButton_themeDark, "Dark"),
        ):
            assert dialog.themeButtonGroup.id(button) == member.value
            assert button.text() == label
            button.setChecked(True)
            assert dialog.settings_model.get("themePreference") == member.value
    finally:
        dialog.close()
        dialog.deleteLater()


def test_theme_manager_and_dialog_share_assignment_rules(application, profile, monkeypatch):
    profile.setValue("themePreference", 999)
    monkeypatch.setattr(theme_manager, "application_settings", lambda: profile)
    manager = ThemeManager()
    assert manager.themePreference == 0
    assert GlobalSettings.fields["themePreference"] is manager.settings_model.fields["themePreference"]
    changes = []
    manager.theme_changed.connect(changes.append)
    manager.setThemePreference(999)
    assert manager.themePreference == 0
    assert changes == []
    assert profile.value("themePreference") == 999
    manager.setThemePreference(2)
    assert manager.themePreference == 2
    assert profile.value("themePreference") == 2


def test_unavailable_audio_device_does_not_discard_saved_choices(application, profile, monkeypatch):
    monkeypatch.setattr(settings_module, "AudioBackend",
                        lambda: SimpleNamespace(get_readable_devices_list=lambda: [], channel_configuration=None,
                                                configuration_changed=SimpleNamespace(connect=lambda slot: None)))
    profile.setValue("deviceName", "Temporarily unplugged")
    profile.setValue("deviceHostApi", "Test API")
    profile.setValue("selectedChannels", [5, 9])
    dialog = Settings_Dialog(None)
    try:
        dialog.restoreState(profile)
        dialog.saveState(profile)
        assert profile.value("deviceName") == "Temporarily unplugged"
        assert profile.value("deviceHostApi") == "Test API"
        assert profile.value("selectedChannels") == [5, 9]
        assert dialog.comboBox_inputDevice.currentIndex() == -1
        assert not dialog.listWidget_channels.isEnabled()
    finally:
        dialog.close()
        dialog.deleteLater()


@pytest.mark.parametrize("value", [1, "bad/group", ["Dock 1", "Dock 1"], ["Dock 1", None]])
def test_layout_validation_recovers_without_rewriting_profile(profile, value):
    profile.setValue("dockNames", value)
    profile.setValue("widgetIdStack", ["2", "3"])
    model = DockLayoutSettings()
    with pytest.raises(SettingsValueError):
        model.set("dockNames", value)
    model.restore(profile)
    assert model.get("dockNames") == model.fields["dockNames"].default
    assert model.get("widgetIdStack") == [2, 3]
    assert profile.value("dockNames") == value


def test_layout_roundtrip_preserves_explicitly_empty_grid_and_string_stack(profile):
    profile.setValue("dockNames", [])
    profile.setValue("widgetIdStack", ["2", "3"])
    profile.sync()
    reloaded = QSettings(profile.fileName(), QSettings.Format.IniFormat)
    model = DockLayoutSettings()
    model.restore(reloaded)
    assert model.get("dockNames") == []
    assert model.get("widgetIdStack") == [2, 3]


@pytest.mark.parametrize("value", [1.5, 0.0, True, False, QByteArray(b"23"), {"old": 6}])
def test_historical_cleanup_leaves_invalid_stack_types_for_owner_recovery(
        profile, tmp_path, value):
    profile.setValue("Docks/dockNames", [])
    profile.setValue("Docks/widgetIdStack", value)
    profile.setValue("Docks/lastSettings/6/delay_range", 4.5)
    profile.setValue("Docks/lastSettings/2/fftSize", 7)
    source = QSettings(str(tmp_path / "empty-friture.ini"), QSettings.Format.IniFormat)
    source.setFallbacksEnabled(False)
    initialize_settings(profile, source)

    assert profile.value("Docks/widgetIdStack") == value
    assert not profile.contains("Docks/lastSettings/6/delay_range")
    assert profile.value("Docks/lastSettings/2/fftSize") == 7
    profile.beginGroup("Docks")
    try:
        model = DockLayoutSettings()
        recovered = model.restore(profile)
        assert "widgetIdStack" in recovered
        assert model.get("widgetIdStack") == []
        assert profile.value("widgetIdStack") == value
    finally:
        profile.endGroup()


def test_unknown_panel_type_defaults_without_touching_panel_preferences(profile):
    profile.setValue("type", "unknown")
    profile.setValue("settings/timeRange", 10.5)
    model = DockSettings()
    model.restore(profile)
    assert model.get("type") == model.fields["type"].default
    assert profile.value("settings/timeRange") == 10.5


class FakeDock:
    def __init__(self, parent, name, engine, widgetId=None):
        self.name = name
        self.widgetId = widgetId

    def objectName(self):
        return self.name

    def restoreState(self, profile):
        pass


@pytest.mark.parametrize("layout", ["missing", "invalid", "empty"])
def test_dock_manager_recovers_default_panel_types_but_keeps_empty_layout(
        application, profile, monkeypatch, layout):
    monkeypatch.setattr(dockmanager, "Dock", FakeDock)
    window = QMainWindow()
    window.qml_engine = object()
    manager = DockManager(window, None)
    if layout == "invalid":
        profile.setValue("dockNames", ["invalid/name"])
    elif layout == "empty":
        profile.setValue("dockNames", [])
    profile.setValue("Dock 0/type", 8)
    profile.setValue("extension/opaque", QByteArray(b"retained"))
    profile.sync()
    reloaded = QSettings(profile.fileName(), QSettings.Format.IniFormat)
    before = {key: reloaded.value(key) for key in reloaded.allKeys()}
    try:
        manager.restoreState(reloaded)
        expected = [] if layout == "empty" else DEFAULT_DOCKS
        assert [dock.widgetId for dock in manager.docks] == expected
        assert [dock.objectName() for dock in manager.docks] == [
            "Dock %d" % i for i in range(len(expected))]
        assert {key: reloaded.value(key) for key in reloaded.allKeys()} == before
    finally:
        window.close()
        window.deleteLater()


def test_dock_manager_recovers_cache_and_creates_unique_name(application, profile, monkeypatch):
    monkeypatch.setattr(dockmanager, "Dock", FakeDock)
    window = QMainWindow()
    window.qml_engine = object()
    manager = DockManager(window, None)
    profile.setValue("dockNames", ["Display", "Dock 7"])
    profile.setValue("Display/type", 2)
    profile.setValue("Dock 7/type", "not a type")
    profile.setValue("widgetIdStack", ["2"])
    profile.setValue("lastSettings/not a type/type", 8)
    profile.setValue("lastSettings/999/type", 8)
    profile.setValue("lastSettings/2/settings/opaque", QByteArray(b"future"))
    try:
        manager.restoreState(profile)
        assert [dock.widgetId for dock in manager.docks] == [2, 1]
        assert manager.last_widget_stack == [2]
        assert list(manager.last_settings) == [2]
        assert manager.last_settings[2].value("settings/opaque") == QByteArray(b"future")
        manager.new_dock()
        assert [dock.objectName() for dock in manager.docks] == ["Display", "Dock 7", "Dock 8"]
        assert manager.docks[-1].widgetId == 2
        assert profile.value("lastSettings/not a type/type") == 8
    finally:
        window.close()
        window.deleteLater()
