"""Settings initialization, one-time Friture import, and durable retries."""

from contextlib import ExitStack, contextmanager
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QByteArray, QSettings

from polyfriture import friture_settings, settings_initialization, settings_schema
from polyfriture.dock import DockSettings
from polyfriture.dockmanager import DockLayoutSettings
from polyfriture.generators.sweep import SweepSettings
from polyfriture.settings import GlobalSettings
from polyfriture.spectrum_settings import SpectrumSettings
from polyfriture.theme_manager import ThemeSettings
from polyfriture.settings_initialization import (
    FRITURE_IMPORT_STATE_KEY,
    INITIALIZATION_JOURNAL_KEY,
    SCHEMA_VERSION_KEY,
    SettingsInitializationError,
    initialize_settings,
)


def ini_settings(path, settings_class=QSettings):
    settings = settings_class(str(path), QSettings.Format.IniFormat)
    settings.setFallbacksEnabled(False)
    return settings


@pytest.fixture
def stores(tmp_path):
    return ini_settings(tmp_path / "fork.ini"), ini_settings(tmp_path / "friture.ini")


def discard_native_store(settings):
    try:
        settings.clear()
        settings.sync()
    finally:
        sip.delete(settings)


def remove_native_registry_namespace(organization):
    import winreg

    try:
        # The stores have been destroyed; remove only their empty test parent.
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, "Software\\" + organization)
    except FileNotFoundError:
        pass


@contextmanager
def native_stores(tmp_path):
    organization = "PolyfritureInitializationTests-" + uuid4().hex
    with ExitStack() as cleanup:
        if sys.platform == "win32":
            cleanup.callback(remove_native_registry_namespace, organization)
        settings_pair = []
        for application in ("fork", "friture"):
            if sys.platform == "win32":
                settings = QSettings(QSettings.Format.NativeFormat, QSettings.Scope.UserScope,
                                     organization, application)
            else:
                suffix = ".plist" if sys.platform == "darwin" else ".conf"
                path = tmp_path / (application + suffix)
                cleanup.callback(path.unlink, missing_ok=True)
                settings = QSettings(str(path), QSettings.Format.NativeFormat)
            cleanup.callback(discard_native_store, settings)
            settings.setFallbacksEnabled(False)
            settings_pair.append(settings)
        yield settings_pair


def assert_native_stores_removed(paths):
    if sys.platform == "win32":
        import winreg

        namespace = paths[0].lstrip("\\").removeprefix("HKEY_CURRENT_USER\\").rsplit("\\", 1)[0]
        assert namespace.startswith("Software\\PolyfritureInitializationTests-")
        with pytest.raises(FileNotFoundError):
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, namespace):
                pass
    else:
        assert all(not Path(path).exists() for path in paths)


def snapshot(settings):
    return {key: settings.value(key) for key in settings.allKeys()}


def write_values(settings, values):
    for key, value in values.items():
        settings.setValue(key, value)
    settings.sync()
    assert settings.status() == QSettings.Status.NoError


def assert_complete(settings, state):
    assert settings.value(SCHEMA_VERSION_KEY, type=int) == settings_schema.CURRENT_VERSION
    assert settings.value(FRITURE_IMPORT_STATE_KEY) == state
    assert not settings.contains(INITIALIZATION_JOURNAL_KEY)


class UnreadableFritureSource(QSettings):
    """Make accidental Friture access observable even when it contains no keys."""

    def allKeys(self):
        raise AssertionError("Initialized fork settings must not read Friture")

    def value(self, *args, **kwargs):
        raise AssertionError("Initialized fork settings must not read Friture")

    def sync(self):
        raise AssertionError("Friture settings must never be synchronized")


class FailCheckpointOnce(QSettings):
    """Persist a checkpoint but report a failed flush, as an interrupted write may."""

    failure_phase = None
    failed = False
    report_error = False

    def sync(self):
        super().sync()
        if self.failed or not self.contains(INITIALIZATION_JOURNAL_KEY):
            return
        if self.contains(SCHEMA_VERSION_KEY):
            phase = "markers"
        elif self.contains("AudioBackend/deviceName"):
            phase = "payload"
        else:
            phase = "journal"
        if phase == self.failure_phase:
            self.failed = True
            self.report_error = True

    def status(self):
        if self.report_error:
            self.report_error = False
            return QSettings.Status.AccessError
        return super().status()


