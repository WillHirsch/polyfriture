"""FFT channel isolation, shared settings and the real grid delegates."""

from pathlib import Path

import numpy as np
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QUrl
from PyQt6.QtQuick import QQuickView

# Register typed Qt properties before DSP tests first expose their metatypes.
from polyfriture.test.test_qml_integration import _register_qml_types
from PyQt6.QtWidgets import QWidget

from polyfriture.audiobackend import SAMPLING_RATE
from polyfriture.audiobuffer import AudioBuffer
from polyfriture.channel_configuration import ChannelConfiguration
from polyfriture.spectrum import Spectrum_Widget
from polyfriture.spectrum_settings import Spectrum_Settings_Dialog
from polyfriture.plotting import frequency_scales as scales


@pytest.fixture
def panels(qt_application):
    parent = QWidget()
    created = []

    def create(ids):
        buffer = AudioBuffer()
        buffer.handle_configuration_changed(ChannelConfiguration(0, ids, 64, 1))
        panel = Spectrum_Widget(parent)
        panel.setfftsize(1024)
        panel.set_buffer(buffer)
        buffer.configuration_changed.connect(panel.reset_channel_state)
        buffer.new_data_available.connect(panel.handle_new_data)
        created.append(panel)
        return panel, buffer

    yield create
    parent.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def push(buffer, samples):
    buffer.handle_new_data(samples, 1., None, buffer.channel_configuration.generation)


@pytest.mark.parametrize("weighting", [0, 1, 2, 3])
def test_every_channel_matches_its_mono_reference_across_transients(panels, weighting):
    panel, buffer = panels((1, 4, 8))
    mono = [panels((channel_id,)) for channel_id in panel._channels]
    for current in [panel, *(reference for reference, _ in mono)]:
        current.setweighting(weighting)
    t = np.arange(4096) / SAMPLING_RATE
    samples = np.vstack([np.sin(2 * np.pi * frequency * t) * gain
                         for frequency, gain in ((750, 0.8), (3000, 0.03), (6000, 0.2))])
    for block in (samples, np.zeros_like(samples), samples[::-1] * 0.5):
        push(buffer, block)
        for row, ((reference, reference_buffer), state) in enumerate(zip(mono, panel._channels.values())):
            push(reference_buffer, block[row:row + 1])
            expected = next(iter(reference._channels.values()))
            np.testing.assert_allclose(state.dispbuffer, expected.dispbuffer)
            np.testing.assert_allclose(state.plot.peak, expected.plot.peak)
            np.testing.assert_allclose(state.plot.peak_int, expected.plot.peak_int)
            np.testing.assert_allclose(state.plot._curve_signal.y_array(), expected.plot._curve_signal.y_array())
            assert state.plot.view_model().fmaxValue == expected.plot.view_model().fmaxValue
            assert state.plot.view_model().fpitchDisplayText == expected.plot.view_model().fpitchDisplayText
    assert len({id(state.dispbuffer) for state in panel._channels.values()}) == 3
    assert len({id(state.plot.peak) for state in panel._channels.values()}) == 3


def test_single_settings_controller_broadcasts_to_existing_and_future_channels(panels):
    panel, buffer = panels((1, 4, 8))
    assert len(panel.parent().findChildren(Spectrum_Settings_Dialog)) == 1
    panel.setfreqscale(scales.Logarithmic)
    panel.setminfreq(80)
    panel.setmaxfreq(12000)
    panel.setmin(-130)
    panel.setmax(-5)
    panel.setweighting(3)
    panel.setresponsetime(1.)
    panel.setShowFreqLabel(False)
    panel.setShowPitchLabel(False)
    panel.setfftsize(2048)
    for state in panel._channels.values():
        model = state.plot.view_model()
        assert model.horizontal_axis is panel.view_model().horizontal_axis
        assert model.vertical_axis is panel.view_model().vertical_axis
        assert model.horizontal_axis.coordinate_transform.scale is scales.Logarithmic
        assert model.horizontal_axis.coordinate_transform.coord_min == 80
        assert model.vertical_axis.coordinate_transform.coord_max == -5
        assert model.vertical_axis.name == "PSD (dB C)"
        assert not model.showFrequencyTracker and not model.showPitchTracker
        assert state.dispbuffer.size == 1025
    panel.pause()
    previous = list(panel._channels.values())
    buffer.handle_configuration_changed(ChannelConfiguration(0, (4, 11), 64, 2))
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert all(sip.isdeleted(state) for state in previous)
    assert tuple(panel._channels) == (4, 11)
    assert [view.label for view in panel.view_model().channels] == ["Channel 5", "Channel 12"]
    for state in panel._channels.values():
        assert state.plot.paused and not state.plot.peak.size
        assert not state.plot.view_model().showFrequencyTracker
        assert state.dispbuffer.size == 1025
    panel.restart()
    assert all(not state.plot.paused for state in panel._channels.values())


def test_live_qml_grid_has_equal_cells_shared_axes_and_channel_readouts(panels, qt_application):
    from polyfriture.test.test_channel_grid import named_items, assert_qml_identity
    _register_qml_types()
    panel, buffer = panels((0, 2, 5, 8, 11))
    samples = np.ones((5, 4096))
    push(buffer, samples)
    view = QQuickView()
    # The process Store is already exercised by the shared-grid suite. Supply
    # the column count before creation to keep this independent QML engine local.
    view.setInitialProperties({"configuredColumns": 3})
    warnings = []
    view.engine().warnings.connect(warnings.extend)
    view.engine().rootContext().setContextProperty("viewModel", panel.view_model())
    try:
        view.setSource(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / "Spectrum.qml")))
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
        for cell in cells:
            assert_qml_identity(cell, "horizontal_axis === viewModel.horizontal_axis")
            assert_qml_identity(cell, "vertical_axis === viewModel.vertical_axis")
        assert len(named_items(root, "channel-grid-x-scale-")) == 3
        assert len(named_items(root, "channel-grid-y-scale-")) == 2
        assert len(named_items(root, "channel-grid-color-scale")) == 0
        first = panel._channels[0].plot.view_model()
        first.setFmax("999999999999999 Hz", 0.5)
        first.setFpitch("A very long derived annotation", 0.5)
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
            panel = Spectrum_Widget(parent)
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
