// Copyright (C) 2026 Will Hirsch
// SPDX-License-Identifier: GPL-3.0-only
// Part of Polyfriture. See COPYING.txt for the GNU General Public License.

import QtQuick 2.15
import QtQuick.Controls 2.15
import polyfriture 1.0

Row {
    id: sineSettingsRoot
    spacing: 8
    required property Sine_Generator_Settings_View_Model settingsViewModel

    SystemPalette { id: systemPalette; colorGroup: SystemPalette.Active }

    Text {
        text: "Frequency:"
        color: systemPalette.text
        anchors.verticalCenter: parent.verticalCenter
    }

    DecimalSpinBox {   
        binding: sineSettingsRoot.settingsViewModel.frequency
        onDecimalValueModified: sineSettingsRoot.settingsViewModel.frequency = decimalValue
    }
}