import QtQuick 2.15
import polyfriture 1.0

ChannelPlotGrid {
    id: meters
    scopedata: viewModel
    channels: viewModel.channels
    showHorizontalAxis: false
    showPlotArea: false
    FontMetrics { id: metrics }
    headerHeight: 3 * metrics.height + 8
    headerDelegate: Component {
        Column {
            spacing: 2
            Text {
                width: parent.width
                text: parent.parent.channelLabel
                color: palette.windowText
                elide: Text.ElideRight
            }
            Text {
                width: parent.width
                text: "Peak " + meters.levelText(parent.parent.channelData.level_data_slow.level_max)
                color: palette.windowText
                elide: Text.ElideRight
            }
            Text {
                width: parent.width
                text: "RMS  " + meters.levelText(parent.parent.channelData.level_data_slow.level_rms)
                color: palette.windowText
                elide: Text.ElideRight
            }
        }
    }
    plotDelegate: Component {
        SingleMeter {
            levelMax: parent.channelData.level_data.level_max
            levelRms: parent.channelData.level_data.level_rms
            levelIECMaxBallistic: parent.channelData.level_data_ballistic.peak_iec
        }
    }
    function levelText(value) {
        return (value < -150 ? "-Inf" : value.toFixed(1)) + " dB FS";
    }
    SystemPalette { id: palette; colorGroup: SystemPalette.Active }
}
