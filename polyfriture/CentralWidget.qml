// Copyright (C) 2026 Will Hirsch
// SPDX-License-Identifier: GPL-3.0-only
// Part of Polyfriture. See COPYING.txt for the GNU General Public License.

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.2
import polyfriture 1.0

Rectangle {
    SystemPalette { id: systemPalette; colorGroup: SystemPalette.Active }
    color: systemPalette.window
    anchors.fill: parent

    property string fixedFont

    TileLayout {
        id: root
        objectName: "main_tile_layout"
        anchors.fill: parent
    }
}

