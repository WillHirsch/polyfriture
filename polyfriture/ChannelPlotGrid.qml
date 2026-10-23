import QtQuick 2.15
import polyfriture 1.0
import "channelGridLayout.js" as ChannelGridLayout

Rectangle {
    id: grid
    anchors.fill: parent
    clip: true
    color: palette.window
    SystemPalette { id: palette; colorGroup: SystemPalette.Active }
    FontMetrics { id: fontMetrics }

    // One set of axes/parameters belongs to the panel. Delegates contain only
    // data rendering; using Plot.qml here would give each cell private margins.
    required property ScopeData scopedata
    required property Component plotDelegate
    // Publish labels and rendering models together, in capture-row order.
    property var channels: []
    property bool showHorizontalAxis: true
    property bool showPlotArea: true
    property int configuredColumns: Store.channel_grid_columns
    property real headerHeight: fontMetrics.height + 4
    property real columnSpacing: 8
    property real rowSpacing: fontMetrics.height / 2 + 4
    property Component headerDelegate: Component {
        Text {
            text: parent.channelLabel
            color: palette.windowText
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }

    readonly property int channelCount: channels.length
    readonly property int columnCount: Math.min(channelCount, Math.max(1, configuredColumns))
    readonly property int rowCount: columnCount ? Math.ceil(channelCount / columnCount) : 0
    readonly property var placements: ChannelGridLayout.placements(channelCount, configuredColumns)
    readonly property bool hasColorAxis: channelCount > 0 && scopedata.show_color_axis

    // Measure shared gutters once. Their size cannot depend on a particular
    // channel's header, readout or presence of axis decorations.
    VerticalScale {
        id: yMeasure
        visible: false
        scale_division: grid.scopedata.vertical_axis.scale_division
    }
    HorizontalScale {
        id: xMeasure
        visible: false
        width: grid.dataWidth
        scale_division: grid.scopedata.horizontal_axis.scale_division
    }
    function maximumLabelWidth(ticks) {
        var width = 0;
        for (var i = 0; i < ticks.length; ++i)
            width = Math.max(width, fontMetrics.boundingRect(ticks[i].value).width);
        return width;
    }
    readonly property real endpointMargin: showHorizontalAxis ? maximumLabelWidth(scopedata.horizontal_axis.scale_division.logicalMajorTicks) / 2 : 0
    readonly property real leftGutter: Math.min(Math.max(0, width),
        Math.max(endpointMargin, fontMetrics.height + 4 + yMeasure.implicitWidth))
    readonly property real desiredRightGutter: hasColorAxis
        ? Math.max(endpointMargin, colorScaleLoader.width + fontMetrics.height + 4)
        : endpointMargin
    readonly property real rightGutter: Math.min(Math.max(0, width - leftGutter), desiredRightGutter)
    readonly property real topGutter: Math.min(Math.max(0, height), yMeasure.topOverflow)
    readonly property real bottomGutter: Math.min(Math.max(0, height - topGutter),
        Math.max(yMeasure.topOverflow, showHorizontalAxis ? xMeasure.implicitHeight + fontMetrics.height + 4 : 0))
    readonly property real innerWidth: Math.max(0, width - leftGutter - rightGutter)
    readonly property real innerHeight: Math.max(0, height - topGutter - bottomGutter)
    readonly property real effectiveColumnSpacing: columnCount > 1
        ? Math.min(Math.max(0, columnSpacing, 2 * endpointMargin + 4), innerWidth / (columnCount - 1)) : 0
    readonly property real effectiveRowSpacing: rowCount > 1
        ? Math.min(Math.max(0, rowSpacing), innerHeight / (rowCount - 1)) : 0
    readonly property real dataWidth: columnCount
        ? Math.max(0, (innerWidth - (columnCount - 1) * effectiveColumnSpacing) / columnCount) : 0
    readonly property real cellHeight: rowCount
        ? Math.max(0, (innerHeight - (rowCount - 1) * effectiveRowSpacing) / rowCount) : 0
    readonly property real effectiveHeaderHeight: Math.min(Math.max(0, headerHeight), cellHeight)
    readonly property real dataHeight: Math.max(0, cellHeight - effectiveHeaderHeight)
    readonly property real dataOriginX: leftGutter
    readonly property real dataOriginY: topGutter + effectiveHeaderHeight
    readonly property real dataBottom: Math.max(topGutter, height - bottomGutter)

    Repeater {
        model: grid.channels
        delegate: Item {
            id: cell
            required property int index
            required property var modelData
            readonly property int channelIndex: index
            readonly property var placement: grid.placements[index] || ({column: 0, rowFromBottom: 0})
            readonly property int column: placement.column
            readonly property int rowFromBottom: placement.rowFromBottom
            objectName: "channel-grid-cell-" + index
            x: grid.leftGutter + column * (grid.dataWidth + grid.effectiveColumnSpacing)
            y: grid.topGutter + (grid.rowCount - 1 - rowFromBottom) * (grid.cellHeight + grid.effectiveRowSpacing)
            width: grid.dataWidth
            height: grid.cellHeight
            clip: true

            Loader {
                width: parent.width
                height: grid.effectiveHeaderHeight
                clip: true
                property int channelIndex: cell.index
                property var channelData: cell.modelData
                property string channelLabel: channelData ? channelData.label : ""
                sourceComponent: grid.headerDelegate
            }
            PlotArea {
                objectName: "channel-grid-data-" + cell.index
                y: grid.effectiveHeaderHeight
                width: parent.width
                height: grid.dataHeight
                visible: width > 0 && height > 0
                clip: true
                horizontal_axis: grid.scopedata.horizontal_axis
                vertical_axis: grid.scopedata.vertical_axis
                decorationsVisible: grid.showPlotArea
                Loader {
                    anchors.fill: parent
                    active: width > 0 && height > 0
                    property int channelIndex: cell.index
                    property var channelData: cell.modelData
                    property string channelLabel: channelData ? channelData.label : ""
                    sourceComponent: grid.plotDelegate
                }
            }
        }
    }

    Repeater {
        model: grid.rowCount
        delegate: VerticalScale {
            required property int index
            objectName: "channel-grid-y-scale-" + index
            x: grid.leftGutter - width
            y: grid.dataOriginY + index * (grid.cellHeight + grid.effectiveRowSpacing)
            width: implicitWidth
            height: grid.dataHeight
            scale_division: grid.scopedata.vertical_axis.scale_division
        }
    }
    Repeater {
        model: grid.rowCount
        delegate: Item {
            required property int index
            x: grid.leftGutter - yMeasure.implicitWidth - 4 - width
            y: grid.dataOriginY + index * (grid.cellHeight + grid.effectiveRowSpacing)
            width: fontMetrics.height
            height: grid.dataHeight
            Text {
                anchors.centerIn: parent
                rotation: -90
                width: parent.height
                height: parent.width
                text: grid.scopedata.vertical_axis.name
                color: palette.windowText
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
            }
        }
    }
    Repeater {
        model: grid.showHorizontalAxis ? grid.columnCount : 0
        delegate: HorizontalScale {
            required property int index
            objectName: "channel-grid-x-scale-" + index
            x: grid.leftGutter + index * (grid.dataWidth + grid.effectiveColumnSpacing)
            y: grid.dataBottom
            width: grid.dataWidth
            height: implicitHeight
            scale_division: grid.scopedata.horizontal_axis.scale_division
        }
    }
    Repeater {
        model: grid.showHorizontalAxis ? grid.columnCount : 0
        delegate: Text {
            required property int index
            x: grid.leftGutter + index * (grid.dataWidth + grid.effectiveColumnSpacing)
            y: grid.dataBottom + xMeasure.implicitHeight + 4
            width: grid.dataWidth
            height: fontMetrics.height
            text: grid.scopedata.horizontal_axis.name
            horizontalAlignment: Text.AlignHCenter
            color: palette.windowText
            elide: Text.ElideRight
        }
    }
    Loader {
        id: colorScaleLoader
        active: grid.hasColorAxis
        x: grid.width - grid.rightGutter + 2
        y: grid.dataOriginY
        width: item ? item.implicitWidth : 0
        // ColorBar allocates one scanline per integer pixel. Keep its shared
        // extent pixel-aligned even when font/header metrics are fractional.
        height: Math.floor(Math.max(0, grid.dataBottom - y))
        sourceComponent: Component {
            ColorScale {
                objectName: "channel-grid-color-scale"
                scale_division: grid.scopedata.color_axis.scale_division
            }
        }
    }
    Item {
        visible: grid.hasColorAxis
        x: colorScaleLoader.x + colorScaleLoader.width + 2
        y: colorScaleLoader.y
        width: fontMetrics.height
        height: colorScaleLoader.height
        Text {
            anchors.centerIn: parent
            rotation: 90
            width: parent.height
            height: parent.width
            text: grid.scopedata.color_axis.name
            color: palette.windowText
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }
    }
}
