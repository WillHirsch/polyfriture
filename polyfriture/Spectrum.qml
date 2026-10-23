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
        }
    }
    headerDelegate: Component {
        Text {
            property var channelModel: parent.channelData
            text: parent.channelLabel
                + (channelModel.showFrequencyTracker ? "    Max: " + channelModel.fmaxValue : "")
                + (channelModel.showPitchTracker ? "    Pitch: " + channelModel.fpitchDisplayText : "")
            color: palette.windowText
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            SystemPalette { id: palette; colorGroup: SystemPalette.Active }
        }
    }
}
