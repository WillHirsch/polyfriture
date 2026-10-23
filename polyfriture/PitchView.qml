import QtQuick 2.15
import polyfriture 1.0

ChannelPlotGrid {
    scopedata: viewModel
    channels: viewModel.channels
    SystemPalette { id: channelPalette; colorGroup: SystemPalette.Active }
    // All channels reserve the same header space, independent of note/value width.
    headerDelegate: Component {
        Text {
            objectName: "pitch-channel-header-" + parent.channelIndex
            text: parent.channelLabel + "   " + parent.channelData.note
                  + "   " + parent.channelData.pitch + " " + parent.channelData.pitch_unit
            textFormat: Text.PlainText
            color: channelPalette.windowText
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }
    plotDelegate: Component {
        PlotCurve {
            anchors.fill: parent
            color: "red"
            curve: parent.channelData.plot_items[0]
        }
    }
}
