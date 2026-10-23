"""Exercise the reusable channel grid with real QML axes and synthetic content."""

from pathlib import Path

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPointF, QUrl
from PyQt6.QtQml import (
    QQmlComponent,
    QQmlEngine,
    QQmlExpression,
    qmlRegisterSingletonType,
    qmlRegisterType,
    qmlTypeId,
)
from PyQt6.QtQuick import QQuickItem

from polyfriture.application import QML_MODULE
from polyfriture import store as store_module
from polyfriture.axis import Axis
from polyfriture.colorBar import ColorBar
from polyfriture.plotting.coordinateTransform import CoordinateTransform
from polyfriture.plotting.scaleDivision import ScaleDivision, Tick
from polyfriture.scope_data import Scope_Data
from polyfriture.store import GetStore, Store


@pytest.fixture
def grid_factory(qt_application):
    # The wider QML integration suite registers these too. Register only missing
    # types so this module also works on its own without exhausting Qt's limit.
    for name, qml_type in (
        ("ScaleDivision", ScaleDivision),
        ("CoordinateTransform", CoordinateTransform),
        ("Axis", Axis),
        ("ColorBar", ColorBar),
        ("Tick", Tick),
        ("ScopeData", Scope_Data),
    ):
        if qmlTypeId(QML_MODULE, 1, 0, name) < 0:
            qmlRegisterType(qml_type, QML_MODULE, 1, 0, name)
    if qmlTypeId(QML_MODULE, 1, 0, "Store") < 0:
        qmlRegisterSingletonType(
            Store, QML_MODULE, 1, 0,
            lambda engine, script_engine: GetStore(), "Store",
        )

    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(warnings.extend)
    axes = Scope_Data(engine)
    axes.horizontal_axis.name = "Time (s)"
    axes.vertical_axis.name = "Amplitude"
    axes.color_axis.name = "Level (dB)"
    engine.rootContext().setContextProperty("testAxes", axes)
    component = QQmlComponent(engine)
    package_url = QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1])).toString()
    component.setData(
        f'''import QtQuick 2.15
import "{package_url}"

Item {{
    id: fixture
    property alias gridColumns: grid.configuredColumns
    property alias channels: grid.channels
    property string readout: "0 dB"
    property real preferredHeaderHeight: 24

    ChannelPlotGrid {{
        id: grid
        objectName: "test-channel-grid"
        anchors.fill: parent
        scopedata: testAxes
        plotDelegate: Component {{
            Rectangle {{
                anchors.fill: parent
                objectName: "test-channel-content-" + parent.channelIndex
                property int presentedIndex: parent.channelIndex
                property string presentedLabel: parent.channelLabel
                property var presentedPayload: parent.channelData.value
                color: Qt.hsla(parent.channelIndex / 7, 0.7, 0.4, 1)
            }}
        }}
        headerDelegate: Component {{
            Item {{
                objectName: "test-channel-header-" + parent.channelIndex
                implicitHeight: fixture.preferredHeaderHeight + parent.channelIndex * 10
                Text {{
                    anchors.fill: parent
                    text: parent.parent.channelLabel + " " + fixture.readout
                }}
            }}
        }}
    }}
}}
'''.encode(),
        QUrl(),
    )
    assert component.status() == QQmlComponent.Status.Ready, "\n".join(
        error.toString() for error in component.errors()
    )
    roots = []

    def create(count, columns=None, width=960, height=640, colorbar=False):
        axes.show_color_axis = colorbar
        properties = {
            "width": width,
            "height": height,
            "channels": [
                {"label": f"Channel {index + 1}", "value": 100 + index}
                for index in range(count)
            ],
        }
        if columns is not None:
            properties["gridColumns"] = columns
        root = component.createWithInitialProperties(properties)
        assert root is not None, "\n".join(error.toString() for error in component.errors())
        roots.append(root)
        settle(qt_application)
        grid = root.findChild(QQuickItem, "test-channel-grid")
        assert grid is not None
        return root, grid, axes

    create.qml_warnings = warnings
    yield create
    for root in roots:
        sip.delete(root)
    sip.delete(engine)


def settle(application):
    for _ in range(3):
        application.processEvents()


def named_items(root, prefix):
    # Repeater delegates join the visual tree without acquiring the grid as
    # their QObject parent, so QObject.findChildren() would miss actual cells.
    result = []
    for child in root.childItems():
        if child.objectName().startswith(prefix):
            result.append(child)
        result.extend(named_items(child, prefix))
    return result


def named_item(root, name):
    matches = [item for item in named_items(root, name) if item.objectName() == name]
    assert len(matches) == 1, f"Expected one QML item {name}, found {len(matches)}"
    return matches[0]


def position(item, grid):
    return item.mapToItem(grid, QPointF())


