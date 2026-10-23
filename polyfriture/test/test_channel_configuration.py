"""Channel routing and reconfiguration never require audio hardware."""

from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QSettings, Qt

from polyfriture import audiobackend, settings as settings_module
from polyfriture.channel_configuration import ChannelConfiguration
from polyfriture.settings import Settings_Dialog


class SyntheticCaptureRing:
    """Interleaved float32 capture bytes, with the same read API as rtmixer."""

    def __init__(self, channel_count):
        self.samples = np.empty((0, channel_count), dtype=np.float32)

    @property
    def read_available(self):
        return len(self.samples)

    def load(self, samples):
        self.samples = np.asarray(samples, dtype=np.float32).copy()

    def get_read_buffers(self, count):
        return count, self.samples[:count].tobytes(), b""

    def advance_read_index(self, count):
        self.samples = self.samples[count:]

    def flush(self):
        self.samples = self.samples[:0]


class SyntheticStream:
    def __init__(self, device_id, fail_start=False):
        self.device = device_id
        self.time = 12.5
        self.active = False
        self.fail_start = fail_start
        self.fail_stop = False
        self.fail_close = False
        self.start_calls = 0
        self.stop_calls = 0
        self.close_calls = 0

    def start(self):
        self.start_calls += 1
        if self.fail_start:
            raise RuntimeError("Synthetic device failed to start")
        self.active = True

    def stop(self):
        self.stop_calls += 1
        if self.fail_stop:
            raise RuntimeError("Synthetic device failed to stop")
        self.active = False

    def close(self):
        self.close_calls += 1
        if self.fail_close:
            raise RuntimeError("Synthetic device failed to close")
        self.active = False


@pytest.fixture
def capture(monkeypatch):
    devices = [
        {"name": "Eight inputs", "index": 3, "max_input_channels": 8, "hostapi": 0},
        {"name": "Four inputs", "index": 8, "max_input_channels": 4, "hostapi": 1},
    ]
    factory = SimpleNamespace(streams=[], rings=[], fail_open=False, fail_start=False,
                              fail_stop=False, fail_close=False, pending_samples=None)
    backend_type = getattr(audiobackend, "__AudioBackend")
    monkeypatch.setattr(backend_type, "get_input_devices", lambda self: devices)
    monkeypatch.setattr(backend_type, "get_output_devices", lambda self: [])

    def open_stream(self, device):
        if factory.fail_open:
            raise RuntimeError("Synthetic device failed to open")
        stream = SyntheticStream(device["index"], factory.fail_start)
        stream.fail_stop = factory.fail_stop
        stream.fail_close = factory.fail_close
        ring = SyntheticCaptureRing(device["max_input_channels"])
        if factory.pending_samples is not None:
            ring.load(factory.pending_samples)
        factory.streams.append(stream)
        factory.rings.append(ring)
        action = SimpleNamespace(stats=SimpleNamespace(input_overflows=0))
        return stream, ring, action, device["max_input_channels"]

    monkeypatch.setattr(backend_type, "open_stream", open_stream)
    backend = backend_type()
    yield backend, factory
    backend.close()
    sip.delete(backend)


@pytest.fixture
def distinct_channels():
    """Every physical channel has a distinguishable sample-by-sample signal."""
    time = np.arange(audiobackend.FRAMES_PER_BUFFER, dtype=np.float32)
    return np.stack([1000 * channel + time for channel in range(8)], axis=1)


def test_configuration_canonicalizes_physical_ids_and_uses_one_based_labels():
    configuration = ChannelConfiguration(3, (7, 2, 0, 2), 8, 1)
    assert configuration.channel_ids == (0, 2, 7)
    assert configuration.channel_labels == ("Channel 1", "Channel 3", "Channel 8")
    assert configuration.device_id == 3
    assert configuration.device_channel_count == 8
    with pytest.raises(FrozenInstanceError):
        configuration.generation = 2


