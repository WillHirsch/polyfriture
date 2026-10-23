"""Channel identity, triggering, QML overflow and scope teardown without audio I/O."""

from types import SimpleNamespace

import numpy as np
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QUrl
from PyQt6.QtQml import QQmlComponent, QQmlEngine
from PyQt6.QtQuick import QQuickView
from PyQt6.QtWidgets import QWidget

from polyfriture.audiobackend import SAMPLING_RATE
from polyfriture.audiobuffer import AudioBuffer
from polyfriture.channel_configuration import ChannelConfiguration
from polyfriture.curve import Curve
from polyfriture.dock import Dock
from polyfriture.longlevels import LongLevelWidget
from polyfriture.plotCurve import PlotCurve
from polyfriture.qml_tools import qml_url
from polyfriture.scope import Scope_Widget
from polyfriture.spectrogram import Spectrogram_Widget


def flush_deletions():
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def plot_curves(item):
    # Repeater delegates have visual parents without corresponding QObject
    # parents, so QObject.findChildren() does not find the rendered traces.
    curves = []
    for child in item.childItems():
        if isinstance(child, PlotCurve):
            curves.append(child)
        curves.extend(plot_curves(child))
    return curves


@pytest.fixture
def scope(qt_application):
    parent = QWidget()
    panel = Scope_Widget(parent)
    buffer = AudioBuffer()
    panel.set_buffer(buffer)
    buffer.configuration_changed.connect(panel.reset_channel_state)
    buffer.new_data_available.connect(panel.handle_new_data)
    yield panel, buffer
    Dock.disconnect_audio_widget(SimpleNamespace(audiobuffer=buffer, audiowidget=panel))
    panel.cleanup()
    parent.deleteLater()
    flush_deletions()


def configure(buffer, channel_ids, generation=1):
    configuration = ChannelConfiguration(7, channel_ids, max(channel_ids) + 1, generation)
    buffer.handle_configuration_changed(configuration)
    return configuration


@pytest.mark.parametrize("channel_count", [1, 2, 3, 8, 17])
def test_scrolling_scope_shows_every_selected_row_with_shared_time(scope, channel_count):
    panel, buffer = scope
    configuration = configure(buffer, tuple(range(1, 2 * channel_count + 1, 2)))
    panel.set_timerange(600.)
    width = int(panel.timerange * 1e-3 * SAMPLING_RATE)
    samples = np.linspace(-0.9, 0.9, channel_count)[:, None] * np.ones((1, width))

    buffer.handle_new_data(samples, 1., None, configuration.generation)

    curves = list(panel.view_model().plot_items)
    assert len(curves) == channel_count
    assert tuple(curve.name for curve in curves) == configuration.channel_labels
    assert tuple(panel._curves) == configuration.channel_ids
    assert len({curve.color for curve in curves}) == channel_count
    assert all(curve.x_array() is curves[0].x_array() for curve in curves)
    assert curves[0].x_array().size == width
    assert curves[0].x_array()[0] == pytest.approx(0.)
    assert curves[0].x_array()[-1] == pytest.approx(1. - 1. / width)
    for row, curve in enumerate(curves):
        np.testing.assert_allclose(curve.y_array(), (1. - samples[row]) / 2.)


def test_trigger_uses_first_physical_channel_and_one_window_for_every_trace(scope):
    panel, buffer = scope
    configuration = configure(buffer, (1, 4, 8))
    panel.set_timerange(2.5)  # 120 displayed samples, 240 searched samples.
    samples = np.full((3, 240), -1.)
    samples[0, 120:] = 1.
    samples[1, 140:] = 1.
    samples[2, 160:] = 1.

    buffer.handle_new_data(samples, 1., None, configuration.generation)

    # The first rising edge's left sample is 119; it appears at the center.
    np.testing.assert_array_equal(panel.samples, samples[:, 59:179])
    for curve, row in zip(panel._curves.values(), samples):
        np.testing.assert_array_equal(curve.y_array(), (1. - row[59:179]) / 2.)

    # Removing the first selected channel changes the trigger to Channel 5.
    configuration = configure(buffer, (4, 8), generation=2)
    assert all(curve.y_array().size == 0 for curve in panel._curves.values())
    buffer.handle_new_data(samples[1:], 2., None, configuration.generation)

    np.testing.assert_array_equal(panel.samples, samples[1:, 79:199])
    assert tuple(curve.name for curve in panel._curves.values()) == ("Channel 5", "Channel 9")


def test_odd_sample_window_keeps_all_traces_equal_length(scope):
    panel, buffer = scope
    configuration = configure(buffer, (0, 2, 5))
    panel.set_timerange(2.7)  # A supported setting produces 129 displayed samples.
    samples = np.full((3, 258), -1.)
    samples[:, 129:] = 1.

    buffer.handle_new_data(samples, 1., None, configuration.generation)

    assert panel.samples.shape == (3, 129)
    assert all(curve.x_array().size == curve.y_array().size == 129 for curve in panel._curves.values())


