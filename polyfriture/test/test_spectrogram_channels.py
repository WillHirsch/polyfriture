"""Synchronized spectrogram histories with synthetic audio and real QML cells."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QUrl
from PyQt6.QtQml import QQmlComponent, QQmlEngine, qmlRegisterSingletonType, qmlRegisterType, qmlTypeId
from PyQt6.QtWidgets import QWidget

from polyfriture.application import QML_MODULE
from polyfriture.audiobackend import SAMPLING_RATE
from polyfriture.audiobuffer import AudioBuffer
from polyfriture.axis import Axis
from polyfriture.channel_configuration import ChannelConfiguration
from polyfriture.colorBar import ColorBar
from polyfriture.plotting.coordinateTransform import CoordinateTransform
from polyfriture.plotting.scaleDivision import ScaleDivision, Tick
from polyfriture.scope_data import Scope_Data
from polyfriture.spectrogram import Spectrogram_Widget
from polyfriture.spectrogram_image import CanvasScaledSpectrogram
from polyfriture.spectrogram_item import SpectrogramItem
from polyfriture.store import GetStore, Store
from polyfriture.test.test_channel_grid import assert_equal_data_geometry, named_items, settle
import polyfriture.plotting.frequency_scales as fscales


def register_qml_types():
    # Register before constructing axes: Qt caches Python property metadata
    # when the first instances are created, including typed transform fields.
    for name, qml_type in (("ScaleDivision", ScaleDivision), ("CoordinateTransform", CoordinateTransform),
                           ("Axis", Axis), ("ColorBar", ColorBar), ("Tick", Tick),
                           ("ScopeData", Scope_Data), ("SpectrogramItem", SpectrogramItem)):
        if qmlTypeId(QML_MODULE, 1, 0, name) < 0:
            qmlRegisterType(qml_type, QML_MODULE, 1, 0, name)
    if qmlTypeId(QML_MODULE, 1, 0, "Store") < 0:
        qmlRegisterSingletonType(Store, QML_MODULE, 1, 0, lambda engine, script: GetStore(), "Store")


@pytest.fixture
def panel_factory(qt_application, monkeypatch):
    register_qml_types()
    def no_backend():
        raise AssertionError("Synthetic spectrogram tests must not open an audio device")

    monkeypatch.setattr("polyfriture.spectrogram.AudioBackend", no_backend)
    parents = []

    def create(ids=(0, 2, 4)):
        parent = QWidget()
        parents.append(parent)
        panel = Spectrogram_Widget(parent)
        buffer = AudioBuffer()
        configuration = ChannelConfiguration(0, ids, max(ids) + 1, 1)
        buffer.handle_configuration_changed(configuration)
        panel.set_buffer(buffer)
        buffer.configuration_changed.connect(panel.reset_channel_state)
        panel.setfftsize(256)
        panel.timerangechanged(0.2)
        for channel in panel._channels.values():
            channel.image.update_screen_size(120, 64)
        return panel, buffer

    yield create
    for parent in parents:
        sip.delete(parent)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def push(panel, buffer, samples):
    buffer.ringbuffer.push(samples, buffer.ringbuffer.offset / SAMPLING_RATE + samples.shape[1] / SAMPLING_RATE)
    panel.handle_new_data(samples)


def pixels(image):
    raster = image.pixmap().toImage()
    return np.array([[raster.pixel(x, y) for x in range(raster.width())] for y in range(raster.height())])


def asymmetric_signals(length, start=0):
    time = np.arange(start, start + length) / SAMPLING_RATE
    return np.array([
        0.7 * np.sin(2 * np.pi * 500 * time),
        0.08 * np.sin(2 * np.pi * 2400 * time),
        0.3 * np.sin(2 * np.pi * 6500 * time),
    ])


def test_asymmetric_channels_match_independent_mono_references(panel_factory):
    panel, buffer = panel_factory()
    mono = [panel_factory((channel_id,)) for channel_id in panel._channels]
    for start, count in ((0, 1536), (1536, 4096), (5632, 1024)):
        signals = asymmetric_signals(count, start)
        push(panel, buffer, signals)
        for row, (reference, reference_buffer) in enumerate(mono):
            push(reference, reference_buffer, signals[row:row + 1])

    channels = list(panel._channels.values())
    for channel, (reference, _) in zip(channels, mono):
        expected = next(iter(reference._channels.values()))
        np.testing.assert_array_equal(pixels(channel.image), pixels(expected.image))
        np.testing.assert_allclose(channel.screen_resampler.old_data, expected.screen_resampler.old_data)
        assert channel.image.last_data_time == expected.image.last_data_time
    for channel, frequency in zip(channels, (500, 2400, 6500)):
        peak = np.argmax(channel.screen_resampler.old_data)
        assert channel.frequency_resampler.xscaled[peak] == pytest.approx(frequency, abs=500)
    # Check the final column against the original mono FFT/normalization
    # calculation as well, rather than only comparing controller instances.
    samples = buffer.data_indexed(panel.old_index - panel.fft_size // 4, panel.fft_size)
    for channel, row in zip(channels, samples):
        window = 0.5 * (1 - np.cos(2 * np.pi * np.arange(panel.fft_size) / (panel.fft_size - 1)))
        power = np.abs(np.fft.rfft(row * window)) ** 2 / panel.fft_size ** 2
        normalized = (10 * np.log10(power + 1e-30) + 140) / 140
        expected = np.interp(channel.frequency_resampler.xscaled, panel.freq, normalized)
        np.testing.assert_allclose(channel.screen_resampler.old_data, expected)
    assert len({channel.image.last_data_time for channel in channels}) == 1
    assert len({channel.screen_resampler.orig_index for channel in channels}) == 1
    assert len({channel.image.canvasscaledspectrogram.write_offset for channel in channels}) == 1
    assert all(not np.array_equal(pixels(channels[0].image), pixels(channel.image)) for channel in channels[1:])
    for attribute in ("image", "frequency_resampler", "screen_resampler", "audio_pipeline"):
        assert len({id(getattr(channel, attribute)) for channel in channels}) == 3


def test_shared_display_clock_pause_and_deferred_restart(panel_factory, monkeypatch):
    panel, buffer = panel_factory()
    push(panel, buffer, asymmetric_signals(2048))
    calls = []
    monkeypatch.setattr("polyfriture.spectrogram.AudioBackend", lambda: SimpleNamespace(
        get_stream_time=lambda: calls.append(True) or 4.))
    panel.canvasUpdate()
    assert len(calls) == 1
    assert {channel.image.paint_time for channel in panel._channels.values()} == {4.}
    panel.pause()
    panel.canvasUpdate()
    panel.restart()
    panel.canvasUpdate()
    assert len(calls) == 1
    assert all(not channel.image.is_playing for channel in panel._channels.values())
    push(panel, buffer, asymmetric_signals(1024, 2048))
    assert all(channel.image.is_playing for channel in panel._channels.values())
    assert not panel.mustRestart
    panel.canvasUpdate()
    assert len(calls) == 2


def test_max_frequency_change_with_weighting_matches_mono_after_new_audio(panel_factory):
    panel, buffer = panel_factory()
    references = [panel_factory((channel_id,)) for channel_id in panel._channels]
    for view, source in [(panel, buffer), *references]:
        view.setweighting(1)
    initial = asymmetric_signals(2048)
    push(panel, buffer, initial)
    for row, (reference, source) in enumerate(references):
        push(reference, source, initial[row:row + 1])
    for view, _ in [(panel, buffer), *references]:
        view.setmaxfreq(8000)
        assert len(view.freq) == view.fft_size // 2 + 1 == len(view.w)
        for channel in view._channels.values():
            assert channel.frequency_resampler.freq is view.freq
    following = asymmetric_signals(1024, 2048)
    push(panel, buffer, following)
    for row, ((reference, source), channel) in enumerate(zip(references, panel._channels.values())):
        push(reference, source, following[row:row + 1])
        expected = next(iter(reference._channels.values()))
        np.testing.assert_allclose(channel.screen_resampler.old_data, expected.screen_resampler.old_data)
        np.testing.assert_array_equal(pixels(channel.image), pixels(expected.image))
        assert channel.image.last_data_time == expected.image.last_data_time


@pytest.mark.parametrize("change", [
    lambda panel: panel.setfftsize(512),
    lambda panel: panel.setminfreq(200),
    lambda panel: panel.setmaxfreq(10000),
    lambda panel: panel.setfreqscale(fscales.Logarithmic),
    lambda panel: panel.setweighting(1),
    lambda panel: panel.setmin(-90),
    lambda panel: panel.setmax(-10),
    lambda panel: panel.timerangechanged(0.3),
])
def test_parameter_changes_clear_all_rasters_and_resampling_together(panel_factory, change):
    panel, buffer = panel_factory()
    push(panel, buffer, asymmetric_signals(2048))
    assert all(channel.image.canvasscaledspectrogram.write_offset for channel in panel._channels.values())
    panel.pause()
    change(panel)
    assert panel.old_index == buffer.ringbuffer.offset
    for channel in panel._channels.values():
        assert channel.screen_resampler.orig_index == channel.screen_resampler.resampled_index == 0
        assert channel.image.canvasscaledspectrogram.write_offset == 0
        assert channel.image.last_data_time == 0
        assert not channel.image.is_playing
        assert channel.image.T == panel.timerange_s
        assert channel.frequency_resampler.scale is panel.freqscale
        assert channel.frequency_resampler.minfreq == panel.minfreq
        assert channel.frequency_resampler.maxfreq == panel.maxfreq
        np.testing.assert_array_equal(channel.frequency_resampler.freq, panel.freq)
        assert channel.image.pixmap().toImage().pixelColor(0, 0).name() == "#000000"
    # No channel-private settings dialogs/models were introduced.
    assert len(panel.parent().findChildren(type(panel.settings_dialog))) == 1


def test_resize_preserves_history_and_remains_equal_to_resized_mono(panel_factory):
    panel, buffer = panel_factory()
    mono, mono_buffer = panel_factory((2,))
    signals = asymmetric_signals(2048)
    push(panel, buffer, signals)
    push(mono, mono_buffer, signals[1:2])
    previous_time = next(iter(panel._channels.values())).image.last_data_time
    for channel in [*panel._channels.values(), *mono._channels.values()]:
        channel.image.update_screen_size(71, 43)
        assert channel.image.last_data_time == previous_time
        assert np.any(pixels(channel.image) != 0xFF000000)
    signals = asymmetric_signals(1024, 2048)
    push(panel, buffer, signals)
    push(mono, mono_buffer, signals[1:2])
    np.testing.assert_array_equal(pixels(panel._channels[2].image), pixels(mono._channels[2].image))


def test_narrow_raster_retains_newest_columns_when_a_block_exceeds_history(qt_application):
    canvas = CanvasScaledSpectrogram(canvas_width=3, canvas_height=1)
    canvas.addData(np.array([[0xFF000001, 0xFF000002, 0xFF000003, 0xFF000004, 0xFF000005]], dtype=np.uint32), 4.)
    assert canvas.write_offset == 5
    assert canvas.last_write_time == 4.
    raster = canvas.getpixmap().toImage()
    # The retained logical history is 3, 4, 5, repeated contiguously across wrap.
    offset = int(canvas.write_offset % 3)
    assert [raster.pixel(offset + x, 0) for x in range(3)] == [0xFF000003, 0xFF000004, 0xFF000005]


def test_repeated_panel_cleanup_disposes_owned_models_images_and_external_dialog(qt_application):
    host = QWidget()
    try:
        for _ in range(3):
            panel = Spectrogram_Widget(host)
            buffer = AudioBuffer()
            buffer.handle_configuration_changed(ChannelConfiguration(0, (0, 1, 3), 4, 1))
            panel.set_buffer(buffer)
            model = panel.view_model()
            views = list(model._channels)
            images = [channel.image for channel in panel._channels.values()]
            dialog = panel.settings_dialog
            panel.cleanup()
            assert model._channels == []
            assert panel._channels == {}
            assert panel.audiobuffer is None
            panel.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert all(sip.isdeleted(obj) for obj in [panel, model, dialog, *views, *images])
            assert host.findChildren(Spectrogram_Widget) == []
    finally:
        sip.delete(host)


def test_real_spectrogram_qml_uses_shared_grid_and_releases_old_channels(panel_factory, qt_application):
    panel, buffer = panel_factory((0, 2, 4, 6, 8))
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(warnings.extend)
    engine.rootContext().setContextProperty("viewModel", panel.view_model())
    package = QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1])).toString()
    component = QQmlComponent(engine)
    component.setData(f'''import QtQuick 2.15
import "{package}"
Item {{ width: 960; height: 640; ImagePlot {{ configuredColumns: 3 }} }}'''.encode(), QUrl())
    assert component.status() == QQmlComponent.Status.Ready, [error.toString() for error in component.errors()]
    root = component.create()
    assert root is not None
    try:
        settle(qt_application)
        grid = named_items(root, "spectrogram-channel-grid")[0]
        assert_equal_data_geometry(grid, 5)
        assert len(named_items(grid, "channel-grid-color-scale")) == 1
        items = named_items(grid, "spectrogram-channel-image-")
        assert len(items) == 5
        assert {image.width() for image in items} == {grid.property("dataWidth")}
        for item in items:
            index = int(item.objectName().rsplit("-", 1)[1])
            assert item.curve is list(panel._channels.values())[index].image
        for index, view in enumerate(panel.view_model()._channels):
            assert view.label == f"Channel {index * 2 + 1}"
            assert view.vertical_axis is panel.view_model().vertical_axis
            assert view.horizontal_axis is panel.view_model().horizontal_axis
            assert view.color_axis is panel.view_model().color_axis
        previous = list(panel.view_model()._channels)
        buffer.handle_configuration_changed(ChannelConfiguration(0, (1, 3), 9, 2))
        settle(qt_application)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert all(sip.isdeleted(view) for view in previous)
        assert_equal_data_geometry(grid, 2)
        root.setProperty("width", 1)
        root.setProperty("height", 1)
        settle(qt_application)
        assert_equal_data_geometry(grid, 2)
        assert all(channel.image.screen_width() >= 1 and channel.image.screen_height() >= 1
                   for channel in panel._channels.values())
        # Hidden zero-sized cells retain a one-pixel processing cache so the
        # next audio callback cannot request an empty frequency resampling.
        push(panel, buffer, asymmetric_signals(1024)[:2])
        assert all(channel.image.last_data_time != 0 for channel in panel._channels.values())
        assert not warnings, "\n".join(warning.toString() for warning in warnings)
    finally:
        sip.delete(root)
        sip.delete(engine)
