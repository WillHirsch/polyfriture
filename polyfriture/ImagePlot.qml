import QtQuick 2.15
import QtQuick.Window 2.2
import QtQuick.Layouts 1.15
import QtQuick.Shapes 1.15
import polyfriture 1.0

ChannelPlotGrid {
    objectName: "spectrogram-channel-grid"
    scopedata: viewModel
    channels: viewModel.channels
    plotDelegate: Component {
        SpectrogramItem {
            anchors.fill: parent
            objectName: "spectrogram-channel-image-" + parent.channelIndex
            curve: parent.channelData.plot_items[0]
        }
    }
}
