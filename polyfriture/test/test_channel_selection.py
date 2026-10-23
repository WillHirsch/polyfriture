"""Checked-channel edits and recovery use actual capture transactions, without hardware."""

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QByteArray, QSettings, Qt
from PyQt6.QtTest import QTest

from polyfriture import audiobackend, settings as settings_module
from polyfriture.settings import GlobalSettings, Settings_Dialog
from polyfriture.settings_model import SettingsValueError
from polyfriture.test.test_channel_configuration import capture


@pytest.fixture
def audio_dialog(capture, monkeypatch, qt_application):
    backend, factory = capture
    monkeypatch.setattr(settings_module, "AudioBackend", lambda: backend)
    monkeypatch.setattr(backend, "get_readable_devices_list", lambda: [device["name"] for device in backend.input_devices])
    monkeypatch.setattr(audiobackend.sounddevice, "query_hostapis", lambda index: {"name": ("WASAPI", "ASIO")[index]})
    dialogs = []
    def create():
        dialog = Settings_Dialog(None)
        dialogs.append(dialog)
        return dialog
    yield create, backend, factory
    for dialog in dialogs:
        sip.delete(dialog)


@pytest.fixture
def profile(tmp_path):
    value = QSettings(str(tmp_path / "selection.ini"), QSettings.Format.IniFormat)
    value.setFallbacksEnabled(False)
    yield value
    sip.delete(value)


def checked(dialog):
    return [row for row in range(dialog.listWidget_channels.count())
            if dialog.listWidget_channels.item(row).checkState() == Qt.CheckState.Checked]


def saved(profile, name="Eight inputs", api="WASAPI", channels=(1, 4, 6)):
    profile.setValue("deviceName", name)
    profile.setValue("deviceHostApi", api)
    profile.setValue("selectedChannels", list(channels))


@pytest.mark.parametrize("value,expected", [
    ([7, 1, 4, 1], [1, 4, 7]), ((3, 0), [0, 3]), (["7", "+1", "4"], [1, 4, 7]),
    (0, [0]), ("12", [12]), ([4096], [4096]),
])
def test_selection_assignment_has_one_canonical_order(value, expected):
    model = GlobalSettings()
    assert model.set("selectedChannels", value) == expected
    assert model.get("selectedChannels") == expected


@pytest.mark.parametrize("value", [None, [], (), True, False, -1, 1.5, "1,2", "", [0, True],
                                  [0, -1], ["bad"], [1.5], {"channel": 0}, QByteArray(b"1")])
def test_invalid_selection_cannot_replace_live_preferences(value):
    model = GlobalSettings()
    model.set("selectedChannels", [1, 3])
    with pytest.raises(SettingsValueError):
        model.set("selectedChannels", value)
    assert model.get("selectedChannels") == [1, 3]


def test_keyboard_checkbox_edits_keep_one_channel_and_sort_physical_rows(audio_dialog):
    create, backend, _ = audio_dialog
    dialog = create()
    generation = backend.channel_configuration.generation
    dialog.listWidget_channels.setCurrentRow(0)
    QTest.keyClick(dialog.listWidget_channels, Qt.Key.Key_Space)
    assert checked(dialog) == [0]
    assert backend.channel_configuration.generation == generation
    assert "at least one" in dialog.label_inputStatus.text()
    for channel in (6, 2, 4, 0):
        dialog.listWidget_channels.setCurrentRow(channel)
        QTest.keyClick(dialog.listWidget_channels, Qt.Key.Key_Space)
    assert checked(dialog) == [2, 4, 6]
    assert backend.channel_configuration.channel_ids == (2, 4, 6)
    assert dialog.settings_model.get("selectedChannels") == [2, 4, 6]
    assert [dialog.listWidget_channels.item(row).text() for row in checked(dialog)] == ["Channel 3", "Channel 5", "Channel 7"]


