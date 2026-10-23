"""The channel-grid preference has one contract for saved and live values."""

from types import SimpleNamespace

from PyQt6.QtCore import QSettings
import pytest

from polyfriture import settings as settings_module
from polyfriture.channel_grid_settings import CHANNEL_GRID_COLUMNS
from polyfriture.settings import GlobalSettings, Settings_Dialog
from polyfriture.settings_model import QT_INT_MAX, SettingsValueError
from polyfriture.store import Store


@pytest.fixture
def profile(tmp_path):
    return QSettings(str(tmp_path / "grid.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def dialog(monkeypatch):
    # Display preferences work without touching real audio devices or settings.
    monkeypatch.setattr(settings_module, "AudioBackend", lambda: SimpleNamespace(
        get_readable_devices_list=lambda: [], channel_configuration=None,
        configuration_changed=SimpleNamespace(connect=lambda slot: None)))
    value = Settings_Dialog(None)
    yield value
    value.close()
    value.deleteLater()


def test_grid_columns_share_one_setting_contract():
    assert GlobalSettings.fields["channelGridColumns"] is CHANNEL_GRID_COLUMNS
    assert CHANNEL_GRID_COLUMNS.minimum == 1
    assert CHANNEL_GRID_COLUMNS.maximum == QT_INT_MAX
    assert Store().channel_grid_columns == GlobalSettings().get("channelGridColumns") == 2


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2.5", QT_INT_MAX + 1])
def test_invalid_grid_columns_do_not_replace_a_live_preference(value):
    model = GlobalSettings()
    store = Store()
    store.channel_grid_columns = 5
    with pytest.raises(SettingsValueError):
        model.set("channelGridColumns", value)
    with pytest.raises(SettingsValueError):
        store.channel_grid_columns = value
    assert model.get("channelGridColumns") == 2
    assert store.channel_grid_columns == 5


def test_live_grid_columns_notify_all_grids_once(dialog):
    store = Store()
    changes = []
    store.channel_grid_columns_changed.connect(changes.append)
    dialog.channel_grid_columns_changed.connect(store.set_channel_grid_columns)
    editor = dialog.spinBox_channelGridColumns
    assert (editor.minimum(), editor.maximum()) == (1, QT_INT_MAX)

    editor.setValue(31)
    editor.setValue(31)

    assert changes == [31]
    assert store.channel_grid_columns == 31
    assert dialog.settings_model.get("channelGridColumns") == 31


def test_grid_columns_restore_and_save_without_audio_hardware(dialog, profile):
    store = Store()
    dialog.channel_grid_columns_changed.connect(store.set_channel_grid_columns)
    profile.setValue("channelGridColumns", "17")
    profile.setValue("themePreference", 2)
    profile.setValue("deviceName", "Disconnected device")

    dialog.restoreState(profile)

    assert dialog.spinBox_channelGridColumns.value() == 17
    assert store.channel_grid_columns == 17
    assert dialog.themeButtonGroup.checkedId() == 2
    dialog.saveState(profile)
    assert profile.value("channelGridColumns") == 17
    assert profile.value("deviceName") == "Disconnected device"


def test_invalid_saved_grid_columns_recover_without_rewriting_store(dialog, profile):
    store = Store()
    store.channel_grid_columns = 8
    dialog.channel_grid_columns_changed.connect(store.set_channel_grid_columns)
    profile.setValue("channelGridColumns", 0)

    dialog.restoreState(profile)

    assert store.channel_grid_columns == CHANNEL_GRID_COLUMNS.default
    assert dialog.spinBox_channelGridColumns.value() == CHANNEL_GRID_COLUMNS.default
    assert profile.value("channelGridColumns") == 0
