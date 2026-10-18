// Copyright (C) 2026 Will Hirsch
// SPDX-License-Identifier: GPL-3.0-only
// Part of Polyfriture. See COPYING.txt for the GNU General Public License.

import QtQuick 2.15
import QtQuick.Controls 2.15
import polyfriture 1.0

Column {
    id: root
    required property Sweep_Generator_Settings_View_Model settingsViewModel

    spacing: 8

    SystemPalette { id: systemPalette; colorGroup: SystemPalette.Active }

    Row {
        spacing: 8

        Text {
            text: "Start frequency:"
            color: systemPalette.text
            anchors.verticalCenter: parent.verticalCenter
        }

        DecimalSpinBox {   
            binding: root.settingsViewModel.start_frequency
            onDecimalValueModified: root.settingsViewModel.start_frequency = decimalValue
        }
    }

    Row {
        spacing: 8

        Text {
            text: "Stop frequency:"
            color: systemPalette.text
            anchors.verticalCenter: parent.verticalCenter
        }

        DecimalSpinBox {   
            binding: root.settingsViewModel.stop_frequency
            onDecimalValueModified: root.settingsViewModel.stop_frequency = decimalValue
        }
    }

    Row {
        spacing: 8

        Text {
            text: "Period:"
            color: systemPalette.text
            anchors.verticalCenter: parent.verticalCenter
        }
        DecimalSpinBox {   
            binding: root.settingsViewModel.period
            onDecimalValueModified: root.settingsViewModel.period = decimalValue
            suffix: " s"
            decimalFrom: 0.01
            decimalTo: 60
        }
    }
}
