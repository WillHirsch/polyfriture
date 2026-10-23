"""Rotate the display and its physical axes without rotating audio histories."""

from pathlib import Path

import numpy as np
import pytest
from PyQt6 import sip
from PyQt6.QtCore import QSettings, QUrl
from PyQt6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression
from PyQt6.QtWidgets import QCheckBox

import polyfriture.plotting.frequency_scales as fscales
from polyfriture.channel_configuration import ChannelConfiguration
from polyfriture.settings_model import BoolSetting, SettingsValueError
from polyfriture.test.test_channel_grid import (
    assert_equal_data_geometry, named_items, settle,
)
from polyfriture.test.test_spectrogram_channels import (
    asymmetric_signals, panel_factory, pixels, push,
)


def assert_axis(axis, name, endpoints, scale):
    assert axis.name == name
    assert (axis.scale_division.scale_min, axis.scale_division.scale_max) == endpoints
    assert axis.scale_division.scale is scale
    transform = axis.coordinate_transform
    assert transform.scale is scale
    assert (transform.coord_min, transform.coord_max) == endpoints
    assert transform.toPlot(0) == pytest.approx(endpoints[0])
    assert transform.toPlot(1) == pytest.approx(endpoints[1])
    midpoint = scale.inverse((scale.transform(endpoints[0]) + scale.transform(endpoints[1])) / 2)
    assert transform.toPlot(0.5) == pytest.approx(midpoint)
    assert transform.toScreen(midpoint) == pytest.approx(0.5)


@pytest.mark.parametrize("scale", fscales.ALL)
def test_physical_axes_scales_and_tracker_formatters_follow_live_orientation(panel_factory, scale):
    panel, _ = panel_factory()
    panel.setminfreq(80)
    panel.setmaxfreq(12000)
    panel.timerangechanged(7.5)
    panel.setfreqscale(scale)
    model = panel.view_model()
    horizontal, vertical, color = model.horizontal_axis, model.vertical_axis, model.color_axis
    for rotated in (False, True, False):
        panel.setrotated(rotated)
        assert model.rotated is rotated
        assert model.horizontal_axis is horizontal
        assert model.vertical_axis is vertical
        assert model.color_axis is color
        frequency_axis, time_axis = (horizontal, vertical) if rotated else (vertical, horizontal)
        assert_axis(frequency_axis, "Frequency (Hz)", (80, 12000), scale)
        assert_axis(time_axis, "Time (s)", (7.5, 0) if rotated else (0, 7.5), fscales.Linear)
        assert frequency_axis.formatTracker(440) == "440 Hz (A4)"
        assert time_axis.formatTracker(3.5) == "3.50 s"
        for channel in model._channels:
            assert channel.horizontal_axis is horizontal
            assert channel.vertical_axis is vertical
            assert channel.color_axis is color


def test_shared_parameters_and_new_channel_generation_keep_rotated_axes(panel_factory):
    panel, buffer = panel_factory()
    panel.setrotated(True)
    panel.setminfreq(200)
    panel.setmaxfreq(10000)
    panel.setfreqscale(fscales.Logarithmic)
    panel.timerangechanged(4)
    panel.setweighting(1)
    panel.setmin(-100)
    panel.setmax(-20)
    buffer.handle_configuration_changed(ChannelConfiguration(0, (1, 3), 9, 2))
    model = panel.view_model()
    assert model.rotated is True
    assert_axis(model.horizontal_axis, "Frequency (Hz)", (200, 10000), fscales.Logarithmic)
    assert_axis(model.vertical_axis, "Time (s)", (4, 0), fscales.Linear)
    assert model.color_axis.name == "PSD (dB A)"
    assert (model.color_axis.scale_division.scale_min, model.color_axis.scale_division.scale_max) == (-100, -20)
    assert [channel.label for channel in model._channels] == ["Channel 2", "Channel 4"]
    for channel in panel._channels.values():
        assert channel.image.T == 4
        assert channel.frequency_resampler.scale is fscales.Logarithmic
        assert channel.frequency_resampler.minfreq == 200
        assert channel.frequency_resampler.maxfreq == 10000
    # Moving the analysis axes back also restores a linear horizontal time axis.
    panel.setrotated(False)
    assert_axis(model.horizontal_axis, "Time (s)", (0, 4), fscales.Linear)
    assert_axis(model.vertical_axis, "Frequency (Hz)", (200, 10000), fscales.Logarithmic)