def test_configuration_has_no_arbitrary_channel_limit():
    configuration = ChannelConfiguration(3, tuple(range(1025)), 1025, 1)
    assert len(configuration.channel_ids) == 1025
    assert configuration.channel_labels[-1] == "Channel 1025"


@pytest.mark.parametrize("channels", [(), (-1,), (8,), (1.0,), (True,), ("1",), (None,)])
def test_configuration_rejects_invalid_channel_selection(channels):
    with pytest.raises(ValueError):
        ChannelConfiguration(3, channels, 8, 1)


def test_backend_routes_noncontiguous_channels_in_physical_order(capture, distinct_channels):
    backend, _ = capture
    events = []
    backend.configuration_changed.connect(lambda configuration: events.append(("configuration", configuration)))
    backend.new_data_available.connect(lambda *packet: events.append(("data", packet)))

    configuration = backend.select_channels([7, 2, 0, 2])
    backend.ringBuffer.load(distinct_channels)
    backend.fetchAudioData()

    assert [event[0] for event in events] == ["configuration", "data"]
    assert events[0][1] is configuration
    samples, input_time, overflow, generation = events[1][1]
    np.testing.assert_array_equal(samples, distinct_channels[:, [0, 2, 7]].T)
    assert samples.shape == (3, audiobackend.FRAMES_PER_BUFFER)
    assert samples.dtype == np.float64
    assert np.isfinite(input_time)
    assert not overflow
    assert generation == configuration.generation == 2


def test_backend_can_emit_every_channel(capture, distinct_channels):
    backend, _ = capture
    configuration = backend.select_channels(range(8))
    backend.ringBuffer.load(distinct_channels)
    packets = []
    backend.new_data_available.connect(lambda *packet: packets.append(packet))
    backend.fetchAudioData()
    np.testing.assert_array_equal(packets[0][0], distinct_channels.T)
    assert packets[0][3] == configuration.generation


def test_generations_change_for_add_remove_and_same_count_replacement(capture):
    backend, _ = capture
    events = []
    backend.configuration_changed.connect(events.append)
    assert backend.channel_configuration.generation == 1
    for generation, channels in enumerate(((0, 3), (1, 5), (5,)), start=2):
        configuration = backend.select_channels(channels)
        assert configuration.channel_ids == channels
        assert configuration.generation == generation
    assert [configuration.generation for configuration in events] == [2, 3, 4]
    assert backend.select_channels([5, 5]) is backend.channel_configuration
    assert len(events) == 3


@pytest.mark.parametrize("channels", [[], [-1], [8], [1.0], [True], ["1"], None])
def test_invalid_backend_selection_preserves_configuration_and_running_state(capture, channels):
    backend, _ = capture
    previous = backend.channel_configuration
    events = []
    backend.configuration_changed.connect(events.append)
    with pytest.raises(ValueError):
        backend.select_channels(channels)
    assert backend.channel_configuration is previous
    assert backend.running
    assert events == []


def test_channel_change_discards_pending_old_configuration_capture(capture, distinct_channels):
    backend, _ = capture
    backend.ringBuffer.load(distinct_channels)
    backend.select_channels([3, 5])
    packets = []
    backend.new_data_available.connect(lambda *packet: packets.append(packet))
    backend.fetchAudioData()
    assert packets == []
    backend.ringBuffer.load(distinct_channels + 10000)
    backend.fetchAudioData()
    np.testing.assert_array_equal(packets[0][0], (distinct_channels + 10000)[:, [3, 5]].T)


@pytest.mark.parametrize("paused", [False, True])
def test_device_change_preserves_run_pause_and_advances_configuration(capture, paused):
    backend, factory = capture
    old_stream = backend.stream
    if paused:
        backend.pause()
    stopped_before = old_stream.stop_calls
    configuration_before = backend.channel_configuration
    success, index = backend.select_input_device(1)
    assert success and index == 1
    assert backend.running is not paused
    assert backend.stream is factory.streams[-1]
    assert backend.stream.active is not paused
    assert backend.stream.start_calls == (0 if paused else 1)
    assert old_stream.close_calls == 1
    assert old_stream.stop_calls >= stopped_before
    configuration = backend.channel_configuration
    assert configuration.device_id == 8
    assert configuration.device_channel_count == 4
    assert configuration.generation == configuration_before.generation + 1


