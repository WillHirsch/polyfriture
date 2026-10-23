"""Octave channel filter/smoothing isolation and actual channel-grid QML."""

from pathlib import Path

import numpy as np
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QUrl
from PyQt6.QtQuick import QQuickView

# Register typed Qt properties before DSP tests first expose their metatypes.
from polyfriture.test.test_qml_integration import _register_qml_types
from PyQt6.QtWidgets import QWidget

from polyfriture.audiobuffer import AudioBuffer
from polyfriture.channel_configuration import ChannelConfiguration
from polyfriture.octavespectrum import OctaveSpectrum_Widget
from polyfriture.octavespectrum_settings import OctaveSpectrum_Settings_Dialog


@pytest.fixture
def panels(qt_application):
    parent = QWidget()

    def create(ids):
        buffer = AudioBuffer()
        buffer.handle_configuration_changed(ChannelConfiguration(0, ids, 64, 1))
        panel = OctaveSpectrum_Widget(parent)
        panel.set_buffer(buffer)
        buffer.configuration_changed.connect(panel.reset_channel_state)
        return panel, buffer

    yield create
    parent.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("bands", [1, 3, 6, 12, 24])
def test_impulse_and_step_outputs_match_independent_mono_references(panels, bands):
    panel, _ = panels((1, 4, 8))
    mono = [panels((channel_id,))[0] for channel_id in panel._channels]
    for current in [panel, *mono]:
        current.setbandsperoctave(bands)
    impulse = np.zeros((3, 2048))
    impulse[0, 0] = 1.
    step = np.zeros_like(impulse)
    step[1] = 0.2
    for block in (impulse, np.zeros_like(impulse), step, np.zeros_like(impulse)):
        panel.handle_new_data(block)
        for row, (reference, state) in enumerate(zip(mono, panel._channels.values())):
            reference.handle_new_data(block[row:row + 1])
            expected = next(iter(reference._channels.values()))
            np.testing.assert_allclose(state.dispbuffers, expected.dispbuffers)
            np.testing.assert_allclose(state.plot.peak, expected.plot.peak)
            np.testing.assert_allclose(state.plot._curve_signal.y_array(), expected.plot._curve_signal.y_array())
            for overlap, expected_overlap in zip(state.filters._overlaps_oct, expected.filters._overlaps_oct):
                np.testing.assert_allclose(overlap, expected_overlap)
        silent = panel._channels[8]
        assert not np.any(silent.dispbuffers)
        assert all(not np.any(tail) for tail in silent.filters._overlaps_oct + silent.filters._overlaps_dec)
    states = list(panel._channels.values())
    assert len({id(state.filters) for state in states}) == 3
    assert len({id(state.plot.peak) for state in states}) == 3


def test_shared_settings_reset_every_filter_and_apply_to_future_channels(panels):
    panel, buffer = panels((1, 4, 8))
    assert len(panel.parent().findChildren(OctaveSpectrum_Settings_Dialog)) == 1
    panel.handle_new_data(np.ones((3, 2048)))
    panel.setmin(-130)
    panel.setmax(-5)
    panel.setweighting(2)
    panel.setresponsetime(1.)
    panel.setbandsperoctave(12)
    for state in panel._channels.values():
        model = state.plot.view_model()
        assert model.horizontal_axis is panel.view_model().horizontal_axis
        assert model.vertical_axis is panel.view_model().vertical_axis
        assert model.vertical_axis.name == "PSD (dB B)"
        assert model.vertical_axis.coordinate_transform.coord_min == -130
        assert model.vertical_axis.coordinate_transform.coord_max == -5
        assert state.filters.bandsperoctave == 12
        assert not np.any(state.dispbuffers)
        assert not state.plot.peak.size
        assert not model._bar_labels
    panel.pause()
    previous = list(panel._channels.values())
    buffer.handle_configuration_changed(ChannelConfiguration(0, (4, 11), 64, 2))
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert all(sip.isdeleted(state) for state in previous)
    assert tuple(panel._channels) == (4, 11)
    assert [model.label for model in panel.view_model().channels] == ["Channel 5", "Channel 12"]
    assert all(state.plot.paused and state.filters.bandsperoctave == 12 for state in panel._channels.values())
    panel.restart()
    assert all(not state.plot.paused for state in panel._channels.values())


def test_real_qml_grid_shares_axes_and_preserves_geometry_with_band_labels(panels, qt_application):
    from polyfriture.test.test_channel_grid import named_items, assert_qml_identity
    _register_qml_types()
    panel, buffer = panels((0, 2, 5, 8, 11))
    panel.handle_new_data(np.ones((5, 2048)))
    view = QQuickView()
    # The process Store is already exercised by the shared-grid suite. Supply
    # the column count before creation to keep this independent QML engine local.
    view.setInitialProperties({"configuredColumns": 3})
    warnings = []
    view.engine().warnings.connect(warnings.extend)
    view.engine().rootContext().setContextProperty("viewModel", panel.view_model())
    try:
        view.setSource(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / "HistPlot.qml")))
        assert view.status() == QQuickView.Status.Ready, [error.toString() for error in view.errors()]
        view.resize(720, 480)
        view.show()
        qt_application.processEvents()
        root = view.rootObject()
        root.setProperty("configuredColumns", 3)
        qt_application.processEvents()
        cells = named_items(root, "channel-grid-data-")
        assert len(cells) == 5
        assert len({(cell.width(), cell.height()) for cell in cells}) == 1
        assert len(named_items(root, "channel-grid-x-scale-")) == 3
        assert len(named_items(root, "channel-grid-y-scale-")) == 2
        for cell in cells:
            assert_qml_identity(cell, "horizontal_axis === viewModel.horizontal_axis")
            assert_qml_identity(cell, "vertical_axis === viewModel.vertical_axis")
        assert not named_items(root, "channel-grid-color-scale")
        panel.setbandsperoctave(24)
        panel.handle_new_data(np.ones((5, 2048)))
        qt_application.processEvents()
        assert len({(cell.width(), cell.height()) for cell in cells}) == 1
        buffer.handle_configuration_changed(ChannelConfiguration(0, (6, 9), 64, 2))
        qt_application.processEvents()
        assert len(named_items(root, "channel-grid-data-")) == 2
        assert not warnings, "\n".join(warning.toString() for warning in warnings)
    finally:
        view.setSource(QUrl())
        view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_repeated_creation_cleanup_disposes_models_curves_and_dialog(qt_application):
    parent = QWidget()
    buffer = AudioBuffer()
    buffer.handle_configuration_changed(ChannelConfiguration(0, (1, 4, 8), 64, 1))
    try:
        for _ in range(4):
            panel = OctaveSpectrum_Widget(parent)
            panel.set_buffer(buffer)
            owned = [panel.view_model(), panel.settings_dialog]
            for state in panel._channels.values():
                owned.extend([state, state.plot, state.plot.view_model(),
                              state.plot._curve_signal, state.plot._curve_peak])
            panel.cleanup()
            panel.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert all(sip.isdeleted(obj) for obj in owned)
    finally:
        parent.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
