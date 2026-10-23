import QtQuick 2.15
import polyfriture 1.0

ChannelPlotGrid {
    scopedata: viewModel
    channels: viewModel.channels
    plotDelegate: Component {
        Item {
            property var channelModel: parent.channelData
            Repeater {
                model: parent.channelModel.plot_items
                PlotFilledCurve {
                    anchors.fill: parent
                    curve: modelData
                }
            }
            Item {
                visible: channelModel.bar_labels_x_distance * parent.width > fontMetrics.boundingRect("100").height
                anchors.fill: parent

                FontMetrics {
                    id: fontMetrics
                }

                SystemPalette { id: systemPalette; colorGroup: SystemPalette.Active }

                Repeater {
                    model: channelModel.barLabels

                    Item {
                        x: modelData.x * parent.width - barLabel.height / 2
                        y: Math.max(4, Math.min(modelData.y * parent.height + 4, parent.height - barLabel.width - 4))

                        // width vs. height: childrenRect doesn't take transformations into account.
                        // https://bugreports.qt-project.org/browse/QTBUG-38953
                        implicitWidth: barLabel.height
                        implicitHeight: barLabel.width

                        Text {
                            id: barLabel
                            text: modelData.unscaled_x
                            rotation: 270
                            transformOrigin: Item.Center
                            anchors.centerIn: parent
                            color: modelData.y * parent.parent.height + 4 > parent.parent.height - barLabel.width - 4 ? systemPalette.windowText : systemPalette.base
                        }
                    }
                }
            }
        }
    }
}
