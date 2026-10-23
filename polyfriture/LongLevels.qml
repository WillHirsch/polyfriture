import QtQuick 2.15
import polyfriture 1.0

ChannelPlotGrid {
    scopedata: viewModel
    channels: viewModel.channels
    plotDelegate: Component {
        PlotCurve {
            anchors.fill: parent
            color: "red"
            curve: parent.channelData.plot_items[0]
        }
    }
}
