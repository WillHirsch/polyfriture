import QtQuick 2.15
import polyfriture 1.0

Rectangle {
    SystemPalette { id: systemPalette; colorGroup: SystemPalette.Active }
    color: systemPalette.window
    property string fixedFont

    TileLayout {
        objectName: "main_tile_layout"
        anchors.fill: parent
        anchors.margins: 5
    }
}