def test_import_preserves_nested_values_and_leaves_source_unchanged(stores):
    fork, friture_source = stores
    values = {
        "themePreference": 2,
        "AudioBackend/themePreference": 2,
        "AudioBackend/deviceName": "USB audio interface",
        "AudioBackend/firstChannel": 3,
        "AudioBackend/secondChannel": 7,
        "AudioBackend/duoInput": -3,
        "Docks/dockNames": ["Dock 2", "Dock 7"],
        "Docks/Dock 2/type": 1,
        "Docks/Dock 2/timeRange": 25,
        "Docks/Dock 7/type": 2,
        "Docks/Dock 7/customNested/value": "retained",
        "Docks/widgetIdStack": [],
        "MainWindow/windowGeometry": QByteArray(b"\x00\x01\xffgeometry"),
        "customBoolean": True,
    }
    write_values(friture_source, values)
    before = snapshot(friture_source)
    source_bytes = Path(friture_source.fileName()).read_bytes()

    initialize_settings(fork, friture_source)

    expected = {**before, "Docks/dockNames": ["Meters", "Dock 2", "Dock 7"], "Docks/Meters/type": 9}
    for key, value in expected.items():
        assert fork.value(key) == value
    assert isinstance(fork.value("MainWindow/windowGeometry"), QByteArray)
    assert snapshot(friture_source) == before
    assert Path(friture_source.fileName()).read_bytes() == source_bytes
    assert_complete(fork, "imported")


def test_completed_import_never_reads_friture_again(stores, tmp_path):
    fork, friture_source = stores
    write_values(friture_source, {"AudioBackend/deviceName": "Original input"})
    initialize_settings(fork, friture_source)
    fork.setValue("AudioBackend/deviceName", "Fork preference")
    fork.sync()
    before = snapshot(fork)
    unreadable = ini_settings(tmp_path / "unreadable.ini", UnreadableFritureSource)

    initialize_settings(fork, unreadable)

    assert snapshot(fork) == before


@pytest.mark.parametrize("theme", [1, "invalid"])
def test_existing_unversioned_fork_preferences_are_not_overwritten(stores, tmp_path, theme):
    fork, friture_source = stores
    write_values(fork, {"AudioBackend/deviceName": "Fork input", "themePreference": theme})
    write_values(friture_source, {"AudioBackend/deviceName": "Friture input", "other": "ignored"})
    unreadable = ini_settings(tmp_path / "unreadable.ini", UnreadableFritureSource)

    initialize_settings(fork, unreadable)

    assert fork.value("AudioBackend/deviceName") == "Fork input"
    assert fork.value("themePreference") == theme
    assert not fork.contains("other")
    assert_complete(fork, "existing")


def test_absent_friture_profile_is_finalized_once(stores):
    fork, friture_source = stores
    initialize_settings(fork, friture_source)
    assert_complete(fork, "absent")
    before = snapshot(fork)
    write_values(friture_source, {"AudioBackend/deviceName": "Appeared later"})

    initialize_settings(fork, friture_source)

    assert snapshot(fork) == before
    assert not fork.contains("AudioBackend/deviceName")


def test_import_accepts_float_sweep_frequencies_saved_by_friture(stores):
    fork, friture_source = stores
    values = {
        "Docks/dockNames": ["Dock 1"],
        "Docks/Dock 1/type": 5,
        "Docks/Dock 1/sweep start frequency": 20.5,
        "Docks/Dock 1/sweep stop frequency": 21999.5,
    }
    write_values(friture_source, values)

    initialize_settings(fork, friture_source)

    assert_complete(fork, "imported")
    expected = {**values, "Docks/dockNames": ["Meters", "Dock 1"], "Docks/Meters/type": 9}
    for key, value in expected.items():
        assert fork.value(key) == value


