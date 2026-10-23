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
import math
import time

from PyQt6 import QtCore
import sounddevice
import rtmixer
from numpy import ndarray, int8, int16, float64, float32, frombuffer, concatenate
import numpy as np
from polyfriture.channel_configuration import ChannelConfiguration

# the sample rate below should be dynamic, taken from PyAudio/PortAudio
SAMPLING_RATE = 48000
FRAMES_PER_BUFFER = 512

__audiobackendInstance = None

# python-sounddevice (bindings to PortAudio)
# > no device friendly name
# > suffer from PortAudio bugs
# > uses old PortAudio binaries
# > sounddevice provides nice Python bindngs
# > rtmixer provides nice C ringbuffer on top of sounddevice

# rtaudio
# > better maintained than PortAudio
# > no device friendly name
# > no ios/android support
# > no nice Python bindings

# qtmultimedia
# > shipped with Qt5
# > no device friendly name
# > supports iOS and android
# > opaque

# python-soundcard
# > not a lot of devs / users
# > no android support
# > provides device ids and friendly name
# > doc, features are lacking


def AudioBackend():
    global __audiobackendInstance
    if __audiobackendInstance is None:
        __audiobackendInstance = __AudioBackend()
    return __audiobackendInstance


class __AudioBackend(QtCore.QObject):

    underflow = QtCore.pyqtSignal()
    configuration_changed = QtCore.pyqtSignal(object)
    new_data_available = QtCore.pyqtSignal(ndarray, float, bool, int)

    def __init__(self):
        QtCore.QObject.__init__(self)

        self.logger = logging.getLogger(__name__)

        self.channel_configuration = None
        self.running = True

        self.logger.info("Initializing audio backend")

        # look for devices
        self.input_devices = self.get_input_devices()
        self.output_devices = self.get_output_devices()

        self.logger.info(f"Found {len(self.input_devices)} input devices and {len(self.output_devices)} output devices")

        self.device = None

        self.stream = None
        self.ringBuffer = None
        self.action = None
        self.nchannels_max = 0
        self.stream_start_time = 0.
        self.stream_read_index = 0
        self.xruns = 0

        # we will try to open all the input devices until one
        # works, starting by the default input device
        for index in range(len(self.input_devices)):
            if self.select_input_device(index)[0]:
                break

        self.chunk_number = 0

        self.devices_with_timing_errors = []

        # throttle the "ringbuffer lagging behind" warning so a persistently
        # starving input (e.g. no live capture device, as in headless CI) does
        # not spam the log on every fetch cycle.
        self._last_lag_warning = 0.0

    def close(self):
        if self.stream is not None:
            self._retire_stream(self.stream)
            self.stream = None
        self.ringBuffer = None
        self.action = None
        self.running = False

    def _retire_stream(self, stream):
        # An unplugged old device must not turn a committed replacement into
        # an apparent failure, or prevent the remaining resources being closed.
        for operation in (stream.stop, stream.close):
            try:
                operation()
            except Exception:
                self.logger.exception("Failed to retire audio stream")

    # method
    def get_readable_devices_list(self):
        raw_devices = sounddevice.query_devices()

        try:
            default_input_device = sounddevice.query_devices(kind='input')
            default_input_device['index'] = raw_devices.index(default_input_device)
        except sounddevice.PortAudioError as err:
            self.logger.warning(f"Failed to query the default input device: {err}")
            default_input_device = None

        devices_list = []
        for device in self.input_devices:
            api = sounddevice.query_hostapis(device['hostapi'])['name']

            if default_input_device is not None and device['index'] == default_input_device['index']:
                extra_info = ' (default)'
            else:
                extra_info = ''

            nchannels = device['max_input_channels']

            desc = "%s (%d channels) (%s) %s" % (device['name'], nchannels, api, extra_info)

            devices_list += [desc]

        return devices_list

    def get_input_device_identities(self):
        """Device names and host APIs in the same order as the device selector.

        Unlike the display labels, these identities do not contain the current
        default marker, channel count, or enumeration index.
        """
        return [(device['name'], sounddevice.query_hostapis(device['hostapi'])['name'])
                for device in self.input_devices]

    def get_input_device_channel_count(self, index):
        return self.input_devices[index]['max_input_channels']

    # method
    def get_readable_output_devices_list(self):
        output_devices = self.get_output_devices()

        # if there are no output devices at all,
        # sounddevice.query_devices(kind='output') raises PortAudioError ("Error
        # querying device -1").
        # Degrade to an empty list.
        if len(output_devices) == 0:
            return []

        raw_devices = sounddevice.query_devices()
        try:
            default_output_device = sounddevice.query_devices(kind='output')
            default_output_device['index'] = raw_devices.index(default_output_device)
        except sounddevice.PortAudioError as err:
            self.logger.warning(f"No default output device available: {err}")
            default_output_device = None

        devices_list = []
        for device in output_devices:
            api = sounddevice.query_hostapis(device['hostapi'])['name']

            if default_output_device is not None and device['index'] == default_output_device['index']:
                extra_info = ' (default)'
            else:
                extra_info = ''

            nchannels = device['max_output_channels']

            desc = "%s (%d channels) (%s) %s" % (device['name'], nchannels, api, extra_info)

            devices_list += [desc]

        return devices_list

    # method
    def get_default_input_device(self):
        try:
            index = sounddevice.default.device[0]
        except IOError:
            index = None

        return index

    # method
    def get_default_output_device(self):
        try:
            index = sounddevice.default.device[1]
        except IOError:
            index = None

        return index

    # method
    # returns a list of input devices index, starting with the system default
    def get_input_devices(self):
        devices = sounddevice.query_devices()

        # early exit if there is no input device. Otherwise query_devices(kind='input') fails
        input_devices = [device for device in devices if device['max_input_channels'] > 0]

        if len(input_devices) == 0:
            return []

        try:
            default_input_device = sounddevice.query_devices(kind='input')
        except sounddevice.PortAudioError as err:
            self.logger.exception(f"Failed to query the default input device: {err}")
            default_input_device = None

        input_devices = []
        if default_input_device is not None:
            # start by the default input device
            default_input_device['index'] = devices.index(default_input_device)
            input_devices += [default_input_device]

        for device in devices:
            # select only the input devices by looking at the number of input channels
            if device['max_input_channels'] > 0:
                device['index'] = devices.index(device)
                # default input device has already been inserted
                if default_input_device is None or device['index'] != default_input_device['index']:
                    input_devices += [device]

        return input_devices

    # method
    # returns a list of output devices index, starting with the system default
    def get_output_devices(self):
        devices = sounddevice.query_devices()

        # sounddevice.query_devices(kind='output') raises PortAudioError when
        # there is no default output device.
        # Degrade gracefully instead.
        try:
            default_output_device = sounddevice.query_devices(kind='output')
        except sounddevice.PortAudioError as err:
            self.logger.warning(f"No default output device available: {err}")
            default_output_device = None

        output_devices = []
        if default_output_device is not None:
            # start by the default output device
            default_output_device['index'] = devices.index(default_output_device)
            output_devices += [default_output_device]

        for device in devices:
            # select only the output devices by looking at the number of output channels
            if device['max_output_channels'] > 0:
                device['index'] = devices.index(device)
                # default output device has already been inserted
                if default_output_device is not None and device['index'] != default_output_device['index']:
                    output_devices += [device]

        return output_devices

    # method.
    # The index parameter is the index in the self.input_devices list of devices !
    # The return parameter is also an index in the same list.
    def select_input_device(self, index, channel_ids=None):
        current_index = self.get_readable_current_device()
        if isinstance(index, bool) or not isinstance(index, (int, np.integer)) or not 0 <= index < len(self.input_devices):
            return False, current_index
        device = self.input_devices[index]
        if device is self.device and self.stream is not None:
            if channel_ids is not None:
                try:
                    self.select_channels(channel_ids)
                except ValueError:
                    return False, current_index
            return True, current_index

        # Prepare the complete device/channel transaction before mutating the
        # active configuration. Invalid requests and failed open/start leave
        # both the previous stream and its queued samples usable.
        candidate = None
        try:
            generation = 1 if self.channel_configuration is None else self.channel_configuration.generation + 1
            channels = (0,) if channel_ids is None else channel_ids
            configuration = ChannelConfiguration(device['index'], channels,
                                                   device['max_input_channels'], generation)
            candidate, ringbuffer, action, channel_count = self.open_stream(device)
            configuration = ChannelConfiguration(device['index'], configuration.channel_ids,
                                                   channel_count, generation)
            if self.running:
                candidate.start()
            start_time = candidate.time
        except Exception:
            self.logger.exception("Failed to select input device and channels")
            if candidate is not None:
                self._retire_stream(candidate)
            return False, current_index

        previous_stream = self.stream
        self.stream, self.ringBuffer, self.action = candidate, ringbuffer, action
        self.device, self.nchannels_max = device, channel_count
        self.stream_start_time, self.stream_read_index = start_time, 0
        self.xruns = action.stats.input_overflows
        self._publish_configuration(configuration)
        if previous_stream is not None:
            self._retire_stream(previous_stream)
        return True, index

    def _publish_configuration(self, configuration):
        # Drop pre-change samples, including partial blocks. New array rows
        # must never be interpreted with the previous generation's identities.
        pending = self.ringBuffer.read_available
        self.ringBuffer.advance_read_index(pending)
        self.stream_read_index += pending
        self.channel_configuration = configuration
        self.configuration_changed.emit(configuration)

    def select_channels(self, channel_ids):
        """Select any nonempty subset; delivery is in physical-channel order."""
        if self.device is None:
            raise ValueError("no input device is configured")
        current = self.channel_configuration
        configuration = ChannelConfiguration(self.device['index'], channel_ids, self.nchannels_max,
                                               current.generation + 1)
        if configuration.channel_ids == current.channel_ids:
            return current
        self._publish_configuration(configuration)
        return configuration

    # method
    def open_stream(self, device):
        self.log_supported_input_formats(device)

        self.logger.info("Opening the stream for device '%s'", device['name'])

        # by default we open the device stream with all the channels
        # (interleaved in the data buffer)
        stream = rtmixer.Recorder(
            device=device['index'],
            channels=device['max_input_channels'],
            blocksize=FRAMES_PER_BUFFER,
            # latency=latency,
            samplerate=SAMPLING_RATE)

        try:
            sampleSize = 4  # float32 bytes per physical channel
            nchannels_max = device['max_input_channels']
            elementSize = nchannels_max * sampleSize
            ringbufferSeconds = 3.
            # rtmixer requires a power-of-two element count.
            ringbufferSize = 2**int(math.log2(ringbufferSeconds * SAMPLING_RATE))
            ringBuffer = rtmixer.RingBuffer(elementSize, ringbufferSize)
            action = stream.record_ringbuffer(ringBuffer)
            self.logger.info("Device claims %d ms latency", 1000 * stream.latency)
            return (stream, ringBuffer, action, nchannels_max)
        except Exception:
            self._retire_stream(stream)
            raise

    def log_supported_input_formats(self, device):
        samplerates = [22050, 44100, 48000, 96000]
        dtypes = [float32, int16, int8]
        supported_formats = []
        for samplerate in samplerates:
            for dtype in dtypes:
                try:
                    sounddevice.check_input_settings(
                        device=device['index'],
                        channels=device['max_input_channels'],
                        dtype=dtype,
                        extra_settings=None,
                        samplerate=samplerate)
                    supported_formats += [f"{samplerate} Hz, {np.dtype(dtype).name}"]
                except Exception:
                    pass # check_input_settings throws when the format is not supported

        api = sounddevice.query_hostapis(device['hostapi'])['name']
        self.logger.info(f"Supported formats for '{device['name']}' on '{api}': {supported_formats}")

    # method
    def open_output_stream(self, device, callback):
        # by default we open the device stream with all the channels
        # (interleaved in the data buffer)
        stream = sounddevice.OutputStream(
            samplerate=SAMPLING_RATE,
            blocksize=FRAMES_PER_BUFFER,
            device=device['index'],
            channels=device['max_output_channels'],
            dtype=int16,
            callback=callback)

        return stream

    def is_output_format_supported(self, device, output_format):
        # raise sounddevice.PortAudioError if the format is not supported
        # the exception message contains the details, such as an invalid sample rate
        sounddevice.check_output_settings(
            device=device['index'],
            channels=device['max_output_channels'],
            dtype=output_format,
            samplerate=SAMPLING_RATE)

    # method
    # return the index of the current input device in the input devices list
    # (not the same as the PortAudio index, since the latter is the index
    # in the list of *all* devices, not only input ones)
    def get_readable_current_device(self):
        return self.input_devices.index(self.device) if self.device is not None else -1

    # method
    def get_readable_current_channels(self):
        return [f"Channel {channel + 1}" for channel in range(self.nchannels_max)]

    # method
    def get_current_device_nchannels(self):
        return self.nchannels_max

    def get_device_outputchannels_count(self, device):
        return device['max_output_channels']

    def fetchAudioData(self):
        if not self.running or self.stream is None or self.action is None or self.ringBuffer is None:
            return

        # Capture keeps producing while synchronous panel slots process each
        # block. Yield to Qt after one block's worth of wall time so catch-up
        # cannot monopolize the GUI thread when processing falls behind. Leave
        # unread samples queued for the next display tick.
        deadline = time.monotonic() + FRAMES_PER_BUFFER / SAMPLING_RATE
        while self.ringBuffer.read_available >= FRAMES_PER_BUFFER:
            configuration = self.channel_configuration
            ringbuffer = self.ringBuffer
            read, buf1, buf2 = self.ringBuffer.get_read_buffers(FRAMES_PER_BUFFER)
            assert read == FRAMES_PER_BUFFER

            stream_time = self.get_stream_time()

            buffer1 = frombuffer(buf1, dtype='float32')
            buffer2 = frombuffer(buf2, dtype='float32')
            buffer = concatenate((buffer1, buffer2)).astype(float64)
            buffer.shape = -1, self.nchannels_max
            self.ringBuffer.advance_read_index(FRAMES_PER_BUFFER)

            # ideally we would use the exact time of the samples retrieved from the ring buffer,
            # but rtmixer does not provide it
            self.stream_read_index += read
            stream_read_time = self.stream_start_time + self.stream_read_index / SAMPLING_RATE

            # when starting a stream, it seems PortAudio gives us some data that is already in the buffer
            # so the stream start time is actually older
            # so we compensate here
            if stream_read_time > stream_time and self.stream_read_index < 100000:
                delta_seconds = stream_read_time - stream_time
                self.stream_start_time -= delta_seconds

            if stream_read_time < stream_time - 100 * FRAMES_PER_BUFFER / SAMPLING_RATE:
                now = time.monotonic()
                if now - self._last_lag_warning >= 5.0:
                    self.logger.warning("Ringbuffer lagging behind: ringbuffer time = %f, stream time = %f", stream_read_time, stream_time)
                    self._last_lag_warning = now

            floatdata = buffer[:, configuration.channel_ids].T

            input_overflows = self.action.stats.input_overflows
            input_overflow = input_overflows > self.xruns
            if input_overflow:
                self.xruns = input_overflows
                self.logger.info("Stream overflow!")
                self.underflow.emit()

            self.new_data_available.emit(floatdata, stream_read_time, input_overflow, configuration.generation)

            self.chunk_number += 1
            # A direct signal handler can reconfigure capture during delivery.
            if ringbuffer is not self.ringBuffer or configuration is not self.channel_configuration or not self.running:
                break
            if time.monotonic() >= deadline:
                break

    def get_stream_time(self) -> float:
        """The current stream time in seconds.

        The time values are monotonically increasing and have
        unspecified origin.

        This provides valid time values for the entire life of the
        stream, from when the stream is opened until it is closed.
        Starting and stopping the stream does not affect the passage of
        time as provided here.

        This time may be used for synchronizing other events to the
        audio stream.
        """

        if self.stream is None:
            return 0

        try:
            return self.stream.time
        except (sounddevice.PortAudioError, OSError):
            if self.stream.device not in self.devices_with_timing_errors:
                self.devices_with_timing_errors.append(self.stream.device)
                self.logger.exception("Failed to read stream time")
            return 0

    def pause(self):
        if self.stream is not None:
            self.stream.stop()
        self.running = False

    def restart(self):
        if self.stream is not None:
            pending = self.ringBuffer.read_available
            self.ringBuffer.advance_read_index(pending)
            self.stream.start()
            self.stream_start_time = self.stream.time
            self.stream_read_index = 0
        self.running = True