@pytest.mark.parametrize("failure", ["open", "start"])
def test_failed_device_change_preserves_live_stream_and_configuration(capture, distinct_channels, failure):
    backend, factory = capture
    backend.ringBuffer.load(distinct_channels)
    previous = (backend.stream, backend.ringBuffer, backend.action, backend.channel_configuration)
    factory.fail_open = failure == "open"
    factory.fail_start = failure == "start"
    events = []
    backend.configuration_changed.connect(events.append)
    success, index = backend.select_input_device(1)
    assert not success and index == 0
    assert (backend.stream, backend.ringBuffer, backend.action, backend.channel_configuration) == previous
    assert backend.running and backend.stream.active
    assert backend.stream.stop_calls == 0
    assert backend.stream.close_calls == 0
    np.testing.assert_array_equal(backend.ringBuffer.samples, distinct_channels)
    assert events == []
    if failure == "start":
        assert factory.streams[-1].close_calls == 1


def test_failed_device_open_preserves_paused_state(capture):
    backend, factory = capture
    backend.pause()
    previous = backend.channel_configuration
    factory.fail_open = True
    assert backend.select_input_device(1) == (False, 0)
    assert not backend.running
    assert not backend.stream.active
    assert backend.stream.start_calls == 1
    assert backend.channel_configuration is previous


def test_successful_replacement_closes_old_stream_even_when_stopping_it_fails(capture):
    backend, _ = capture
    old_stream = backend.stream
    old_stream.fail_stop = True
    previous_generation = backend.channel_configuration.generation
    assert backend.select_input_device(1) == (True, 1)
    assert old_stream.stop_calls == 1
    assert old_stream.close_calls == 1
    assert backend.stream is not old_stream
    assert backend.stream.active and backend.running
    assert backend.channel_configuration.device_id == 8
    assert backend.channel_configuration.generation == previous_generation + 1


def test_failed_candidate_cleanup_errors_do_not_mask_original_device_failure(capture):
    backend, factory = capture
    old_stream = backend.stream
    configuration = backend.channel_configuration
    factory.fail_start = factory.fail_stop = factory.fail_close = True
    assert backend.select_input_device(1) == (False, 0)
    candidate = factory.streams[-1]
    assert candidate is not old_stream
    assert candidate.stop_calls == candidate.close_calls == 1
    assert backend.stream is old_stream
    assert backend.channel_configuration is configuration
    assert old_stream.active and backend.running
    assert old_stream.stop_calls == old_stream.close_calls == 0


def test_close_then_restart_cannot_emit_queued_old_capture(capture, distinct_channels):
    backend, _ = capture
    backend.ringBuffer.load(distinct_channels)
    packets = []
    backend.new_data_available.connect(lambda *packet: packets.append(packet))
    backend.close()
    backend.restart()
    backend.fetchAudioData()
    assert backend.stream is None
    assert backend.ringBuffer is None
    assert backend.action is None
    assert packets == []


def test_same_device_can_be_reopened_after_close(capture, distinct_channels):
    backend, factory = capture
    old_stream = backend.stream
    previous_generation = backend.channel_configuration.generation
    backend.close()
    assert backend.select_input_device(0) == (True, 0)
    assert backend.stream is factory.streams[-1]
    assert backend.stream is not old_stream
    assert not backend.running
    assert not backend.stream.active
    assert backend.channel_configuration.generation == previous_generation + 1
    backend.restart()
    backend.ringBuffer.load(distinct_channels)
    packets = []
    backend.new_data_available.connect(lambda *packet: packets.append(packet))
    backend.fetchAudioData()
    np.testing.assert_array_equal(packets[0][0], distinct_channels[:, [0]].T)


