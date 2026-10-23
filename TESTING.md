# Source tests and CI policy

The source suite runs through pytest discovery, using `testpaths` and
`python_files` in `pyproject.toml`. New tests under `polyfriture/test/` join CI
automatically; there is no selected-file allowlist.

## Run locally

```sh
uv sync --frozen --dev
uv run --frozen pytest -ra
```

The test configuration supplies headless Qt defaults (`offscreen`, `Basic`
controls, and software Qt Quick rendering) before collection and retains one
`QApplication` for the session. An explicit environment setting overrides a
default when debugging. No display server or audio device is required.

On Ubuntu, install the runtime libraries before syncing:

```sh
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  libportaudio2 libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0
```

Windows and macOS use the PortAudio library bundled with the locked
`sounddevice` wheel. The source suite does not need the packaging scripts,
PyInstaller output, a source-built PortAudio, or a virtual audio device.

To reproduce a CI Python version, set `UV_PYTHON` to `3.11` or `3.14` before
both commands. For example, in PowerShell:

```powershell
$env:UV_PYTHON = '3.14'
uv sync --frozen --dev
uv run --frozen pytest -ra --junitxml=test-results/junit.xml
```

`UV_PYTHON` takes precedence over the repository's `.python-version` file.
CI pins uv to 0.10.5 and installs project and development dependencies from
`uv.lock`; it does not update the lock file or install an additional pytest
version independently.

## Coverage and triggers

[The source-test workflow](.github/workflows/tests.yml) runs this matrix:

| Runner | Python versions |
| --- | --- |
| Ubuntu 22.04 | 3.11, 3.14 |
| Windows Server 2022 | 3.11, 3.14 |
| macOS 15 | 3.11, 3.14 |

Python 3.11 covers the declared minimum. Python 3.14 provides a newer
interpreter with binary-wheel coverage in the current lock file; this initial
matrix does not claim to test every permitted Python version. In particular,
the locked NumPy 2.4.6 has wheels through Python 3.14. Changing this matrix or
adding a dependency-upgrade lane is an explicit future policy change.

Every pull request and push to `main` runs the entire discovered suite.
Superseded PR test runs are cancelled. Matrix jobs continue independently
after another job fails, so platform-specific failures remain visible.

## Merge and release gates

- **Pull requests:** the stable `Source tests` check succeeds only when every
  matrix job succeeds. This is the check to require in the `main` branch
  ruleset, rather than maintaining six version-specific required check names.
  Workflow files report checks; enforcement of required checks is configured
  separately in the repository's branch rules.
- **Packaging:** the existing build jobs and packaged-application launch
  checks remain separate from source testing. Their outcomes are separately
  visible on PRs and `main`.
- **Tagged releases:** the build workflow calls the same source-test workflow
  at the tagged commit. Release creation requires that call and all three
  packaging jobs to succeed. The release job runs only for tag pushes, so PRs
  and ordinary branch pushes do not download artifacts for release preparation.

Dependencies failing to install, collection errors, test failures and cancelled
matrix jobs fail the aggregate source check. Diagnostic artifact transport
failures emit a warning and do not change the test outcome. Existing packaging
artifact upload behavior is unchanged.

## Results and isolation

Each matrix job records Python, uv, pytest, NumPy, PyQt, compiled/runtime Qt,
and PortAudio versions. Console output, environment details, and JUnit XML are
uploaded as OS/Python-specific artifacts with 14-day retention, including on
test failure. The job's console log remains available if artifact upload fails.
`-ra` makes skip reasons visible.

Tests use synthetic signals and mocked audio hardware. Settings tests use
temporary INI stores or mocked source discovery. Native-format integration tests
use unique test namespaces on Windows and explicit temporary files elsewhere;
they destroy settings objects and remove their files or exact empty registry
parents on success, failure and skip. Tests must not read installed Friture
profiles, write application settings, or open real audio devices. A future test
requiring real hardware needs a separately reviewed opt-in mechanism.

Windows registry/private-hive tests are intentionally skipped on other operating
systems. Native settings tests can skip when the temporary native store is not
writable; the reason is reported. These platform/access conditions are the only
current exceptions: there are no known-failure exclusions or broad xfails.

## Audited baseline

The full suite on `main` at `83a1e81` was audited on 23 October 2026 using
Windows, Python 3.13.4, pytest 9.1.1, NumPy 2.4.6, PyQt 6.11.0 and Qt runtime
6.11.1: **313 collected, 310 passed, 3 failed**.

All three failures were obsolete pitch-tracker tests: missing required input
timestamps, a search range above the fixture's Nyquist frequency, and an expected
pitch outside the configured search range. This change repairs those fixtures,
tests fundamental detection with a stronger second harmonic and a stated
10-cent tolerance, and tests frame/history bookkeeping with deterministic pitch
estimates. Production DSP behavior is unchanged. After repair, the same full
suite passes without known-failure exceptions.
