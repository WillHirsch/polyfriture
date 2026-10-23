"""Catch-up yields to GUI controls without discarding queued capture samples."""

import numpy as np
from PyQt6.QtCore import QTimer

from polyfriture import audiobackend
from polyfriture.test.test_channel_configuration import capture


def test_continuous_capture_yields_to_queued_controls(capture, monkeypatch, qt_application):
    backend, _ = capture
    clock = [0.]
    monkeypatch.setattr(audiobackend.time, "monotonic", lambda: clock[0])
    block = np.ones((audiobackend.FRAMES_PER_BUFFER, 8), dtype=np.float32)
    backend.ringBuffer.load(block)
    packets = []

    def process(samples, *metadata):
        packets.append(samples.copy())
        clock[0] += .02
        # A live producer can replace every block while the consumer works.
        # Bound the reproduction so the former drain loop fails promptly.
        if len(packets) < 8:
            backend.ringBuffer.load(block * (len(packets) + 1))

    backend.new_data_available.connect(process)
    controls = []
    QTimer.singleShot(0, lambda: controls.append("serviced"))
    backend.fetchAudioData()
    assert len(packets) == 1
    assert backend.ringBuffer.read_available == len(block)
    assert not controls
    qt_application.processEvents()
    assert controls == ["serviced"]
    backend.fetchAudioData()
    assert len(packets) == 2
    np.testing.assert_array_equal(packets[1], 2 * block[:, :1].T)


def test_yield_retains_order_timestamps_and_partial_capture_block(capture, monkeypatch):
    backend, _ = capture
    backend.select_channels((2, 6))
    clock = [0.]
    monkeypatch.setattr(audiobackend.time, "monotonic", lambda: clock[0])
    count = audiobackend.FRAMES_PER_BUFFER
    samples = np.arange((3 * count + 17) * 8, dtype=np.float32).reshape(-1, 8)
    # The queued audio precedes the stream clock, as a real backlog would.
    backend.stream.time += .5
    backend.ringBuffer.load(samples)
    packets = []

    def process(data, timestamp, overflow, generation):
        packets.append((data.copy(), timestamp, overflow, generation))
        clock[0] += .02

    backend.new_data_available.connect(process)
    for index in range(3):
        backend.fetchAudioData()
        assert len(packets) == index + 1
        assert backend.ringBuffer.read_available == (2 - index) * count + 17
        np.testing.assert_array_equal(packets[index][0], samples[index * count:(index + 1) * count, (2, 6)].T)
    np.testing.assert_array_equal(backend.ringBuffer.samples, samples[-17:])
    np.testing.assert_allclose(np.diff([packet[1] for packet in packets]), count / audiobackend.SAMPLING_RATE)
    assert all(not overflow and generation == backend.channel_configuration.generation
               for _, _, overflow, generation in packets)
    backend.fetchAudioData()
    assert len(packets) == 3
    assert backend.chunk_number == 3


def test_fast_catch_up_still_processes_multiple_blocks_in_one_tick(capture, monkeypatch):
    backend, _ = capture
    clock = [0.]
    monkeypatch.setattr(audiobackend.time, "monotonic", lambda: clock[0])
    count = audiobackend.FRAMES_PER_BUFFER
    backend.ringBuffer.load(np.zeros((3 * count, 8), dtype=np.float32))
    packets = []

    def process(*packet):
        packets.append(packet)
        clock[0] += .001

    backend.new_data_available.connect(process)
    backend.fetchAudioData()
    assert len(packets) == 3
    assert backend.ringBuffer.read_available == 0
