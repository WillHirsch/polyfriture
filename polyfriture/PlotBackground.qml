// Copyright (C) 2026 Will Hirsch
// SPDX-License-Identifier: GPL-3.0-only
// Part of Polyfriture. See COPYING.txt for the GNU General Public License.

import QtQuick 2.15
import QtQuick.Layouts 1.15
import QtQuick.Shapes 1.15

Rectangle {
    id: background

    SystemPalette { id: systemPalette; colorGroup: SystemPalette.Active }

    gradient: Gradient {
        GradientStop { position: -0.5; color: systemPalette.window }
        GradientStop { position: 0.5; color: systemPalette.base }
    }
}