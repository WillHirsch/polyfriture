// Copyright (C) 2026 Will Hirsch
// SPDX-License-Identifier: GPL-3.0-only
// Part of Polyfriture. See COPYING.txt for the GNU General Public License.

import QtQuick 2.15
import QtQuick.Window 2.2
import QtQuick.Layouts 1.15
import QtQuick.Shapes 1.15
import polyfriture 1.0

Plot {
    scopedata: viewModel

    Repeater {
        model: scopedata.plot_items

        PlotFilledCurve {
            anchors.fill: parent
            curve: modelData
        }
    }

    Column {
        anchors.fill: parent
        spacing: 0
        FrequencyTracker {
            visible: scopedata.showFrequencyTracker
            anchors.left: parent.left
            anchors.right: parent.right
            fmaxValue: scopedata.fmaxValue
            fmaxLogicalValue: scopedata.fmaxLogicalValue
        }

        FrequencyTracker {
            visible: scopedata.showPitchTracker
            anchors.left: parent.left
            anchors.right: parent.right
            fmaxValue: scopedata.fpitchDisplayText
            fmaxLogicalValue: scopedata.fpitchValue
        }
    }
}
