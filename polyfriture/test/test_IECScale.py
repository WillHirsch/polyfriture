# Copyright (C) 2026 Will Hirsch
# SPDX-License-Identifier: GPL-3.0-only
# Part of Polyfriture. See COPYING.txt for the GNU General Public License.

if __name__ == '__main__':
    import numpy as np
    import matplotlib.pyplot as plt

    import sys
    sys.path.insert(0, '.')

    import polyfriture.qsynthmeter as meter # type: ignore

    scale = meter.IECScale()

    x = np.linspace(-100, 10, 1000)
    y = [scale.iec_scale(x0) for x0 in x]

    plt.figure()
    plt.plot(x, y)

    plt.show()
