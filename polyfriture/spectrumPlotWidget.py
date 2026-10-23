#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging

from PyQt6.QtCore import QObject

from numpy import zeros, ones, log10
import numpy as np

from polyfriture.audiobackend import SAMPLING_RATE
from polyfriture.spectrum_data import Spectrum_Data
from polyfriture.filled_curve import CurveType, FilledCurve
from polyfriture.pitch_tracker import format_frequency

# The peak decay rates (magic goes here :).
PEAK_DECAY_RATE = 1.0 - 3e-6
# Number of cycles the peak stays on hold before fall-off.
PEAK_FALLOFF_COUNT = 32  # default : 16


class SpectrumPlotWidget(QObject):

    def __init__(self, parent, *, axes=None):
        super(SpectrumPlotWidget, self).__init__(parent)

        self.logger = logging.getLogger(__name__)

        self._spectrum_data = Spectrum_Data(self, axes=axes)

        self._curve_signal = FilledCurve(CurveType.SIGNAL)
        self._spectrum_data.add_plot_item(self._curve_signal)

        self._curve_peak = FilledCurve(CurveType.PEEK, self._spectrum_data)
        self._spectrum_data.insert_plot_item(0, self._curve_peak)

        if axes is None:
            self._spectrum_data.show_legend = False
            self._spectrum_data.vertical_axis.name = "PSD (dB)"
            self._spectrum_data.vertical_axis.setTrackerFormatter(lambda x: "%.1f dB" % (x))
            self._spectrum_data.horizontal_axis.name = "Frequency (Hz)"
            self._spectrum_data.horizontal_axis.setTrackerFormatter(format_frequency)
            self._spectrum_data.horizontal_axis.show_minor_grid_lines = True

            self._spectrum_data.vertical_axis.setRange(0, 1)
            self._spectrum_data.horizontal_axis.setRange(0, 22000)

        self.paused = False

        self.peak = zeros((3,))
        self.peak_int = zeros((3,))
        self.peak_decay = ones((3,)) * PEAK_DECAY_RATE

        self.normVerticalScaleTransform = self._spectrum_data.vertical_axis.coordinate_transform
        self.normHorizontalScaleTransform = self._spectrum_data.horizontal_axis.coordinate_transform

    def qml_file_name(self):
        return "Spectrum.qml"
    
    def view_model(self):
        return self._spectrum_data

    def reset(self):
        self.peak = zeros(0)
        self.peak_int = zeros(0)
        self.peak_decay = zeros(0)
        empty = zeros(0)
        self._curve_signal.setData(empty, empty, empty, empty, 1.)
        self._curve_peak.setData(empty, empty, empty, empty, 1.)
        self._spectrum_data.setFmax("", 0.)
        self._spectrum_data.setFpitch("", 0.)

    def setfreqscale(self, scale):
        self.normHorizontalScaleTransform.setScale(scale)
        self._spectrum_data.horizontal_axis.setScale(scale)

    def setfreqrange(self, minfreq, maxfreq):
        self.xmin = minfreq
        self.xmax = maxfreq

        self._spectrum_data.horizontal_axis.setRange(minfreq, maxfreq)
        self.normHorizontalScaleTransform.setRange(minfreq, maxfreq)

    def setspecrange(self, spec_min, spec_max):
        if spec_min > spec_max:
            spec_min, spec_max = spec_max, spec_min

        self._spectrum_data.vertical_axis.setRange(spec_min, spec_max)
        self.normVerticalScaleTransform.setRange(spec_min, spec_max)

    def setweighting(self, weighting):
        if weighting == 0:
            title = "PSD (dB)"
        elif weighting == 1:
            title = "PSD (dB A)"
        elif weighting == 2:
            title = "PSD (dB B)"
        else:
            title = "PSD (dB C)"

        self._spectrum_data.vertical_axis.name = title

    def setShowFreqLabel(self, showFreqLabel):
        self._spectrum_data.showFrequencyTracker = showFreqLabel

    def setShowPitchLabel(self, showPitchLabel):
        self._spectrum_data.showPitchTracker = showPitchLabel

    def setdata(self, x, y, fmax, fpitch):
        if not self.paused:
            if fmax < 2e2:
                text = "%.1f Hz" % (fmax)
            else:
                text = "%d Hz" % (np.rint(fmax))
            self._spectrum_data.setFmax(
                text, self.normHorizontalScaleTransform.toScreen(fmax)
            )
            self._spectrum_data.setFpitch(
                format_frequency(fpitch),
                self.normHorizontalScaleTransform.toScreen(fpitch),
            )

            M = np.max(y)
            m = self.normVerticalScaleTransform.coord_min
            y_int = (y - m) / (np.abs(M - m) + 1e-3)

            x_left = zeros(x.shape)
            x_right = zeros(x.shape)
            x_left[0] = 1e-10
            x_left[1:] = (x[1:] + x[:-1]) / 2.0
            x_right[:-1] = x_left[1:]
            x_right[-1] = float(SAMPLING_RATE / 2)
            scaled_x_left = self.normHorizontalScaleTransform.toScreen(x_left)
            scaled_x_right = self.normHorizontalScaleTransform.toScreen(x_right)

            scaled_y = 1.0 - self.normVerticalScaleTransform.toScreen(y)
            z = y_int
            self._curve_signal.setData(
                scaled_x_left, scaled_x_right, scaled_y, z, 1.0
            )

            self.compute_peaks(y)
            scaled_peak = 1.0 - self.normVerticalScaleTransform.toScreen(self.peak)
            z_peak = self.peak_int
            self._curve_peak.setData(
                scaled_x_left, scaled_x_right, scaled_peak, z_peak, 1.0
            )

    def draw(self):
        return

    def pause(self):
        self.paused = True

    def restart(self):
        self.paused = False

    def canvasUpdate(self):
        return

    def compute_peaks(self, y):
        if len(self.peak) != len(y):
            y_ones = ones(y.shape)
            self.peak = y_ones * (-500.0)
            self.peak_int = zeros(y.shape)
            self.peak_decay = y_ones * 20.0 * log10(PEAK_DECAY_RATE) * 5000

        mask1 = self.peak < y
        mask2 = ~mask1
        mask2_a = mask2 * (self.peak_int < 0.2)
        mask2_b = mask2 * (self.peak_int >= 0.2)

        self.peak[mask1] = y[mask1]
        self.peak[mask2_a] = self.peak[mask2_a] + self.peak_decay[mask2_a]

        self.peak_decay[mask1] = 20.0 * log10(PEAK_DECAY_RATE) * 5000
        self.peak_decay[mask2_a] += 20.0 * log10(PEAK_DECAY_RATE) * 5000

        self.peak_int[mask1] = 1.0
        self.peak_int[mask2_b] *= 0.975