def test_last_checkbox_rejection_preserves_queued_samples_and_paused_state(audio_dialog):
    create, backend, _ = audio_dialog
    dialog = create()
    backend.pause()
    samples = np.ones((17, 8), dtype=np.float32)
    backend.ringBuffer.load(samples)
    configuration = backend.channel_configuration
    dialog.listWidget_channels.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert backend.channel_configuration is configuration
    np.testing.assert_array_equal(backend.ringBuffer.samples, samples)
    assert not backend.running
    assert checked(dialog) == [0]


def test_failed_channel_edit_rolls_back_checks_and_saved_preference(audio_dialog, monkeypatch):
    create, backend, _ = audio_dialog
    dialog = create()
    before = backend.channel_configuration
    def fail(channels):
        raise RuntimeError("Synthetic channel failure")
    monkeypatch.setattr(backend, "select_channels", fail)
    dialog.listWidget_channels.item(6).setCheckState(Qt.CheckState.Checked)
    assert backend.channel_configuration is before
    assert checked(dialog) == [0]
    assert dialog.settings_model.get("selectedChannels") == [0]
    assert "previous" in dialog.label_inputStatus.text()


def test_host_api_disambiguates_same_named_devices(audio_dialog, profile):
    create, backend, _ = audio_dialog
    backend.input_devices[0]["name"] = "Four inputs"
    dialog = create()
    saved(profile, "Four inputs", "ASIO", (1, 3))
    dialog.restoreState(profile)
    assert backend.channel_configuration.device_id == 8
    assert backend.channel_configuration.channel_ids == (1, 3)
    assert dialog.comboBox_inputDevice.currentIndex() == 1
    assert checked(dialog) == [1, 3]


@pytest.mark.parametrize("api", ["", "WASAPI"])
def test_ambiguous_identity_does_not_guess_or_lose_preference(audio_dialog, profile, api):
    create, backend, _ = audio_dialog
    backend.input_devices[1]["name"] = "Eight inputs"
    backend.input_devices[1]["hostapi"] = 0
    dialog = create()
    saved(profile, api=api)
    configuration = backend.channel_configuration
    dialog.restoreState(profile)
    assert backend.channel_configuration is configuration
    assert checked(dialog) == [0]
    assert "ambiguous" in dialog.label_inputStatus.text()
    dialog.saveState(profile)
    assert profile.value("selectedChannels") == [1, 4, 6]
    assert profile.value("deviceHostApi") == api


@pytest.mark.parametrize("wanted,active", [([1, 7], [1]), ([4, 7], [0])])
def test_missing_channels_use_valid_subset_but_keep_requested_preference(audio_dialog, profile, wanted, active):
    create, backend, _ = audio_dialog
    dialog = create()
    saved(profile, "Four inputs", "ASIO", wanted)
    dialog.restoreState(profile)
    assert checked(dialog) == active
    assert list(backend.channel_configuration.channel_ids) == active
    assert "unavailable" in dialog.label_inputStatus.text()
    dialog.saveState(profile)
    assert profile.value("selectedChannels") == wanted
    dialog.listWidget_channels.item(2).setCheckState(Qt.CheckState.Checked)
    dialog.saveState(profile)
    assert profile.value("selectedChannels") == sorted([*active, 2])


def test_failed_saved_device_does_not_apply_its_channels_to_current_input(audio_dialog, profile):
    create, backend, factory = audio_dialog
    backend.select_channels([2, 6])
    backend.pause()
    dialog = create()
    saved(profile, "Four inputs", "ASIO", (1, 3))
    before = backend.channel_configuration
    factory.fail_open = True
    dialog.restoreState(profile)
    assert backend.channel_configuration is before
    assert not backend.running
    assert checked(dialog) == [2, 6]
    assert dialog.comboBox_inputDevice.currentIndex() == 0
    dialog.saveState(profile)
    assert profile.value("deviceName") == "Four inputs"
    assert profile.value("selectedChannels") == [1, 3]
    assert "Could not open" in dialog.label_inputStatus.text()


