#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2009 Timothée Lecomte

# This file is part of Friture.
#
# Friture is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as published by
# the Free Software Foundation.
#
# Friture is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Friture.  If not, see <http://www.gnu.org/licenses/>.

import sys
import logging
import time
import traceback
import friture_monitor
from pathlib import Path
from html import escape
from friture_monitor.application import APPLICATION_NAME, ISSUES_URL, LOG_FILENAME, configure_application, log_directory
from PyQt6 import QtCore
from PyQt6.QtWidgets import QMessageBox, QApplication


def fileexcepthook(exception_type, exception_value, traceback_object):
    logger = logging.getLogger(__name__)

    exceptionText = "".join(traceback.format_exception(exception_type, exception_value, traceback_object))
    logger.critical("Unhandled exception: %s", exceptionText)

    versionInfo = APPLICATION_NAME + " " + friture_monitor.__version__
    timeString = time.strftime("%Y-%m-%d, %H:%M:%S")

    logDir = log_directory()

    notice = """
        <h1>Oops! Something went wrong!</h1>
        <p>Sorry, there was an error we could not handle.</p>
        <p>You can choose to abort, or to ignore the error and try to continue
        (this is not guaranteed to work).</p>
        <h2>Please help us fix it!</h2>\n\n
        <p>Please create an issue on <a href="{issuesUrl}">{issuesUrl}</a>
        and include the log file named <i>{logFileName}</i> from the following folder:</p>
        <p><a href="{logDirUrl}">{logDir}</a></p>
        <h3>Error details</h3>""" \
        .format(logFileName=LOG_FILENAME, logDir=escape(logDir), logDirUrl=Path(logDir).as_uri(), issuesUrl=ISSUES_URL)

    msg = notice + timeString + ' (%s)' % versionInfo + '<br>' + exceptionText.replace("\r\n", "\n").replace("\n", "<br>").replace(" ", '&nbsp;')

    return msg


def errorBox(message):
    logger = logging.getLogger(__name__)

    try:
        if QApplication.instance() is None:
            app = QApplication(sys.argv)  # assignment is needed to keep the application alive
            configure_application(app)

        errorbox = QMessageBox()
        errorbox.setWindowTitle(APPLICATION_NAME + " error occurred")
        errorbox.setText(message)
        errorbox.setTextFormat(QtCore.Qt.TextFormat.RichText)
        errorbox.setStandardButtons(QMessageBox.StandardButton.Abort)

        continueButton = errorbox.addButton("Ignore and try to continue", QMessageBox.ButtonRole.RejectRole)

        ret = errorbox.exec()

        if ret == QMessageBox.StandardButton.Abort:
            sys.exit(1)
        else:
            logger.info("Try to continue")
    except Exception:
        logger.exception("Failed to display the error box")


def excepthook(exception_type, exception_value, traceback_object):
    gui_message = fileexcepthook(exception_type, exception_value, traceback_object)
    errorBox(gui_message)


sys.excepthook = excepthook
