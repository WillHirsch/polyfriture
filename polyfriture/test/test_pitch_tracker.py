# -*- coding: utf-8 -*-

# Copyright (C) 2024 Celeste Sinéad
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

import unittest
from unittest.mock import patch
import numpy as np
import numpy.testing as npt

from polyfriture.pitch_tracker import PitchTracker
from polyfriture.ringbuffer import RingBuffer

class PitchTrackerTest(unittest.TestCase):
    def test_new_frames(self) -> None:
        buf = RingBuffer()
        tracker = PitchTracker(buf, fft_size=4, overlap=0.5)
        buf.push(np.array([np.arange(2)]), 0.0)
        buf.push(np.array([np.arange(2, 5)]), 2 / tracker.sample_rate)
        npt.assert_array_equal(
            [np.array([np.arange(4)])],
            list(tracker.new_frames())
        )
        buf.push(np.array([np.arange(5, 8)]), 5 / tracker.sample_rate)
        npt.assert_array_equal(
            [np.array([np.arange(2, 6)]), np.array([np.arange(4, 8)])],
            list(tracker.new_frames())
        )

    def test_estimate_pitch(self) -> None:
        buf = RingBuffer()
        sample_rate = 48000
        tracker = PitchTracker(
            buf, fft_size=4096, sample_rate=sample_rate,
            min_freq=100, max_freq=1000, cres=10,
        )
        fundamental = 440.0
        phase = 2 * np.pi * fundamental * np.arange(tracker.fft_size) / sample_rate
        # The second harmonic is louder than the fundamental. Tracking the
        # loudest FFT peak would therefore report an octave too high.
        frame = np.array([0.3 * np.sin(phase) + 0.5 * np.sin(2 * phase)
                          + 0.2 * np.sin(3 * phase)])
        pitch = tracker.estimate_pitch(frame)
        assert pitch is not None
        self.assertTrue(np.isfinite(pitch))
        # Allow one configured pitch-grid step (10 cents), rather than exact
        # floating-point equality, while still rejecting an octave error.
        error_cents = 1200 * np.log2(pitch / fundamental)
        self.assertLessEqual(abs(error_cents), 10)

    def test_update(self) -> None:
        buf = RingBuffer()
        fft_size = 4096
        sample_rate = 48000
        tracker = PitchTracker(buf, fft_size=fft_size, overlap=0.5, sample_rate=sample_rate)
        block_duration = fft_size / sample_rate
        samples = np.array([np.sin(2 * np.pi * 440 * np.arange(2 * fft_size) / sample_rate)])

        # Test frame consumption and history independently of pitch estimation,
        # which is exercised above using a real harmonic signal.
        with patch.object(tracker, "estimate_pitch", side_effect=[440.0, 441.0, 442.0]) as estimate:
            buf.push(samples[:, :fft_size], 0.0)
            npt.assert_array_equal(tracker.get_estimates(block_duration), np.zeros((3,)))
            self.assertTrue(tracker.update())
            self.assertFalse(tracker.update())
            npt.assert_array_equal(tracker.get_estimates(block_duration), [0, 0, 440])
            self.assertEqual(estimate.call_count, 1)

            buf.push(samples[:, fft_size:], block_duration)
            self.assertTrue(tracker.update())
            self.assertFalse(tracker.update())
            npt.assert_array_equal(
                tracker.get_estimates(2 * block_duration), [0, 0, 440, 441, 442]
            )
            self.assertEqual(tracker.get_latest_estimate(), 442)
            self.assertEqual(estimate.call_count, 3)