@pytest.mark.parametrize("index", [-1, 2, 1.5, True, None])
def test_invalid_device_selection_is_rejected_without_reconfiguration(capture, index):
    backend, factory = capture
    configuration = backend.channel_configuration
    assert backend.select_input_device(index) == (False, 0)
    assert backend.channel_configuration is configuration
    assert len(factory.streams) == 1


def test_same_device_selection_is_a_no_op(capture):
    backend, factory = capture
    configuration = backend.channel_configuration
    assert backend.select_input_device(0) == (True, 0)
    assert backend.channel_configuration is configuration
    assert len(factory.streams) == 1


def test_no_input_device_has_no_configuration_or_deliverable_audio(monkeypatch):
    backend_type = getattr(audiobackend, "__AudioBackend")
    monkeypatch.setattr(backend_type, "get_input_devices", lambda self: [])
    monkeypatch.setattr(backend_type, "get_output_devices", lambda self: [])
    opener = Mock(side_effect=AssertionError("No device should be opened"))
    monkeypatch.setattr(backend_type, "open_stream", opener)
    backend = backend_type()
    try:
        assert backend.channel_configuration is None
        assert backend.get_readable_current_device() == -1
        assert backend.get_readable_current_channels() == []
        assert backend.select_input_device(0) == (False, -1)
        with pytest.raises(ValueError, match="device"):
            backend.select_channels([0])
        packets = []
        backend.new_data_available.connect(lambda *packet: packets.append(packet))
        backend.fetchAudioData()
        assert packets == []
        opener.assert_not_called()
    finally:
        backend.close()
        sip.delete(backend)


@pytest.mark.parametrize("paused", [False, True])
def test_device_and_noncontiguous_channels_are_published_as_one_transaction(capture, paused):
    backend, factory = capture
    backend.select_channels([1, 4, 7])
    old_stream = backend.stream
    previous_generation = backend.channel_configuration.generation
    if paused:
        backend.pause()
    factory.pending_samples = np.ones((17, 4), dtype=np.float32)
    events = []
    backend.configuration_changed.connect(events.append)

    assert backend.select_input_device(1, [3, 1, 3]) == (True, 1)

    assert len(events) == 1
    configuration = events[0]
    assert configuration is backend.channel_configuration
    assert configuration.channel_ids == (1, 3)
    assert configuration.device_id == 8
    assert configuration.generation == previous_generation + 1
    assert backend.ringBuffer.read_available == 0
    assert backend.stream_read_index == 17
    assert backend.running is not paused
    assert backend.stream.active is not paused
    assert backend.stream.start_calls == (0 if paused else 1)
    assert old_stream.close_calls == 1


@pytest.mark.parametrize("channels", [[], [-1], [4], [1.0], [True], ["1"]])
def test_invalid_device_channel_transaction_preserves_capture(capture, distinct_channels, channels):
    backend, factory = capture
    backend.select_channels([0, 2, 7])
    backend.ringBuffer.load(distinct_channels)
    previous = (backend.stream, backend.ringBuffer, backend.action, backend.channel_configuration)
    events = []
    backend.configuration_changed.connect(events.append)

    assert backend.select_input_device(1, channels) == (False, 0)

    assert (backend.stream, backend.ringBuffer, backend.action, backend.channel_configuration) == previous
    assert len(factory.streams) == 1
    assert backend.stream.active and backend.running
    np.testing.assert_array_equal(backend.ringBuffer.samples, distinct_channels)
    assert events == []


