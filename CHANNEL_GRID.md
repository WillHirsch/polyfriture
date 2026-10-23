# Shared channel grid

`ChannelPlotGrid.qml` supplies the layout for channel-based panels. It renders
one equal-sized data rectangle per selected channel, with a uniform header
above every rectangle. Row Y scales, column X scales and the optional colorbar
are outside the data delegates. Every cell references the panel's same axes,
so ranges, transforms and color normalization are shared.

The global **Columns within each panel** setting defaults to two. It is saved
as `AudioBackend/channelGridColumns` with the other global display preferences
and exposed as `Store.channel_grid_columns`. It changes all grids immediately;
it does not rearrange whole panels. The editor accepts positive integers up
to Qt's integer range, without an additional layout or channel-count cap.
FFT Spectrum, 2D Spectrogram, Octave Spectrum, Long-time Levels, Pitch Tracker
and Level Meter use this component. Scope overlays all selected channels on
one plot; Generator remains an output utility.

## Placement

Use `min(configuredColumns, channelCount)` nonempty columns. Balance their
populations, giving an extra channel to each leftmost column when needed.
Fill each column bottom-to-top before proceeding right. Five channels and
three columns therefore appear as:

```text
2  4  .
1  3  5
```

`placements` exposes `{column, rowFromBottom}` coordinates. This bottom-left
coordinate system keeps the bottom and left boundaries populated. There are
no delegates or axes for empty slots above shorter columns.

The Spectrogram panel can rotate clockwise by 90 degrees. Frequency increases
rightward and newest audio appears at the bottom, with labels remaining
upright. This transposes the occupied cell coordinates: the global column
count becomes the rotated row count. The panel still uses one shared colorbar
and equal data rectangles, and changing orientation preserves its history.

## Delegate contract

Supply the panel's `scopedata`, ordered `channels` collection, and a
`plotDelegate` component. Each channel object has a `label` and its rendering
data. Publish the collection together so names and data cannot change order
independently. For example:

```qml
ChannelPlotGrid {
    scopedata: viewModel.axes
    channels: viewModel.channelViews
    plotDelegate: Component {
        PlotCurve {
            anchors.fill: parent
            curve: parent.channelData.curve
        }
    }
}
```

Loaded delegates receive `parent.channelIndex`, `parent.channelLabel` and
`parent.channelData` (the channel object itself). The plot delegate contains data rendering only; it must
not contain `Plot.qml`, private axes or its own colorbar. A panel may replace
`headerDelegate` using the same contract for readouts or annotations. All
headers receive the panel-wide `headerHeight` regardless of their content's
implicit size. Long default names are elided; custom headers are clipped to
their allocated area. Channel-specific content cannot change plot geometry.

Shared gutters account for axis text and endpoint tick labels. Data widths
and heights are computed once and applied identically to every cell. The
public `dataWidth`, `dataHeight`, `dataOriginX` and `dataOriginY` properties
describe the geometry. A small available area reduces spacing and headers,
then reduces the data dimensions to zero as necessary. Dimensions remain
nonnegative and rendering is clipped; the component imposes no minimum size.

The QML tests instantiate synthetic delegates and real shared axes, checking
placement, incomplete grids, resizing, names/readouts, tiny sizes, shared
scales, a single colorbar, and live global-setting changes without audio
hardware or installed application settings.