def test_first_schema_upgrade_moves_central_widget_and_removes_obsolete_level_dock(stores):
    fork, friture_source = stores
    write_values(friture_source, {
        "CentralWidget/type": 2,
        "CentralWidget/customNested/value": "central settings",
        "Docks/dockNames": ["Old levels", "Existing scope"],
        "Docks/Old levels/type": 0,
        "Docks/Old levels/obsolete": "discard",
        "Docks/Existing scope/type": 1,
    })
    before = snapshot(friture_source)

    initialize_settings(fork, friture_source)

    assert fork.value("Docks/dockNames") == ["Meters", "central", "Existing scope"]
    assert fork.value("Docks/central/type", type=int) == 2
    assert fork.value("Docks/central/customNested/value") == "central settings"
    assert not any(key.startswith("CentralWidget/") for key in fork.allKeys())
    assert not any(key.startswith("Docks/Old levels/") for key in fork.allKeys())
    assert snapshot(friture_source) == before
    assert_complete(fork, "imported")


def test_singleton_ini_layout_import_upgrades_before_normal_owner_restoration(tmp_path):
    source_path = tmp_path / "singleton-friture.ini"
    source_path.write_text(
        "[Docks]\n"
        "dockNames=Old levels\n"
        "Old%20levels\\type=0\n"
        "Old%20levels\\obsolete=discard\n"
        "[CentralWidget]\n"
        "type=2\n"
        "freqMin=123\n"
        "fftSize=invalid\n"
        "[extension]\n"
        "opaque=@ByteArray(retained)\n",
        encoding="utf-8",
    )
    source = ini_settings(source_path)
    fork = ini_settings(tmp_path / "fork.ini")
    assert source.value("Docks/dockNames") == "Old levels"
    before = snapshot(source)
    source_bytes = source_path.read_bytes()

    initialize_settings(fork, source)

    layout = DockLayoutSettings()
    fork.beginGroup("Docks")
    layout.restore(fork)
    fork.endGroup()
    assert layout.get("dockNames") == ["Meters", "central"]
    panel_type = DockSettings()
    spectrum = SpectrumSettings()
    fork.beginGroup("Docks/central")
    panel_type.restore(fork)
    spectrum.restore(fork)
    fork.endGroup()
    assert panel_type.get("type") == 2
    assert spectrum.get("freqMin") == 123
    assert spectrum.get("fftSize") == SpectrumSettings.fields["fftSize"].default
    assert not any(key.startswith("Docks/Old levels/") or key.startswith("CentralWidget/")
                   for key in fork.allKeys())
    assert fork.value("extension/opaque") == QByteArray(b"retained")
    assert snapshot(source) == before
    assert source_path.read_bytes() == source_bytes
    assert_complete(fork, "imported")


@pytest.mark.parametrize("existing_version", [None, 0, 1])
def test_retired_features_are_cleaned_for_imported_and_existing_profiles(stores, existing_version):
    fork, friture_source = stores
    values = {
        "AudioBackend/showPlayback": "invalid retired value",
        "AudioBackend/historyLength": 600,
        "AudioBackend/firstChannel": 3,
        "Docks/dockNames": ["Delay", "Spectrum", "Pitch"],
        "Docks/Delay/type": 6,
        "Docks/Delay/delay_range": 4.5,
        "Docks/Spectrum/type": 2,
        "Docks/Spectrum/fftSize": 9,
        "Docks/Pitch/type": 8,
        "Docks/widgetIdStack": [6, 2, 8],
        "Docks/lastSettings/6/delay_range": 4.5,
        "Docks/lastSettings/2/fftSize": 9,
        "extension/opaque": QByteArray(b"\x00\xffretained"),
    }
    if existing_version is None:
        write_values(friture_source, values)
    else:
        write_values(fork, values)
        if existing_version:
            write_values(fork, {SCHEMA_VERSION_KEY: existing_version,
                                FRITURE_IMPORT_STATE_KEY: "existing"})
    source_before = Path(friture_source.fileName()).read_bytes() if friture_source.allKeys() else None

    initialize_settings(fork, friture_source)

    assert fork.value("Docks/dockNames") == ["Meters", "Spectrum", "Pitch"]
    assert fork.value("Docks/widgetIdStack") == [2, 8]
    assert not fork.contains("AudioBackend/showPlayback")
    assert not fork.contains("AudioBackend/historyLength")
    assert not any(key.startswith(("Docks/Delay/", "Docks/lastSettings/6/"))
                   for key in fork.allKeys())
    assert fork.value("AudioBackend/firstChannel") == 3
    assert fork.value("Docks/Spectrum/fftSize") == 9
    assert fork.value("Docks/Pitch/type") == 8
    assert fork.value("Docks/lastSettings/2/fftSize") == 9
    assert fork.value("extension/opaque") == values["extension/opaque"]
    assert_complete(fork, "imported" if existing_version is None else "existing")
    initialized = snapshot(fork)
    initialize_settings(fork, friture_source)
    assert snapshot(fork) == initialized
    if source_before is not None:
        assert Path(friture_source.fileName()).read_bytes() == source_before


