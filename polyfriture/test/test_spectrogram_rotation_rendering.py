"""Rotate the real rolling raster while retaining its canonical DSP axes."""

import numpy as np
import pytest
from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtTest import QSignalSpy

from polyfriture.spectrogram_item import SpectrogramItem
from polyfriture.spectrogram_item_data import SpectrogramImageData


def image_pixels(image):
    return np.array([[image.pixel(x, y) for x in range(image.width())]
                     for y in range(image.height())], dtype=np.uint32)


def asymmetric_pixels(height, width):
    rows, columns = np.indices((height, width), dtype=np.uint32)
    return np.uint32(0xFF000000) | ((rows + 1) << 16) | ((columns + 1) << 8) | (rows + columns)


def paint(item):
    result = QImage(int(item.width()), int(item.height()), QImage.Format.Format_RGB32)
    result.fill(Qt.GlobalColor.magenta)
    painter = QPainter(result)
    try:
        item.paint(painter)
    finally:
        painter.end()
    return result


@pytest.mark.parametrize("rotated", [False, True])
def test_asymmetric_raster_has_correct_time_and_frequency_edges(qt_application, rotated):
    item = SpectrogramItem()
    image = SpectrogramImageData()
    try:
        item.setWidth(7)
        item.setHeight(5)
        item.rotated = rotated
        item.curve = image
        logical_width, logical_height = (5, 7) if rotated else (7, 5)
        colors = asymmetric_pixels(logical_height, logical_width)
        image.push(colors, 4.)
        image.draw(4.)

        # The input is ordered low-to-high in frequency, while the canonical
        # raster places high frequencies at the top and newest samples right.
        canonical = np.flipud(colors)
        expected = np.rot90(canonical, -1) if rotated else canonical
        np.testing.assert_array_equal(image_pixels(paint(item)), expected)
        if rotated:
            np.testing.assert_array_equal(expected[-1], colors[:, -1])
            np.testing.assert_array_equal(expected[:, -1], colors[-1])
        else:
            np.testing.assert_array_equal(expected[:, -1], colors[::-1, -1])
            np.testing.assert_array_equal(expected[0], colors[-1])
    finally:
        sip.delete(item)
        sip.delete(image)


def test_live_rotation_resize_and_paused_cache_preserve_history(qt_application):
    item = SpectrogramItem()
    image = SpectrogramImageData()
    try:
        item.setWidth(10)
        item.setHeight(6)
        item.curve = image
        image.set_jitter(0.2)
        image.push(asymmetric_pixels(6, 4), 8.)
        image.draw(8.)
        image.pause()
        canvas = image.canvasscaledspectrogram
        before = canvas.pixmap.toImage()
        changes = QSignalSpy(item.rotatedChanged)

        item.rotated = True
        assert len(changes) == 1
        assert (image.screen_width(), image.screen_height()) == (6, 10)
        assert (canvas.canvas_width, canvas.canvas_height) == (8, 10)
        # Rotation uses the same sequential smooth resizes as any ordinary
        # cache resize, including its jitter margin; it never erases history.
        expected = before.scaled(16, 6, Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        expected = expected.scaled(16, 10, Qt.AspectRatioMode.IgnoreAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        np.testing.assert_array_equal(image_pixels(canvas.pixmap.toImage()), image_pixels(expected))
        assert canvas.write_offset == pytest.approx(4 * 8 / 12)
        assert image.last_data_time == canvas.last_write_time == image.paint_time == 8.
        assert not image.is_playing

        item.rotated = True
        assert len(changes) == 1
        item.setWidth(9)
        item.setHeight(7)
        assert (image.screen_width(), image.screen_height()) == (7, 9)
        assert (canvas.canvas_width, canvas.canvas_height) == (9, 9)
        assert image.last_data_time == canvas.last_write_time == image.paint_time == 8.
        assert np.any(image_pixels(canvas.pixmap.toImage()) != 0xFF000000)

        item.rotated = False
        assert len(changes) == 2
        assert (image.screen_width(), image.screen_height()) == (9, 7)
        assert not image.is_playing
        assert np.any(image_pixels(canvas.pixmap.toImage()) != 0xFF000000)
    finally:
        sip.delete(item)
        sip.delete(image)


@pytest.mark.parametrize("rotated", [False, True])
def test_paint_restores_callers_transform(qt_application, rotated):
    item = SpectrogramItem()
    image = SpectrogramImageData()
    result = QImage(20, 20, QImage.Format.Format_RGB32)
    painter = QPainter(result)
    try:
        item.setWidth(7)
        item.setHeight(5)
        item.curve = image
        item.rotated = rotated
        painter.translate(2, 3)
        original = painter.worldTransform()
        item.paint(painter)
        assert painter.worldTransform() == original
    finally:
        painter.end()
        sip.delete(item)
        sip.delete(image)
