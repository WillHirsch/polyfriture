#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2021 Timothée Lecomte
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

def dB_to_IEC(dB):
    if dB < -70.0:
        return 0.0
    elif dB < -60.0:
        return (dB + 70.0) * 0.0025
    elif dB < -50.0:
        return (dB + 60.0) * 0.005 + 0.025
    elif dB < -40.0:
        return (dB + 50.0) * 0.0075 + 0.075
    elif dB < -30.0:
        return (dB + 40.0) * 0.015 + 0.15
    elif dB < -20.0:
        return (dB + 30.0) * 0.02 + 0.3
    else:  # if dB < 0.0
        return (dB + 20.0) * 0.025 + 0.5

class IECScale:
    """The meter's piecewise IEC mapping, exposed through the ordinary axis API."""
    NAME = "IEC"

    @staticmethod
    def transform(value):
        import numpy as np
        return np.vectorize(dB_to_IEC, otypes=[float])(value)

    @staticmethod
    def inverse(value):
        import numpy as np
        return np.interp(value, [0., .025, .075, .15, .3, .5, 1.],
                         [-70., -60., -50., -40., -30., -20., 0.])

    @staticmethod
    def ticks(scale_min, scale_max):
        return [v for v in (-60., -50., -40., -30., -20., -10., -6., -3., 0.)
                if min(scale_min, scale_max) <= v <= max(scale_min, scale_max)], []