def test_first_schema_upgrade_does_not_replace_existing_central_dock(stores):
    fork, friture_source = stores
    write_values(friture_source, {
        "CentralWidget/type": 2,
        "CentralWidget/custom": "old",
        "Docks/dockNames": ["central"],
        "Docks/central/type": 1,
        "Docks/central/custom": "keep",
    })

    initialize_settings(fork, friture_source)

    assert fork.value("Docks/dockNames") == ["Meters", "central"]
    assert fork.value("Docks/central/type", type=int) == 1
    assert fork.value("Docks/central/custom") == "keep"
    assert not fork.contains("CentralWidget/type")


def test_former_empty_layout_retains_only_the_previously_permanent_meters(stores):
    fork, friture_source = stores
    write_values(friture_source, {"Docks/dockNames": None, "Docks/widgetIdStack": None})

    initialize_settings(fork, friture_source)

    assert fork.contains("Docks/dockNames")
    assert fork.value("Docks/dockNames") == ["Meters"]
    assert fork.value("Docks/Meters/type") == 9
    assert fork.value("Docks/widgetIdStack") in (None, [])
    assert_complete(fork, "imported")


@pytest.mark.parametrize("existing_version", [None, 0, 1, 2])
def test_meter_panel_upgrade_runs_once_for_imported_and_existing_layouts(stores, existing_version):
    fork, source = stores
    values = {"Docks/dockNames": ["Scope", "Spectrum"], "Docks/Scope/type": 1,
              "Docks/Spectrum/type": 2, "Docks/Scope/custom": QByteArray(b"retained")}
    if existing_version is None:
        write_values(source, values)
    else:
        write_values(fork, {**values, SCHEMA_VERSION_KEY: existing_version,
                            FRITURE_IMPORT_STATE_KEY: "existing"})
    source_before = snapshot(source)

    initialize_settings(fork, source)

    assert fork.value("Docks/dockNames") == ["Meters", "Scope", "Spectrum"]
    assert fork.value("Docks/Meters/type") == 9
    assert fork.value("Docks/Scope/custom") == QByteArray(b"retained")
    assert_complete(fork, "imported" if existing_version is None else "existing")
    assert snapshot(source) == source_before
    # The new ordinary panel can be closed permanently after the one upgrade.
    fork.setValue("Docks/dockNames", ["Scope", "Spectrum"])
    fork.sync()
    initialize_settings(fork, source)
    assert fork.value("Docks/dockNames") == ["Scope", "Spectrum"]