def assert_qml_identity(item, expression):
    # Evaluate identity in QML: PyQt may expose a dynamically typed QML property
    # as an opaque pointer rather than recovering its Python QObject wrapper.
    comparison = QQmlExpression(QQmlEngine.contextForObject(item), item, expression)
    result, undefined = comparison.evaluate()
    assert not comparison.hasError(), comparison.error().toString()
    assert not undefined and result is True


def assert_equal_data_geometry(grid, count):
    data_items = [named_item(grid, f"channel-grid-data-{index}") for index in range(count)]
    assert len(named_items(grid, "channel-grid-data-")) == count
    for item in data_items:
        assert item.width() == pytest.approx(grid.property("dataWidth"))
        assert item.height() == pytest.approx(grid.property("dataHeight"))
        assert item.width() >= 0
        assert item.height() >= 0
    return data_items


def test_incomplete_grid_fills_bottom_to_top_then_left_to_right(grid_factory):
    _, grid, _ = grid_factory(5, 3)
    assert grid.property("rowCount") == 2
    assert grid.property("columnCount") == 3
    cells = [named_item(grid, f"channel-grid-cell-{index}") for index in range(5)]
    assert [(cell.property("column"), cell.property("rowFromBottom")) for cell in cells] == [
        (0, 0), (0, 1), (1, 0), (1, 1), (2, 0),
    ]
    points = [position(cell, grid) for cell in cells]
    assert points[0].x() == points[1].x() < points[2].x() == points[3].x() < points[4].x()
    assert points[1].y() == points[3].y() < points[0].y() == points[2].y() == points[4].y()
    assert_equal_data_geometry(grid, 5)


@pytest.mark.parametrize("count,columns,rows,occupied_columns", [
    (0, 3, 0, 0),
    (1, 8, 1, 1),
    (2, 8, 1, 2),
    (5, 3, 2, 3),
    (6, 3, 2, 3),
    (7, 3, 3, 3),
])
def test_only_occupied_boundaries_have_axes(grid_factory, count, columns, rows, occupied_columns):
    _, grid, axes = grid_factory(count, columns, colorbar=True)
    data_items = assert_equal_data_geometry(grid, count)
    y_scales = named_items(grid, "channel-grid-y-scale-")
    x_scales = named_items(grid, "channel-grid-x-scale-")
    assert len(y_scales) == rows
    assert len(x_scales) == occupied_columns
    for scale in y_scales:
        assert_qml_identity(scale, "scale_division === testAxes.vertical_axis.scale_division")
        assert scale.height() == pytest.approx(grid.property("dataHeight"))
        assert position(scale, grid).x() <= min(position(item, grid).x() for item in data_items)
    for column in range(occupied_columns):
        scale = named_item(grid, f"channel-grid-x-scale-{column}")
        assert_qml_identity(scale, "scale_division === testAxes.horizontal_axis.scale_division")
        assert scale.width() == pytest.approx(grid.property("dataWidth"))
        bottom_cell = next(
            cell for cell in named_items(grid, "channel-grid-cell-")
            if cell.property("column") == column and cell.property("rowFromBottom") == 0
        )
        data = named_item(grid, f"channel-grid-data-{bottom_cell.property('channelIndex')}")
        assert position(scale, grid).x() == pytest.approx(position(data, grid).x())
        assert position(scale, grid).y() >= position(data, grid).y() + data.height()
    color_scales = named_items(grid, "channel-grid-color-scale")
    assert len(color_scales) == (1 if count else 0)
    if color_scales:
        assert_qml_identity(color_scales[0], "scale_division === testAxes.color_axis.scale_division")


def test_plot_payload_and_all_axes_are_shared_without_per_channel_parameters(grid_factory):
    _, grid, axes = grid_factory(5, 3)
    assert named_items(grid, "channel-grid-color-scale") == []
    for index in range(5):
        content = named_item(grid, f"test-channel-content-{index}")
        assert content.property("presentedIndex") == index
        assert content.property("presentedLabel") == f"Channel {index + 1}"
        assert content.property("presentedPayload") == 100 + index
        data = named_item(grid, f"channel-grid-data-{index}")
        assert_qml_identity(data, "horizontal_axis === testAxes.horizontal_axis")
        assert_qml_identity(data, "vertical_axis === testAxes.vertical_axis")


def test_long_labels_and_live_readouts_preserve_equal_plot_geometry(grid_factory, qt_application):
    root, grid, axes = grid_factory(5, 3, colorbar=True)
    before = [(item.width(), item.height()) for item in assert_equal_data_geometry(grid, 5)]
    root.setProperty("channels", [
        {"label": "Very long physical channel label " * (index + 1), "value": 100 + index}
        for index in range(5)
    ])
    root.setProperty("readout", "-123456789.987654 dB " * 8)
    root.setProperty("preferredHeaderHeight", 200)
    settle(qt_application)
    assert [(item.width(), item.height()) for item in assert_equal_data_geometry(grid, 5)] == before

    axes.vertical_axis.setRange(-1000000, 1000000)
    axes.color_axis.setRange(-1000000, 1000000)
    settle(qt_application)
    assert_equal_data_geometry(grid, 5)
    root.setProperty("width", 701)
    root.setProperty("height", 431)
    settle(qt_application)
    assert_equal_data_geometry(grid, 5)