def test_rotation_preserves_paused_history_clocks_and_processing_state(panel_factory):
    panel, buffer = panel_factory()
    reference, reference_buffer = panel_factory()
    initial = asymmetric_signals(2048)
    push(panel, buffer, initial)
    push(reference, reference_buffer, initial)
    panel.PlotZoneImage.draw(4)
    panel.pause()
    before = []
    for channel in panel._channels.values():
        before.append((
            channel, pixels(channel.image), channel.screen_resampler.orig_index,
            channel.screen_resampler.resampled_index, channel.image.last_data_time,
            channel.image.paint_time, channel.image.canvasscaledspectrogram.write_offset,
        ))
    cursor = panel.old_index
    for rotated in (True, False, True):
        panel.setrotated(rotated)
        assert panel.PlotZoneImage.paused
        assert panel.old_index == cursor
        for channel, raster, original, resampled, timestamp, paint_time, write_offset in before:
            assert not channel.image.is_playing
            np.testing.assert_array_equal(pixels(channel.image), raster)
            assert channel.screen_resampler.orig_index == original
            assert channel.screen_resampler.resampled_index == resampled
            assert channel.image.last_data_time == timestamp
            assert channel.image.paint_time == paint_time
            assert channel.image.canvasscaledspectrogram.write_offset == write_offset
    # Without a QML geometry change, display orientation cannot affect DSP.
    following = asymmetric_signals(1024, 2048)
    panel.restart()
    push(panel, buffer, following)
    push(reference, reference_buffer, following)
    for channel, other in zip(panel._channels.values(), reference._channels.values()):
        np.testing.assert_array_equal(pixels(channel.image), pixels(other.image))
        np.testing.assert_array_equal(channel.screen_resampler.old_data, other.screen_resampler.old_data)


def test_orientation_is_one_panel_setting_with_independent_save_restore(panel_factory, tmp_path):
    panel, _ = panel_factory()
    other, _ = panel_factory()
    assert isinstance(panel.settings_dialog.model.fields["rotated"], BoolSetting)
    assert panel.settings_dialog.model.get("rotated") is False
    checkboxes = panel.settings_dialog.findChildren(QCheckBox)
    assert len(checkboxes) == 1
    checkboxes[0].setChecked(True)
    assert panel.view_model().rotated is True
    assert other.view_model().rotated is False
    assert panel.settings_dialog.model.get("rotated") is True
    with pytest.raises(SettingsValueError):
        panel.settings_dialog.model.set("rotated", "sideways")
    settings = QSettings(str(tmp_path / "orientation.ini"), QSettings.Format.IniFormat)
    panel.saveState(settings)
    settings.sync()
    other.restoreState(QSettings(settings.fileName(), QSettings.Format.IniFormat))
    assert other.view_model().rotated is True
    assert other.settings_dialog.findChildren(QCheckBox)[0].isChecked()
    assert len(panel.parent().findChildren(type(panel.settings_dialog))) == 1
    assert len(other.parent().findChildren(type(other.settings_dialog))) == 1


@pytest.mark.parametrize("saved", [None, "sideways", 2, [], False, "false", 0])
def test_missing_invalid_and_false_saved_orientation_restore_standard_view(panel_factory, tmp_path, saved):
    panel, _ = panel_factory()
    checkbox = panel.settings_dialog.findChildren(QCheckBox)[0]
    checkbox.setChecked(True)
    settings = QSettings(str(tmp_path / "orientation.ini"), QSettings.Format.IniFormat)
    if saved is not None:
        settings.setValue("rotated", saved)
    panel.restoreState(settings)
    assert panel.settings_dialog.model.get("rotated") is False
    assert panel.view_model().rotated is False
    assert not checkbox.isChecked()
    assert panel.view_model().horizontal_axis.name == "Time (s)"


