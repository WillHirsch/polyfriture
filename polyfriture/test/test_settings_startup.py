"""A settings-import failure must abort startup with a useful GUI message."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_settings_failure_explains_retry_and_aborts_before_audio_or_main_window(tmp_path):
    # Startup changes Qt metadata, exception hooks and logging handlers. Run it
    # in a fresh process so none of those changes leak into the other GUI tests.
    script = textwrap.dedent("""\
        import sys
        from unittest.mock import patch

        from polyfriture import analyzer

        # An unexpected assertion should fail the subprocess, not open the
        # application's general-purpose exception dialog and wait for a user.
        sys.excepthook = sys.__excepthook__
        log_directory = sys.argv[1]
        detail = (
            "Cannot read Friture's Store settings while its registry hive is in use. "
            "Close Friture and any Registry Editor opened in its package context, then retry."
        )
        failure = analyzer.SettingsInitializationError(detail)
        with (
            patch.object(analyzer, "initialize_settings", side_effect=failure) as initialize,
            patch.object(analyzer, "Friture", side_effect=AssertionError("Window created")) as window,
            patch.object(analyzer, "AudioBackend", side_effect=AssertionError("Audio opened")) as audio,
            patch.object(analyzer.QMessageBox, "critical") as message,
            patch.object(analyzer, "log_directory", return_value=log_directory),
            patch.object(analyzer.platform, "system", return_value="startup-test"),
            patch.object(sys, "argv", ["polyfriture", "--no-splash"]),
        ):
            try:
                analyzer.main()
            except SystemExit as error:
                assert error.code == 1
                assert error.__cause__ is failure
            else:
                raise AssertionError("Startup continued after settings initialization failed")

            initialize.assert_called_once_with()
            message.assert_called_once_with(
                None, analyzer.APPLICATION_DISPLAY_NAME + " settings", detail
            )
            window.assert_not_called()
            audio.assert_not_called()
        """)
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "logs")],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