def test_selection_changes_keep_identity_color_and_dispose_removed_curves(scope):
    panel, buffer = scope
    configure(buffer, (1, 4, 8))
    original = panel._curves.copy()
    colors = {channel_id: curve.color for channel_id, curve in original.items()}

    configure(buffer, (4, 8, 11), generation=2)
    flush_deletions()

    assert sip.isdeleted(original[1])
    assert panel._curves[4] is original[4]
    assert panel._curves[8] is original[8]
    assert panel._curves[4].color == colors[4]
    assert panel._curves[8].color == colors[8]
    assert len(panel.view_model().findChildren(Curve)) == 3

    configure(buffer, (1, 4), generation=3)
    flush_deletions()

    assert panel._curves[1].color == colors[1]
    assert panel._curves[4].color == colors[4]
    assert len(panel.view_model().findChildren(Curve)) == 2
    panel.reset_channel_state(None)
    flush_deletions()
    assert not list(panel.view_model().plot_items)
    assert not panel.view_model().findChildren(Curve)
    assert panel.samples.shape == (0, 0)


def test_repeated_creation_and_close_removes_curves_dialog_and_subscriptions(qt_application):
    parent = QWidget()
    buffer = AudioBuffer()
    configure(buffer, (0, 3, 7))
    try:
        for _ in range(5):
            panel = Scope_Widget(parent)
            panel.set_buffer(buffer)
            buffer.configuration_changed.connect(panel.reset_channel_state)
            buffer.new_data_available.connect(panel.handle_new_data)
            owned = [panel.view_model(), panel.settings_dialog, *panel._curves.values()]
            dock = SimpleNamespace(audiobuffer=buffer, audiowidget=panel)

            Dock.disconnect_audio_widget(dock)
            panel.cleanup()
            panel.deleteLater()
            flush_deletions()

            assert all(sip.isdeleted(obj) for obj in owned)
            assert buffer.receivers(buffer.configuration_changed) == 0
            assert buffer.receivers(buffer.new_data_available) == 0
        buffer.new_data_available.emit(np.zeros((3, 32)))
    finally:
        parent.deleteLater()
        flush_deletions()


@pytest.fixture
def qml_types():
    # Share the suite's registration guard; Qt limits registered Python types.
    from polyfriture.test.test_qml_integration import _register_qml_types
    _register_qml_types()


def test_qml_legend_scrolls_without_squeezing_plot_and_replaces_all_traces(scope, qml_types, qt_application):
    panel, buffer = scope
    configure(buffer, tuple(range(32)))
    view = QQuickView()
    view.engine().rootContext().setContextProperty("viewModel", panel.view_model())
    try:
        view.setSource(qml_url("Scope.qml"))
        assert view.status() == QQuickView.Status.Ready, [error.toString() for error in view.errors()]
        view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
        view.resize(480, 240)
        view.show()
        qt_application.processEvents()
        root = view.rootObject()
        plot_area = root.findChild(QObject, "plotArea")
        legend = root.findChild(QObject, "legend")
        viewport = legend.findChild(QObject, "legendViewport")
        assert len(plot_curves(root)) == 32
        assert 0. < legend.width() <= 0.3 * root.width()
        assert plot_area.width() > root.width() / 2.
        assert viewport.property("contentHeight") > viewport.height()
        assert viewport.property("clip")

        old_curves = list(panel._curves.values())
        configure(buffer, (33, 36, 40), generation=2)
        qt_application.processEvents()
        flush_deletions()

        rendered = plot_curves(root)
        assert len(rendered) == 3
        assert all(sip.isdeleted(curve) for curve in old_curves)
        assert {item.curve.name for item in rendered} == {"Channel 34", "Channel 37", "Channel 41"}
        assert {item.color.name() for item in rendered} == {curve.color for curve in panel._curves.values()}
    finally:
        view.setSource(QUrl())
        view.deleteLater()
        flush_deletions()


@pytest.mark.parametrize("panel_type", [LongLevelWidget, Spectrogram_Widget])
def test_shared_plot_qml_still_accepts_history_and_spectrogram_models(panel_type, qml_types, qt_application):
    parent = QWidget()
    panel = panel_type(parent)
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("viewModel", panel.view_model())
    component = QQmlComponent(engine, qml_url(panel.qml_file_name()))
    try:
        assert component.status() == QQmlComponent.Status.Ready, [error.toString() for error in component.errors()]
        root = component.create()
        assert root is not None, [error.toString() for error in component.errors()]
        assert panel.view_model().horizontal_axis is not None
        if panel_type is LongLevelWidget:
            rendered = plot_curves(root)
            assert len(rendered) == 1
            assert rendered[0].color.name() == "#ff0000"
        else:
            assert panel.view_model().show_color_axis
        root.deleteLater()
    finally:
        engine.deleteLater()
        parent.deleteLater()
        flush_deletions()