@pytest.mark.parametrize("owner_type,group,values,recovered,preserved", [
    (ThemeSettings, "", {"themePreference": "invalid"},
     ["themePreference"], {}),
    (GlobalSettings, "AudioBackend", {"AudioBackend/themePreference": 99,
                                      "AudioBackend/firstChannel": 7},
     ["themePreference"], {"firstChannel": 7, "deviceName": "Retained input"}),
    (SpectrumSettings, "Docks/central", {"CentralWidget/type": 2,
                                        "CentralWidget/fftSize": "invalid",
                                        "CentralWidget/freqMin": 123},
     ["fftSize"], {"freqMin": 123}),
    (SweepSettings, "Docks/Sweep", {"Docks/dockNames": ["Sweep"], "Docks/Sweep/type": 5,
                                    "Docks/Sweep/sweep start frequency": 100.,
                                    "Docks/Sweep/sweep stop frequency": 100.,
                                    "Docks/Sweep/sweep period": 2.5},
     ["sweep start frequency", "sweep stop frequency"], {"sweep period": 2.5}),
    (DockLayoutSettings, "Docks", {"Docks/dockNames": ["bad/name"],
                                   "Docks/widgetIdStack": [2, 1]},
     ["dockNames"], {"widgetIdStack": [2, 1]}),
    (DockSettings, "Docks/Scope", {"Docks/dockNames": ["Scope"],
                                   "Docks/Scope/type": "invalid"},
     ["type"], {}),
])
def test_import_and_existing_profiles_share_owner_recovery_after_schema_upgrade(
        stores, tmp_path, owner_type, group, values, recovered, preserved):
    fork, friture_source = stores
    values = {"AudioBackend/deviceName": "Retained input",
              "extension/opaque": QByteArray(b"\x00\xfffuture"), **values}
    write_values(friture_source, values)
    source_before = snapshot(friture_source)
    source_bytes = Path(friture_source.fileName()).read_bytes()
    own_profile = ini_settings(tmp_path / "existing.ini")
    write_values(own_profile, values)
    unreadable = ini_settings(tmp_path / "unreadable.ini", UnreadableFritureSource)

    initialize_settings(fork, friture_source)
    initialize_settings(own_profile, unreadable)

    normalized = []
    for settings in (fork, own_profile):
        before_restore = snapshot(settings)
        owner = owner_type()
        settings.beginGroup(group)
        try:
            owner.restore(settings)
        finally:
            settings.endGroup()
        normalized.append({key: owner.get(key) for key in owner.fields})
        for key in recovered:
            assert owner.get(key) == owner.fields[key].default
        for key, expected in preserved.items():
            assert owner.get(key) == expected
        assert snapshot(settings) == before_restore
        assert settings.value("AudioBackend/deviceName") == "Retained input"
        assert settings.value("extension/opaque") == QByteArray(b"\x00\xfffuture")
        assert isinstance(settings.value("extension/opaque"), QByteArray)
    assert normalized[0] == normalized[1]
    if group == "Docks/central":
        assert not fork.contains("CentralWidget/type")
        assert fork.value("Docks/central/type") == 2
    assert snapshot(friture_source) == source_before
    assert Path(friture_source.fileName()).read_bytes() == source_bytes
    assert_complete(fork, "imported")
    assert_complete(own_profile, "existing")


@pytest.mark.parametrize("phase", ["journal", "payload", "markers"])
def test_failed_flush_resumes_original_snapshot_before_reading_changed_friture_profile(tmp_path, phase):
    fork_path = tmp_path / "fork.ini"
    fork = ini_settings(fork_path, FailCheckpointOnce)
    fork.failure_phase = phase
    friture_source = ini_settings(tmp_path / "friture.ini")
    write_values(friture_source, {"AudioBackend/deviceName": "Original input", "themePreference": 1})

    with pytest.raises(SettingsInitializationError):
        initialize_settings(fork, friture_source)

    assert fork.failed, "The intended checkpoint must actually be exercised"
    assert fork.contains(INITIALIZATION_JOURNAL_KEY)
    if phase == "journal":
        assert not fork.contains("AudioBackend/deviceName")
    if phase != "markers":
        assert not fork.contains(SCHEMA_VERSION_KEY)
        assert not fork.contains(FRITURE_IMPORT_STATE_KEY)
    write_values(friture_source, {"AudioBackend/deviceName": "Changed input", "themePreference": 2})
    resumed = ini_settings(fork_path)
    unreadable = ini_settings(tmp_path / "unreadable.ini", UnreadableFritureSource)

    initialize_settings(resumed, unreadable)

    assert resumed.value("AudioBackend/deviceName") == "Original input"
    assert resumed.value("themePreference", type=int) == 1
    assert_complete(resumed, "imported")
    assert friture_source.value("AudioBackend/deviceName") == "Changed input"


def test_sync_exception_is_reported_as_initialization_error(stores):
    _, friture_source = stores

    class RaisingSettings(QSettings):
        def sync(self):
            raise OSError("simulated interrupted write")

    fork = ini_settings(friture_source.fileName() + ".fork", RaisingSettings)
    write_values(friture_source, {"AudioBackend/deviceName": "Input"})

    with pytest.raises(SettingsInitializationError):
        initialize_settings(fork, friture_source)

    assert not fork.contains(SCHEMA_VERSION_KEY)
    assert not fork.contains(FRITURE_IMPORT_STATE_KEY)


