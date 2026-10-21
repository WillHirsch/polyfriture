import QtQuick 2.15
import QtQuick.Controls 2.15
import polyfriture 1.0

Row {
    id: root
    required property Burst_Generator_Settings_View_Model settingsViewModel
    spacing: 8

    SystemPalette { id: systemPalette; colorGroup: SystemPalette.Active }

    Text {
        text: "Period:"
        color: systemPalette.text
        anchors.verticalCenter: parent.verticalCenter
    }
    DecimalSpinBox {   
        binding: root.settingsViewModel.period
        onDecimalValueModified: root.settingsViewModel.period = decimalValue
        suffix: " s"
        decimalFrom: root.settingsViewModel.periodMinimum
        decimalTo: root.settingsViewModel.periodMaximum
    }
}
