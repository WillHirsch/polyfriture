"""Run GUI tests headlessly with one application for the whole test session."""

from collections.abc import Iterator
import os

import pytest


# Configure Qt before test modules import GUI or QML components. Explicit
# environment overrides remain available when debugging with a real display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qt_application() -> Iterator[QApplication]:
    # Module and unittest fixtures can reuse this instance without allowing the
    # application to be destroyed between groups of GUI tests.
    application = QApplication.instance() or QApplication([])
    assert isinstance(application, QApplication)
    yield application
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