def test_real_qml_rotates_only_images_and_rebinds_physical_tracker_axes(panel_factory, qt_application):
    panel, buffer = panel_factory((0, 2, 4, 6, 8))
    engine, root, warnings = create_scene(panel)
    try:
        settle(qt_application)
        push(panel, buffer, np.tile(asymmetric_signals(2048)[0], (5, 1)))
        panel.pause()
        cursor = panel.old_index
        clocks = [(channel.image.paint_time, channel.image.last_data_time) for channel in panel._channels.values()]
        grid = named_items(root, "spectrogram-channel-grid")[0]
        for rotated in (False, True, False):
            panel.setrotated(rotated)
            settle(qt_application)
            assert (grid.property("rowCount"), grid.property("columnCount")) == ((3, 2) if rotated else (2, 3))
            assert_equal_data_geometry(grid, 5)
            assert len(named_items(grid, "channel-grid-color-scale")) == 1
            assert panel.old_index == cursor
            for item in named_items(grid, "spectrogram-channel-image-"):
                assert item.rotated is rotated
                assert item.rotation() == 0
                assert item.curve.screen_width() == max(1, int(item.height() if rotated else item.width()))
                assert item.curve.screen_height() == max(1, int(item.width() if rotated else item.height()))
                assert np.any(pixels(item.curve) != 0xFF000000)
            assert [(channel.image.paint_time, channel.image.last_data_time) for channel in panel._channels.values()] == clocks
            for data_item in named_items(grid, "channel-grid-data-"):
                tracker = named_items(data_item, "plot-tracker-text")
                assert len(tracker) == 1
                expected = (panel.view_model().horizontal_axis.formatTracker(panel.minfreq if rotated else 0)
                            + ", " + panel.view_model().vertical_axis.formatTracker(0 if rotated else panel.maxfreq))
                assert tracker[0].property("text") == expected
            assert not warnings, "\n".join(warning.toString() for warning in warnings)
        panel.setrotated(True)
        settle(qt_application)
        panel.restart()
        push(panel, buffer, np.tile(asymmetric_signals(1024, 2048)[0], (5, 1)))
        assert panel.old_index > cursor
        assert not panel.PlotZoneImage.paused
        assert len({channel.image.last_data_time for channel in panel._channels.values()}) == 1
        for channel, (_, previous_time) in zip(panel._channels.values(), clocks):
            assert channel.image.last_data_time > previous_time
            assert channel.screen_resampler.height == channel.image.screen_height()
            assert channel.frequency_resampler.nsamples == channel.image.screen_height()
        assert not warnings, "\n".join(warning.toString() for warning in warnings)
    finally:
        sip.delete(root)
        sip.delete(engine)


def test_single_cell_stationary_tracker_changes_units_when_coordinates_stay_equal(panel_factory, qt_application):
    panel, _ = panel_factory((0,))
    panel.setfreqscale(fscales.Linear)
    panel.setmaxfreq(20)
    panel.timerangechanged(20)
    engine, root, warnings = create_scene(panel)
    try:
        settle(qt_application)
        grid = named_items(root, "spectrogram-channel-grid")[0]
        data = named_items(grid, "channel-grid-data-")[0]
        tracker = named_items(data, "plot-tracker-text")[0]
        crosshair = next(item for item in descendants(data) if item.metaObject().indexOfProperty("relativePosX") >= 0)
        # Keep the tracker at the bottom right throughout the switch. All
        # coordinates are numerically 20, but their physical units change.
        position = QQmlExpression(QQmlEngine.contextForObject(crosshair), crosshair,
                                 "relativePosX = 1; relativePosY = 1; true")
        assert position.evaluate() == (True, False)
        assert not position.hasError(), position.error().toString()
        for rotated in (False, True, False):
            panel.setrotated(rotated)
            settle(qt_application)
            assert (grid.property("rowCount"), grid.property("columnCount")) == (1, 1)
            horizontal, vertical = panel.view_model().horizontal_axis, panel.view_model().vertical_axis
            assert tracker.property("text") == horizontal.formatTracker(20) + ", " + vertical.formatTracker(20)
        assert not warnings, "\n".join(warning.toString() for warning in warnings)
    finally:
        sip.delete(root)
        sip.delete(engine)


def create_scene(panel):
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
    return engine, root, warnings


def descendants(item):
    for child in item.childItems():
        yield child
        yield from descendants(child)