@pytest.mark.parametrize("size", [(1, 1), (0, 0), (25, 10)])
@pytest.mark.parametrize("count,columns", [(0, 4), (1, 4), (5, 3)])
def test_tiny_panels_keep_plot_and_axis_geometry_nonnegative(grid_factory, size, count, columns):
    _, grid, _ = grid_factory(count, columns, width=size[0], height=size[1], colorbar=True)
    assert grid.property("dataWidth") >= 0
    assert grid.property("dataHeight") >= 0
    assert_equal_data_geometry(grid, count)
    for prefix in ("channel-grid-cell-", "channel-grid-y-scale-", "channel-grid-x-scale-", "channel-grid-color-scale"):
        for item in named_items(grid, prefix):
            assert item.width() >= 0
            assert item.height() >= 0


def test_global_column_changes_reflow_an_existing_grid(grid_factory, qt_application):
    store = GetStore()
    previous = store.channel_grid_columns
    try:
        store.channel_grid_columns = 2
        _, grid, _ = grid_factory(5)
        assert (grid.property("columnCount"), grid.property("rowCount")) == (2, 3)
        store.channel_grid_columns = 3
        settle(qt_application)
        assert (grid.property("columnCount"), grid.property("rowCount")) == (3, 2)
        assert_equal_data_geometry(grid, 5)
        last = named_item(grid, "channel-grid-cell-4")
        assert (last.property("column"), last.property("rowFromBottom")) == (2, 0)
    finally:
        store.channel_grid_columns = previous


def test_live_channel_replacement_addition_removal_and_empty_grid(grid_factory, qt_application):
    root, grid, _ = grid_factory(5, 3, colorbar=True)
    for count in (2, 7, 0, 3):
        labels = [f"Replacement channel {index + 1}" for index in range(count)]
        root.setProperty("channels", [
            {"label": label, "value": 200 + index}
            for index, label in enumerate(labels)
        ])
        settle(qt_application)
        assert len(named_items(grid, "channel-grid-cell-")) == count
        assert_equal_data_geometry(grid, count)
        assert len(named_items(grid, "channel-grid-x-scale-")) == min(count, 3)
        assert len(named_items(grid, "channel-grid-color-scale")) == (1 if count else 0)
        for index, label in enumerate(labels):
            content = named_item(grid, f"test-channel-content-{index}")
            assert content.property("presentedLabel") == label
            assert content.property("presentedPayload") == 200 + index
    assert not grid_factory.qml_warnings, "\n".join(
        warning.toString() for warning in grid_factory.qml_warnings
    )


def test_shared_colorbar_can_render_with_fractional_font_and_header_geometry(grid_factory, qt_application):
    _, grid, _ = grid_factory(5, 3, colorbar=True)
    grid.setProperty("headerHeight", 22.5)
    settle(qt_application)
    color_scale = named_item(grid, "channel-grid-color-scale")
    bars = [item for item in color_scale.childItems() if isinstance(item, ColorBar)]
    assert len(bars) == 1
    # Invoke the real renderer, since floating-point item geometry can otherwise
    # pass QML layout tests but fail during its NumPy vertex allocation.
    node = bars[0].updatePaintNode(None, None)
    assert node is not None
    assert node.geometry().vertexCount() > 0
    sip.delete(node)


def test_destroying_a_qml_consumer_preserves_the_process_store(qt_application, monkeypatch):
    # Give this engine its own instance: Qt singleton wrappers belong to the
    # engine that first consumes them, whereas the ownership rule is process-wide.
    monkeypatch.setattr(store_module, "__storeInstance", None)
    store = GetStore()
    module = "PolyfritureStoreOwnershipTest"
    qmlRegisterSingletonType(
        Store, module, 1, 0, lambda engine, script_engine: GetStore(), "Store",
    )
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    root = None
    try:
        component.setData(
            f'''import QtQml 2.15
import {module} 1.0
QtObject {{ property int columns: Store.channel_grid_columns }}'''.encode(),
            QUrl(),
        )
        assert component.status() == QQmlComponent.Status.Ready
        root = component.create()
        assert root is not None
        assert root.property("columns") == store.channel_grid_columns
        sip.delete(root)
        sip.delete(engine)
        assert not sip.isdeleted(store)
        assert GetStore() is store
    finally:
        if root is not None and not sip.isdeleted(root):
            sip.delete(root)
        if not sip.isdeleted(engine):
            sip.delete(engine)
        if not sip.isdeleted(store):
            sip.delete(store)
