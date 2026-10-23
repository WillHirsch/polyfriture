"""Exercise packaged-startup decisions with real, isolated child processes."""

import importlib.util
from pathlib import Path
import sys

import pytest


@pytest.fixture
def smoke(monkeypatch, tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts" / "smoke_test.py"
    spec = importlib.util.spec_from_file_location("packaged_smoke", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    log = tmp_path / "polyfriture.log.txt"
    monkeypatch.setattr(module, "log_file_path", lambda: str(log))
    monkeypatch.setattr(module, "startup_banner", lambda: "Polyfriture test starting")
    monkeypatch.setattr(module, "TIMEOUT_SECONDS", 2)
    return module, log


def run_child(monkeypatch, module, log, code):
    preamble = "from pathlib import Path\nimport sys, time\nlog = Path(%r)\n" % str(log)
    monkeypatch.setattr(sys, "argv", ["smoke_test.py", sys.executable, "-c", preamble + code])
    return module.main()


def startup_text(module):
    return module.startup_banner() + "\n" + module.FULL_INIT_LINE + "\n"


def test_previous_success_does_not_pass_a_launch_that_never_initializes(smoke, monkeypatch):
    module, log = smoke
    log.write_text(startup_text(module), encoding="utf-8")

    assert run_child(monkeypatch, module, log, "pass") == 1


def test_previous_full_init_does_not_complete_a_new_partial_startup(smoke, monkeypatch):
    module, log = smoke
    log.write_text(startup_text(module), encoding="utf-8")

    assert run_child(
        monkeypatch, module, log,
        "with log.open('a', encoding='utf-8') as output:\n"
        "    output.write(%r)\n" % (module.startup_banner() + "\n"),
    ) == 1


def test_new_success_ignores_an_older_launch_failure(smoke, monkeypatch):
    module, log = smoke
    old_log = "Traceback (most recent call last): old failure\n"
    log.write_text(old_log, encoding="utf-8")

    assert run_child(
        monkeypatch, module, log,
        "with log.open('a', encoding='utf-8') as output:\n"
        "    output.write(%r)\n" % startup_text(module),
    ) == 0
    assert log.read_text(encoding="utf-8") == old_log + startup_text(module)


def test_normal_log_rotation_still_accepts_current_startup(smoke, monkeypatch):
    module, log = smoke
    log.write_text("Unhandled exception: older launch\n", encoding="utf-8")

    assert run_child(
        monkeypatch, module, log,
        "log.rename(log.with_suffix('.txt.1'))\n"
        "log.write_text(%r, encoding='utf-8')\n" % startup_text(module),
    ) == 0


def test_crash_after_full_init_fails(smoke, monkeypatch):
    module, log = smoke

    assert run_child(
        monkeypatch, module, log,
        "log.write_text(%r, encoding='utf-8')\nsys.exit(1)\n" % startup_text(module),
    ) == 1


def test_initialized_application_can_remain_running_until_timeout(smoke, monkeypatch):
    module, log = smoke

    assert run_child(
        monkeypatch, module, log,
        "log.write_text(%r, encoding='utf-8')\ntime.sleep(60)\n" % startup_text(module),
    ) == 0


@pytest.mark.parametrize("destination", ["stdout", "stderr", "log"])
def test_current_python_or_qml_error_fails(smoke, monkeypatch, destination):
    module, log = smoke
    code = "log.write_text(%r, encoding='utf-8')\n" % startup_text(module)
    error = "QML error(s): missing packaged asset"
    if destination == "log":
        code += "with log.open('a', encoding='utf-8') as output:\n    output.write(%r)\n" % error
    else:
        code += "print(%r, file=sys.%s)\n" % (error, destination)

    assert run_child(monkeypatch, module, log, code) == 1