@pytest.mark.parametrize("status", [QSettings.Status.FormatError, QSettings.Status.AccessError])
def test_friture_source_errors_use_defaults_only_for_malformed_data(stores, tmp_path, status):
    fork, _ = stores

    class ErrorStatusSettings(QSettings):
        def status(self):
            return status

    friture_source = ini_settings(tmp_path / "unreadable-source.ini", ErrorStatusSettings)
    friture_source.setValue("AudioBackend/deviceName", "Must not import")

    if status == QSettings.Status.FormatError:
        initialize_settings(fork, friture_source)
        assert_complete(fork, "invalid")
    else:
        with pytest.raises(SettingsInitializationError):
            initialize_settings(fork, friture_source)
        assert not fork.contains(SCHEMA_VERSION_KEY)
        assert not fork.contains(FRITURE_IMPORT_STATE_KEY)
    assert not fork.contains("AudioBackend/deviceName")


def test_interruption_between_payload_keys_replays_entire_snapshot(tmp_path):
    class InterruptedSettings(QSettings):
        interrupted = False

        def setValue(self, key, value):
            super().setValue(key, value)
            if self.contains(INITIALIZATION_JOURNAL_KEY) and not key.startswith("Polyfriture/") and not self.interrupted:
                self.interrupted = True
                raise RuntimeError("simulated process interruption between payload keys")

    fork_path = tmp_path / "fork.ini"
    fork = ini_settings(fork_path, InterruptedSettings)
    friture_source = ini_settings(tmp_path / "friture.ini")
    write_values(friture_source, {"firstPreference": "first", "secondPreference": "second"})

    with pytest.raises(RuntimeError, match="simulated process interruption"):
        initialize_settings(fork, friture_source)

    assert fork.contains(INITIALIZATION_JOURNAL_KEY)
    assert fork.contains("firstPreference") != fork.contains("secondPreference")
    assert not fork.contains(SCHEMA_VERSION_KEY)
    fork.sync()
    friture_source.setValue("firstPreference", "changed later")
    friture_source.sync()
    resumed = ini_settings(fork_path)
    unreadable = ini_settings(tmp_path / "unreadable.ini", UnreadableFritureSource)

    initialize_settings(resumed, unreadable)

    assert resumed.value("firstPreference") == "first"
    assert resumed.value("secondPreference") == "second"
    assert_complete(resumed, "imported")


@pytest.mark.parametrize("journal", [
    "not a journal",
    {"schemaVersion": 1},
    {"values": {}, "remove": [], "schemaVersion": settings_schema.CURRENT_VERSION + 1,
     "upstreamImport": "imported"},
])
def test_corrupt_or_future_journal_is_rejected_without_mutation(stores, journal):
    fork, friture_source = stores
    write_values(fork, {INITIALIZATION_JOURNAL_KEY: journal, "custom": "preserve"})
    write_values(friture_source, {"AudioBackend/deviceName": "Do not import"})
    before = snapshot(fork)

    with pytest.raises(SettingsInitializationError):
        initialize_settings(fork, friture_source)

    assert snapshot(fork) == before
    assert not fork.contains(SCHEMA_VERSION_KEY)
    assert not fork.contains(FRITURE_IMPORT_STATE_KEY)


def test_future_schema_is_not_downgraded_or_changed(stores):
    fork, friture_source = stores
    write_values(fork, {SCHEMA_VERSION_KEY: settings_schema.CURRENT_VERSION + 1,
                        FRITURE_IMPORT_STATE_KEY: "imported", "custom": "preserve"})
    before = snapshot(fork)

    with pytest.raises(SettingsInitializationError):
        initialize_settings(fork, friture_source)

    assert snapshot(fork) == before


def test_subsequent_schema_upgrades_run_once_without_reimporting(stores, tmp_path, monkeypatch):
    fork, friture_source = stores
    write_values(friture_source, {"AudioBackend/deviceName": "Original input"})
    initialize_settings(fork, friture_source)
    calls = []

    def next_upgrade(values):
        calls.append(dict(values))
        values["NewFeature/setting"] = "upgraded"

    monkeypatch.setattr(settings_schema, "CURRENT_VERSION", settings_schema.CURRENT_VERSION + 1)
    monkeypatch.setattr(settings_schema, "UPGRADES", (*settings_schema.UPGRADES, next_upgrade))
    unreadable = ini_settings(tmp_path / "unreadable.ini", UnreadableFritureSource)

    initialize_settings(fork, unreadable)
    initialize_settings(fork, unreadable)

    assert len(calls) == 1
    assert fork.value("AudioBackend/deviceName") == "Original input"
    assert fork.value("NewFeature/setting") == "upgraded"
    assert fork.value(SCHEMA_VERSION_KEY, type=int) == settings_schema.CURRENT_VERSION
    assert fork.value(FRITURE_IMPORT_STATE_KEY) == "imported"
    assert not fork.contains(INITIALIZATION_JOURNAL_KEY)


