// Copyright (C) 2026 Will Hirsch
// SPDX-License-Identifier: GPL-3.0-only
// Part of Polyfriture. See COPYING.txt for the GNU General Public License.

import QtQuick 2.15
import QtQuick.Window 2.2
import QtQuick.Layouts 1.15
import QtQuick.Shapes 1.15
import polyfriture 1.0
import "plotItemColors.js" as PlotItemColors

Plot {
    scopedata: viewModel

    Repeater {
        model: scopedata.plot_items

        PlotCurve {
            anchors.fill: parent
            color: PlotItemColors.color(index)
            curve: modelData
        }
    }
}