@pytest.mark.parametrize("failure, paused", [("open", False), ("start", False), ("open", True)])
def test_failed_explicit_device_channel_transaction_preserves_every_capture_field(
        capture, distinct_channels, failure, paused):
    backend, factory = capture
    backend.select_channels([1, 3, 6])
    if paused:
        backend.pause()
    backend.ringBuffer.load(distinct_channels)
    previous = (backend.stream, backend.ringBuffer, backend.action, backend.channel_configuration,
                backend.device, backend.nchannels_max, backend.stream_start_time,
                backend.stream_read_index, backend.xruns, backend.running)
    starts, stops = backend.stream.start_calls, backend.stream.stop_calls
    factory.fail_open = failure == "open"
    factory.fail_start = failure == "start"
    events = []
    backend.configuration_changed.connect(events.append)

    assert backend.select_input_device(1, (0, 2, 3)) == (False, 0)

    assert (backend.stream, backend.ringBuffer, backend.action, backend.channel_configuration,
            backend.device, backend.nchannels_max, backend.stream_start_time,
            backend.stream_read_index, backend.xruns, backend.running) == previous
    assert backend.stream.active is not paused
    assert (backend.stream.start_calls, backend.stream.stop_calls) == (starts, stops)
    np.testing.assert_array_equal(backend.ringBuffer.samples, distinct_channels)
    assert events == []


@pytest.mark.parametrize("paused", [False, True])
def test_explicit_channels_on_active_device_reconfigure_without_reopening(capture, distinct_channels, paused):
    backend, factory = capture
    if paused:
        backend.pause()
    backend.ringBuffer.load(distinct_channels[:17])
    stream = backend.stream
    starts, stops = stream.start_calls, stream.stop_calls
    generation = backend.channel_configuration.generation

    assert backend.select_input_device(0, [6, 2]) == (True, 0)

    assert backend.channel_configuration.channel_ids == (2, 6)
    assert backend.channel_configuration.generation == generation + 1
    assert backend.stream is stream
    assert len(factory.streams) == 1
    assert backend.ringBuffer.read_available == 0
    assert backend.running is not paused
    assert stream.active is not paused
    assert (stream.start_calls, stream.stop_calls) == (starts, stops)
    current = backend.channel_configuration
    assert backend.select_input_device(0, [2, 6]) == (True, 0)
    assert backend.channel_configuration is current
    assert backend.select_input_device(0, [8]) == (False, 0)
    assert backend.channel_configuration is current


def test_new_device_without_saved_channels_defaults_to_first_input(capture):
    backend, _ = capture
    backend.select_channels([2, 5, 7])
    assert backend.select_input_device(1) == (True, 1)
    assert backend.channel_configuration.channel_ids == (0,)


def test_device_metadata_uses_the_capture_enumeration_order(capture, monkeypatch):
    backend, _ = capture
    # Re-enumeration must not replace the cached capture selector order.
    # Display labels and stable identities must refer to the same devices.
    monkeypatch.setattr(backend, "get_input_devices", Mock(side_effect=AssertionError("must use cached devices")))
    default = backend.input_devices[1].copy()
    raw_devices = [None] * 9
    raw_devices[3] = backend.input_devices[0]
    raw_devices[8] = default
    monkeypatch.setattr(audiobackend.sounddevice, "query_devices",
                        lambda kind=None: default.copy() if kind == "input" else raw_devices)
    monkeypatch.setattr(audiobackend.sounddevice, "query_hostapis",
                        lambda index: {"name": ("WASAPI", "ASIO")[index]})

    assert backend.get_input_device_identities() == [("Eight inputs", "WASAPI"), ("Four inputs", "ASIO")]
    assert [backend.get_input_device_channel_count(index) for index in range(2)] == [8, 4]
    labels = backend.get_readable_devices_list()
    assert labels[0].startswith("Eight inputs (8 channels) (WASAPI)")
    assert labels[1].startswith("Four inputs (4 channels) (ASIO)")
    assert "(default)" not in labels[0]
    assert "(default)" in labels[1]