def test_native_stores_import_qt_values_without_touching_application_namespaces(tmp_path):
    with native_stores(tmp_path) as (fork, friture_source):
        paths = [fork.fileName(), friture_source.fileName()]
        if not fork.isWritable() or not friture_source.isWritable():
            pytest.skip("Native-format settings are not writable in this environment")
        write_values(friture_source, {
            "MainWindow/windowGeometry": QByteArray(b"\x00\xfe\xff"),
            "Docks/dockNames": ["Dock 1"],
            "Docks/Dock 1/type": 1,
            "AudioBackend/firstChannel": 4,
        })
        before = snapshot(friture_source)

        initialize_settings(fork, friture_source)

        assert fork.value("MainWindow/windowGeometry") == QByteArray(b"\x00\xfe\xff")
        assert fork.value("Docks/dockNames") == ["Meters", "Dock 1"]
        assert fork.value("AudioBackend/firstChannel", type=int) == 4
        assert snapshot(friture_source) == before
        assert_complete(fork, "imported")
    assert_native_stores_removed(paths)


@pytest.mark.parametrize("interruption", [RuntimeError, pytest.skip.Exception])
def test_native_stores_are_removed_when_test_fails_or_skips(tmp_path, interruption):
    with pytest.raises(interruption):
        with native_stores(tmp_path) as settings_pair:
            paths = [settings.fileName() for settings in settings_pair]
            if not all(settings.isWritable() for settings in settings_pair):
                pytest.skip("Native-format settings are not writable in this environment")
            for settings in settings_pair:
                write_values(settings, {"nested/testValue": "temporary"})
            raise interruption("simulated test exit")
    assert_native_stores_removed(paths)


def use_windows_discovery(monkeypatch):
    from polyfriture import friture_settings_windows

    monkeypatch.setattr(settings_initialization, "read_friture_settings",
                        lambda source=None: friture_settings._read_windows())
    return friture_settings_windows


def test_absent_windows_sources_are_finalized_once(stores, monkeypatch):
    fork, _ = stores
    windows = use_windows_discovery(monkeypatch)
    monkeypatch.setattr(windows, "read_native_settings", lambda: {})
    monkeypatch.setattr(windows, "read_store_settings", lambda: {})
    initialize_settings(fork)
    assert_complete(fork, "absent")

    def unexpected_discovery(source=None):
        raise AssertionError("An absent import must not discover sources on later launches")

    monkeypatch.setattr(settings_initialization, "read_friture_settings", unexpected_discovery)
    initialize_settings(fork)
    assert_complete(fork, "absent")


def test_windows_import_falls_back_to_store_and_never_reimports(stores, monkeypatch):
    fork, _ = stores
    windows = use_windows_discovery(monkeypatch)
    values = {
        "themePreference": 2,
        "AudioBackend/firstChannel": 4,
        "Docks/dockNames": ["Dock 1"],
        "Docks/Dock 1/type": 1,
        "MainWindow/windowGeometry": QByteArray(b"\x00\xfe\xff"),
        "unknown/nested/value": "retained",
        SCHEMA_VERSION_KEY: 999,
    }
    monkeypatch.setattr(windows, "read_native_settings", lambda: {})
    monkeypatch.setattr(windows, "read_store_settings", lambda: values)

    initialize_settings(fork)

    for key, value in values.items():
        if key not in (SCHEMA_VERSION_KEY, "Docks/dockNames"):
            assert fork.value(key) == value
    assert fork.value("Docks/dockNames") == ["Meters", "Dock 1"]
    assert fork.value("Docks/Meters/type") == 9
    assert_complete(fork, "imported")
    before = snapshot(fork)

    def unexpected_discovery(source=None):
        raise AssertionError("A completed import must not discover Friture settings again")

    monkeypatch.setattr(settings_initialization, "read_friture_settings", unexpected_discovery)
    initialize_settings(fork)
    assert snapshot(fork) == before


