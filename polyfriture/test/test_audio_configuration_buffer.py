"""Generation boundaries clear history before consumers see new audio."""

import numpy as np
import pytest

from polyfriture.audiobuffer import AudioBuffer
from polyfriture.channel_configuration import ChannelConfiguration


def configuration(channels, generation, device=3):
    return ChannelConfiguration(device, channels, 8, generation)


@pytest.mark.parametrize("channels", [(0, 2, 7), (2,), (1, 5)])
def test_configuration_resets_samples_cursors_and_time_before_notification(channels):
    buffer = AudioBuffer()
    buffer.handle_configuration_changed(configuration((0, 2), 1))
    buffer.handle_new_data(np.ones((2, 512)), 10., False, 1)
    observations = []
    buffer.configuration_changed.connect(lambda config: observations.append((
        config, buffer.ringbuffer.offset, buffer.ringbuffer.offset_time,
        buffer.newpoints, buffer.lastDataTime, buffer.data(512).copy())))
    next_configuration = configuration(channels, 2)
    buffer.handle_configuration_changed(next_configuration)
    assert len(observations) == 1
    seen, offset, time, points, last_time, data = observations[0]
    assert seen is next_configuration
    assert (offset, time, points, last_time) == (0, 0., 0, 0.)
    np.testing.assert_array_equal(data, np.zeros((len(channels), 512)))
    buffer.handle_new_data(np.full((len(channels), 512), 2.), 20., False, 2)
    np.testing.assert_array_equal(buffer.data(1024)[:, :512], 0.)
    np.testing.assert_array_equal(buffer.data(512), 2.)


def test_old_and_premature_generations_cannot_reintroduce_history():
    buffer = AudioBuffer()
    first = configuration((0, 2), 1)
    second = configuration((1, 5), 2)
    notifications = []
    buffer.new_data_available.connect(notifications.append)
    # Data must follow its configuration, even when its count would match.
    buffer.handle_new_data(np.ones((2, 512)), 1., False, 1)
    assert buffer.ringbuffer.offset == 0
    buffer.handle_configuration_changed(first)
    buffer.handle_configuration_changed(second)
    buffer.handle_new_data(np.ones((2, 512)), 2., False, 1)
    buffer.handle_new_data(np.ones((2, 512)), 3., False, 3)
    buffer.handle_new_data(np.ones((2, 512)), 3., False)
    buffer.handle_configuration_changed(first)
    assert buffer.channel_configuration is second
    assert buffer.ringbuffer.offset == 0
    assert notifications == []
    buffer.handle_new_data(np.ones((2, 512)), 4., False, 2)
    assert buffer.ringbuffer.offset == 512
    assert len(notifications) == 1


def test_wrong_row_count_is_rejected_before_buffer_mutation():
    buffer = AudioBuffer()
    buffer.handle_configuration_changed(configuration((1, 4, 6), 1))
    with pytest.raises(ValueError, match="rows"):
        buffer.handle_new_data(np.ones((2, 512)), 1., False, 1)
    assert buffer.ringbuffer.offset == 0


def test_new_data_time_is_published_before_consumer_notification():
    buffer = AudioBuffer()
    buffer.handle_configuration_changed(configuration((0,), 1))
    times = []
    buffer.new_data_available.connect(lambda data: times.append(buffer.lastDataTime))
    buffer.handle_new_data(np.ones((1, 512)), 42., False, 1)
    assert times == [42.]
