"""Application identity and isolated persistent and temporary settings stores."""

import os

import platformdirs
from PyQt6.QtCore import QDir, QSettings, QTemporaryFile
from PyQt6.QtGui import QGuiApplication

from polyfriture import __version__


APPLICATION_NAME = "polyfriture"
APPLICATION_DISPLAY_NAME = "Polyfriture"
ORGANIZATION_NAME = "polyfriture"
APPLICATION_ID = "io.github.willhirsch.polyfriture"
QML_MODULE = "polyfriture"
PROJECT_URL = "https://github.com/WillHirsch/polyfriture"
ISSUES_URL = PROJECT_URL + "/issues"
LOG_FILENAME = APPLICATION_NAME + ".log.txt"
PYTHON_PROFILE_FILENAME = APPLICATION_NAME + ".cprof"
KCACHEGRIND_PROFILE_FILENAME = APPLICATION_NAME + ".cachegrind"


def configure_application(app: QGuiApplication) -> None:
    """Set metadata before any window, theme, or settings consumer is created."""
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setOrganizationDomain("willhirsch.github.io")
    app.setApplicationName(APPLICATION_NAME)
    app.setApplicationDisplayName(APPLICATION_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APPLICATION_NAME)


def application_settings() -> QSettings:
    """Open only the fork's settings, independently of caller application metadata."""
    settings = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)
    settings.setFallbacksEnabled(False)
    return settings


def temporary_settings() -> QSettings:
    """Create an independent widget cache removed when its settings object dies.

    A default QSettings instance shares the application's persistent store. It
    cannot serve as a snapshot when several closed or replaced widgets retain
    different settings.
    """
    temporary_file = QTemporaryFile(os.path.join(QDir.tempPath(), APPLICATION_NAME + "-XXXXXX.ini"))
    if not temporary_file.open():
        raise OSError("Could not create a temporary settings cache: " + temporary_file.errorString())
    filename = temporary_file.fileName()
    # Release the handle so QSettings can replace the file atomically on Windows.
    temporary_file.close()
    settings = QSettings(filename, QSettings.Format.IniFormat)
    temporary_file.setParent(settings)
    settings.setFallbacksEnabled(False)
    return settings


def log_directory() -> str:
    return platformdirs.user_log_dir(APPLICATION_NAME, "")