@pytest.mark.parametrize("failing_reader", ["read_native_settings", "read_store_settings"])
def test_windows_read_errors_leave_import_unfinished_and_retryable(stores, monkeypatch, failing_reader):
    fork, _ = stores
    windows = use_windows_discovery(monkeypatch)
    monkeypatch.setattr(windows, "read_native_settings", lambda: {})
    monkeypatch.setattr(windows, "read_store_settings", lambda: {"themePreference": 2})

    def locked_source():
        raise PermissionError("Close Friture and its Registry Editor before retrying")

    with monkeypatch.context() as failure:
        failure.setattr(windows, failing_reader, locked_source)
        with pytest.raises(SettingsInitializationError, match="Close Friture"):
            initialize_settings(fork)

    assert not fork.contains(INITIALIZATION_JOURNAL_KEY)
    assert not fork.contains(SCHEMA_VERSION_KEY)
    assert not fork.contains(FRITURE_IMPORT_STATE_KEY)

    initialize_settings(fork)
    assert fork.value("themePreference", type=int) == 2
    assert_complete(fork, "imported")


@pytest.mark.parametrize("initial, expected_state", [
    ({"custom": "existing preference"}, "existing"),
    ({"custom": "completed preference", SCHEMA_VERSION_KEY: settings_schema.CURRENT_VERSION,
      FRITURE_IMPORT_STATE_KEY: "absent"}, "absent"),
    ({INITIALIZATION_JOURNAL_KEY: {"values": {"custom": "prepared preference"}, "remove": [],
                   "schemaVersion": settings_schema.CURRENT_VERSION, "upstreamImport": "imported"}}, "imported"),
])
def test_existing_completed_and_pending_stores_do_not_discover_sources(stores, monkeypatch,
                                                                     initial, expected_state):
    fork, _ = stores
    write_values(fork, initial)

    def unexpected_discovery(source=None):
        raise AssertionError("This store must not discover Friture settings")

    monkeypatch.setattr(settings_initialization, "read_friture_settings", unexpected_discovery)
    initialize_settings(fork)
    assert_complete(fork, expected_state)


def test_explicit_friture_source_is_passed_to_reader(stores, monkeypatch):
    fork, source = stores
    write_values(source, {"themePreference": 1})
    calls = []
    read_source = friture_settings.read_friture_settings

    def observe_reader(explicit_source=None):
        calls.append(explicit_source)
        return read_source(explicit_source)

    monkeypatch.setattr(settings_initialization, "read_friture_settings", observe_reader)
    initialize_settings(fork, friture_source=source)
    assert calls == [source]
    assert fork.value("themePreference", type=int) == 1
    assert_complete(fork, "imported")


def test_existing_completion_metadata_keeps_its_persisted_names(stores, monkeypatch):
    fork, _ = stores
    write_values(fork, {
        "Polyfriture/schemaVersion": settings_schema.CURRENT_VERSION,
        "Polyfriture/upstreamImport": "imported",
        "custom": "existing preference",
    })
    before = snapshot(fork)

    def unexpected_import(_source):
        raise AssertionError("A previously completed import must remain completed")

    monkeypatch.setattr(settings_initialization, "read_friture_settings", unexpected_import)
    initialize_settings(fork)

    assert snapshot(fork) == before


def test_existing_journal_keeps_its_persisted_format(stores, monkeypatch):
    fork, _ = stores
    write_values(fork, {
        "Polyfriture/pendingMigration": {
            "values": {"custom": "prepared preference",
                       "AudioBackend/historyLength": 600,
                       "Docks/lastSettings/6/delay_range": 4.5},
            "remove": [],
            "schemaVersion": 1,
            "upstreamImport": "imported",
        },
    })

    def unexpected_import(_source):
        raise AssertionError("A saved journal must finish without reading Friture again")

    monkeypatch.setattr(settings_initialization, "read_friture_settings", unexpected_import)
    initialize_settings(fork)

    assert fork.value("custom") == "prepared preference"
    assert not fork.contains("AudioBackend/historyLength")
    assert not fork.contains("Docks/lastSettings/6/delay_range")
    assert fork.value("Polyfriture/schemaVersion", type=int) == settings_schema.CURRENT_VERSION
    assert fork.value("Polyfriture/upstreamImport") == "imported"
    assert not fork.contains("Polyfriture/pendingMigration")
