import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.2
import polyfriture 1.0

Rectangle {
    id: main_window
    SystemPalette { id: systemPalette; colorGroup: SystemPalette.Active }
    color: systemPalette.window

    property string fixedFont

    RowLayout {
        objectName: "main_row_layout"
        anchors.fill: parent
        spacing: 3

        Levels {
            level_view_model: main_window_view_model.level_view_model
            Layout.fillHeight: true
            Layout.margins: 5
            fixedFont: main_window.fixedFont
        }

        TileLayout {
            id: tileLayout
            objectName: "main_tile_layout"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: 5
        }
    }
}