def test_missing_device_keeps_selection_until_explicit_channel_edit(audio_dialog, profile):
    create, backend, _ = audio_dialog
    dialog = create()
    saved(profile, "Unplugged", "WASAPI", (5, 7))
    dialog.restoreState(profile)
    dialog.saveState(profile)
    assert checked(dialog) == [0]
    assert profile.value("deviceName") == "Unplugged"
    assert profile.value("selectedChannels") == [5, 7]
    dialog.listWidget_channels.item(3).setCheckState(Qt.CheckState.Checked)
    dialog.saveState(profile)
    assert profile.value("deviceName") == "Eight inputs"
    assert profile.value("deviceHostApi") == "WASAPI"
    assert profile.value("selectedChannels") == [0, 3]


def test_valid_default_restore_clears_an_earlier_missing_device_message(audio_dialog, profile):
    create, _, _ = audio_dialog
    dialog = create()
    saved(profile, "Unplugged")
    dialog.restoreState(profile)
    assert dialog.label_inputStatus.text()
    profile.clear()
    dialog.restoreState(profile)
    assert dialog.label_inputStatus.text() == ""


def test_large_device_has_no_selector_channel_cap(audio_dialog):
    create, backend, _ = audio_dialog
    backend.input_devices[0]["max_input_channels"] = 129
    assert backend.select_input_device(1)[0]
    assert backend.select_input_device(0)[0]
    dialog = create()
    assert dialog.listWidget_channels.count() == 129
    dialog.listWidget_channels.item(128).setCheckState(Qt.CheckState.Checked)
    dialog.listWidget_channels.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert backend.channel_configuration.channel_ids == (128,)
    assert dialog.listWidget_channels.item(128).text() == "Channel 129"


@pytest.mark.parametrize("has_devices", [False, True])
def test_dialog_remains_usable_without_an_active_device_and_can_retry(audio_dialog, monkeypatch, profile, has_devices):
    create, backend, factory = audio_dialog
    factory.fail_open = True
    if not has_devices:
        monkeypatch.setattr(type(backend), "get_input_devices", lambda self: [])
    unavailable = type(backend)()
    monkeypatch.setattr(settings_module, "AudioBackend", lambda: unavailable)
    monkeypatch.setattr(unavailable, "get_readable_devices_list", lambda: [device["name"] for device in unavailable.input_devices])
    try:
        dialog = create()
        assert unavailable.channel_configuration is None
        assert dialog.comboBox_inputDevice.currentIndex() == -1
        assert dialog.listWidget_channels.count() == 0
        assert not dialog.listWidget_channels.isEnabled()
        assert "No usable" in dialog.label_inputStatus.text()
        saved(profile)
        dialog.restoreState(profile)
        dialog.saveState(profile)
        assert profile.value("selectedChannels") == [1, 4, 6]
        dialog.spinBox_channelGridColumns.setValue(3)
        assert dialog.settings_model.get("channelGridColumns") == 3
        if has_devices:
            factory.fail_open = False
            dialog.comboBox_inputDevice.setCurrentIndex(0)
            dialog.comboBox_inputDevice.activated.emit(0)
            assert unavailable.channel_configuration.channel_ids == (0,)
            assert checked(dialog) == [0]
            assert dialog.listWidget_channels.isEnabled()
            assert not dialog.label_inputStatus.text()
    finally:
        unavailable.close()


def test_input_enumeration_keeps_devices_when_no_default_is_configured(monkeypatch):
    devices = [{"name": "Input A", "max_input_channels": 2},
               {"name": "Output", "max_input_channels": 0},
               {"name": "Input B", "max_input_channels": 8}]
    def query_devices(kind=None):
        if kind == "input":
            raise audiobackend.sounddevice.PortAudioError("No default input")
        return devices
    monkeypatch.setattr(audiobackend.sounddevice, "query_devices", query_devices)
    available = getattr(audiobackend, "__AudioBackend").get_input_devices(SimpleNamespace(logger=Mock()))
    assert [device["name"] for device in available] == ["Input A", "Input B"]
    assert [device["index"] for device in available] == [0, 2]