@pytest.mark.parametrize("running", [False, True])
def test_settings_changes_preserve_capture_state(capture, monkeypatch, running):
    backend, _ = capture
    if not running:
        backend.pause()
    monkeypatch.setattr(settings_module, "AudioBackend", lambda: backend)
    monkeypatch.setattr(backend, "get_readable_devices_list", lambda: ["Eight inputs", "Four inputs"])
    monkeypatch.setattr(backend, "get_input_device_identities", lambda: [("Eight inputs", "WASAPI"), ("Four inputs", "ASIO")])
    dialog = Settings_Dialog(None)
    try:
        dialog.listWidget_channels.item(5).setCheckState(Qt.CheckState.Checked)
        dialog.listWidget_channels.item(2).setCheckState(Qt.CheckState.Checked)
        dialog.comboBox_inputDevice.setCurrentIndex(1)
        dialog.comboBox_inputDevice.activated.emit(1)
        assert backend.running is running
        assert dialog.comboBox_inputDevice.currentIndex() == 1
    finally:
        sip.delete(dialog)


def test_failed_settings_device_change_reverts_once_without_recursive_selection(capture, monkeypatch):
    backend, factory = capture
    monkeypatch.setattr(settings_module, "AudioBackend", lambda: backend)
    monkeypatch.setattr(backend, "get_readable_devices_list", lambda: ["Eight inputs", "Four inputs"])
    monkeypatch.setattr(backend, "get_input_device_identities", lambda: [("Eight inputs", "WASAPI"), ("Four inputs", "ASIO")])
    selector = Mock(wraps=backend.select_input_device)
    monkeypatch.setattr(backend, "select_input_device", selector)
    dialog = Settings_Dialog(None)
    try:
        factory.fail_open = True
        dialog.comboBox_inputDevice.setCurrentIndex(1)
        dialog.comboBox_inputDevice.activated.emit(1)
        selector.assert_called_once_with(1)
        assert dialog.comboBox_inputDevice.currentIndex() == 0
        assert dialog.settings_model.get("deviceName") == "Eight inputs"
        assert [row for row in range(dialog.listWidget_channels.count())
                if dialog.listWidget_channels.item(row).checkState() == Qt.CheckState.Checked] == list(backend.channel_configuration.channel_ids)
    finally:
        sip.delete(dialog)


def test_reselecting_active_fallback_replaces_unavailable_saved_preference(capture, monkeypatch, tmp_path):
    backend, factory = capture
    backend.select_channels([2, 7])
    monkeypatch.setattr(settings_module, "AudioBackend", lambda: backend)
    monkeypatch.setattr(backend, "get_readable_devices_list", lambda: ["Eight inputs", "Four inputs"])
    monkeypatch.setattr(backend, "get_input_device_identities",
                        lambda: [("Eight inputs", "WASAPI"), ("Four inputs", "ASIO")])
    profile = QSettings(str(tmp_path / "missing-input.ini"), QSettings.Format.IniFormat)
    profile.setValue("deviceName", "Temporarily unplugged")
    profile.setValue("deviceHostApi", "WASAPI")
    profile.setValue("selectedChannels", [1, 4, 6])
    dialog = Settings_Dialog(None)
    try:
        dialog.restoreState(profile)
        assert dialog.comboBox_inputDevice.currentIndex() == 0
        assert "unavailable" in dialog.label_inputStatus.text()
        assert dialog.settings_model.get("deviceName") == "Temporarily unplugged"
        previous_configuration = backend.channel_configuration
        selector = Mock(wraps=backend.select_input_device)
        monkeypatch.setattr(backend, "select_input_device", selector)

        # A user may explicitly choose the same item already displayed. Qt
        # emits activated in this case, but currentIndexChanged is silent.
        dialog.comboBox_inputDevice.activated.emit(0)

        selector.assert_called_once_with(0)
        assert backend.channel_configuration is previous_configuration
        assert len(factory.streams) == 1
        assert dialog.settings_model.get("deviceName") == "Eight inputs"
        assert dialog.settings_model.get("deviceHostApi") == "WASAPI"
        assert dialog.settings_model.get("selectedChannels") == [2, 7]
        assert dialog.label_inputStatus.text() == ""
        dialog.saveState(profile)
        assert profile.value("deviceName") == "Eight inputs"
        assert profile.value("selectedChannels") == [2, 7]
    finally:
        sip.delete(dialog)
