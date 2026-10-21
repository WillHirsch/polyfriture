"""Read Windows Friture settings without modifying installed applications.

Private application hives live entirely in pytest's temporary directory. Tests
never create keys in HKCU or inspect the current user's application settings.
"""

from contextlib import contextmanager
import sys
import tempfile

import pytest
from PyQt6.QtCore import QByteArray, QDataStream, QIODevice, QPoint

from polyfriture import friture_settings_windows


pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows registry API")


@contextmanager
def writable_private_hive(path):
    import ctypes
    from ctypes import wintypes
    import winreg

    load = ctypes.WinDLL("advapi32", use_last_error=True).RegLoadAppKeyW
    load.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.HKEY),
                     wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
    load.restype = wintypes.LONG
    handle = wintypes.HKEY()
    result = load(str(path), ctypes.byref(handle), winreg.KEY_ALL_ACCESS, 1, 0)
    if result:
        raise ctypes.WinError(result)
    try:
        yield handle.value
        winreg.FlushKey(handle.value)
    finally:
        winreg.CloseKey(handle.value)


@pytest.fixture
def store_hive(tmp_path):
    """Build a Store-shaped hive, without administrator privileges or HKCU keys."""
    local_app_data = tmp_path / "Local"
    hive_path = (local_app_data / "Packages" / friture_settings_windows.STORE_PACKAGE_FAMILY
                 / "SystemAppData" / "Helium" / "User.dat")
    hive_path.parent.mkdir(parents=True)

    def populate(values, registry_path=r"Software\Friture\Friture"):
        import winreg

        with writable_private_hive(hive_path) as root:
            for key, (value_type, value) in values.items():
                group, _, name = key.rpartition("/")
                group_path = registry_path + ("\\" + group.replace("/", "\\") if group else "")
                with winreg.CreateKeyEx(root, group_path, 0, winreg.KEY_WRITE) as destination:
                    winreg.SetValueEx(destination, name, 0, value_type, value)
        return local_app_data, hive_path

    return populate


def source_snapshot(directory):
    return {
        path.relative_to(directory): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in directory.rglob("*") if path.is_file()
    }


def test_store_hive_preserves_qt_values_and_all_source_files(store_hive, tmp_path, monkeypatch):
    import winreg

    variant = QByteArray()
    stream = QDataStream(variant, QIODevice.OpenModeFlag.WriteOnly)
    stream.setVersion(QDataStream.Version.Qt_4_0)
    stream.writeQVariant({"answer": 42, "enabled": True})
    serialized_variant = "@Variant(" + bytes(variant).decode("latin1") + ")"
    local_app_data, hive_path = store_hive({
        "AudioBackend/deviceName": (winreg.REG_SZ, "Mikrofon — 音声"),
        "AudioBackend/duoInput": (winreg.REG_DWORD, 0xFFFFFFFD),
        "Docks/dockNames": (winreg.REG_MULTI_SZ, ["Dock 2", "Dock 7"]),
        "Docks/Dock 2/type": (winreg.REG_DWORD, 5),
        "Docks/Dock 2/sweep start frequency": (winreg.REG_SZ, "20.5"),
        "MainWindow/windowGeometry": (winreg.REG_BINARY,
                                    "@ByteArray(\x00\xfe\xffgeometry)".encode("utf-16-le")),
        "customPoint": (winreg.REG_SZ, "@Point(4 5)"),
        "customString": (winreg.REG_BINARY, "@String(before\x00after)".encode("utf-16-le")),
        "literalAtSign": (winreg.REG_SZ, "@@ByteArray(literal)"),
        "emptyList": (winreg.REG_MULTI_SZ, []),
        "negativeQword": (winreg.REG_QWORD, 0xFFFFFFFFFFFFFFF7),
        "customVariant": (winreg.REG_BINARY, serialized_variant.encode("utf-16-le")),
    })
    scratch = tmp_path / "reader-temporary-files"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    before = source_snapshot(hive_path.parent)

    values = friture_settings_windows.read_store_settings(local_app_data)

    assert values == {
        "AudioBackend/deviceName": "Mikrofon — 音声",
        "AudioBackend/duoInput": -3,
        "Docks/dockNames": ["Dock 2", "Dock 7"],
        "Docks/Dock 2/type": 5,
        "Docks/Dock 2/sweep start frequency": "20.5",
        "MainWindow/windowGeometry": QByteArray(b"\x00\xfe\xffgeometry"),
        "customPoint": QPoint(4, 5),
        "customString": "before\x00after",
        "literalAtSign": "@ByteArray(literal)",
        "emptyList": [],
        "negativeQword": -9,
        "customVariant": {"answer": 42, "enabled": True},
    }
    assert source_snapshot(hive_path.parent) == before
    assert list(scratch.iterdir()) == []


def test_store_hive_without_friture_preferences_is_absent(store_hive):
    import winreg

    local_app_data, hive_path = store_hive(
        {"unrelated": (winreg.REG_SZ, "not Friture settings")}, r"Software\AnotherApplication"
    )
    before = source_snapshot(hive_path.parent)

    assert friture_settings_windows.read_store_settings(local_app_data) == {}

    assert source_snapshot(hive_path.parent) == before


def test_missing_store_installation_does_not_create_files(tmp_path):
    local_app_data = tmp_path / "not-created"

    assert friture_settings_windows.read_store_settings(local_app_data) == {}

    assert not local_app_data.exists()


def test_store_discovery_uses_local_app_data_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert friture_settings_windows.read_store_settings() == {}

    assert list(tmp_path.iterdir()) == []


def test_corrupt_existing_hive_is_an_error_and_cleans_temporary_files(tmp_path, monkeypatch):
    hive_path = (tmp_path / "Packages" / friture_settings_windows.STORE_PACKAGE_FAMILY
                 / "SystemAppData" / "Helium" / "User.dat")
    hive_path.parent.mkdir(parents=True)
    hive_path.write_bytes(b"not a registry hive")
    scratch = tmp_path / "reader-temporary-files"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    before = source_snapshot(hive_path.parent)

    with pytest.raises(OSError):
        friture_settings_windows.read_store_settings(tmp_path)

    assert source_snapshot(hive_path.parent) == before
    assert list(scratch.iterdir()) == []


def test_locked_existing_hive_is_an_error(store_hive, tmp_path, monkeypatch):
    import ctypes
    from ctypes import wintypes
    import winreg

    local_app_data, hive_path = store_hive({"custom": (winreg.REG_SZ, "preserved")})
    before = source_snapshot(hive_path.parent)
    scratch = tmp_path / "reader-temporary-files"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_file = kernel32.CreateFileW
    open_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                          wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    open_file.restype = wintypes.HANDLE
    close_file = kernel32.CloseHandle
    close_file.argtypes = [wintypes.HANDLE]
    close_file.restype = wintypes.BOOL
    handle = open_file(str(hive_path), 0x80000000, 0, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        with pytest.raises(OSError, match="Close Friture"):
            friture_settings_windows.read_store_settings(local_app_data)
    finally:
        close_file(handle)
    assert source_snapshot(hive_path.parent) == before
    assert list(scratch.iterdir()) == []


def test_store_registry_names_follow_qsettings_conventions(store_hive):
    import winreg

    local_app_data, _ = store_hive({
        "": (winreg.REG_SZ, "unnamed root value"),
        "Nested/": (winreg.REG_SZ, "unnamed nested value"),
        "left/right": (winreg.REG_SZ, "nested"),
        "back\\slash": (winreg.REG_SZ, "literal backslash"),
    })

    assert friture_settings_windows.read_store_settings(local_app_data) == {
        ".": "unnamed root value",
        "Nested/.": "unnamed nested value",
        "left/right": "nested",
        "back/slash": "literal backslash",
    }


def test_native_reader_uses_read_only_qt_decoding_without_creating_settings(monkeypatch):
    import winreg

    calls = []

    def native_values(root, path):
        calls.append((root, path))
        return {
            "MainWindow/windowGeometry": (
                "@ByteArray(\x00\xfe\xff)".encode("utf-16-le"), winreg.REG_BINARY
            ),
            "Docks/dockNames": (["Dock 1"], winreg.REG_MULTI_SZ),
            "AudioBackend/duoInput": (0xFFFFFFFD, winreg.REG_DWORD),
        }

    monkeypatch.setattr(friture_settings_windows, "_read_registry_tree", native_values)

    assert friture_settings_windows.read_native_settings() == {
        "MainWindow/windowGeometry": QByteArray(b"\x00\xfe\xff"),
        "Docks/dockNames": ["Dock 1"],
        "AudioBackend/duoInput": -3,
    }
    assert calls == [(winreg.HKEY_CURRENT_USER, r"Software\Friture\Friture")]


def test_store_reader_uses_system_offline_registry_without_loading_a_live_hive(store_hive, monkeypatch):
    import ctypes
    import winreg

    local_app_data, _ = store_hive({"custom": (winreg.REG_SZ, "from the private hive")})
    original_load = ctypes.WinDLL
    loaded_libraries = []

    def load_offline_reader(name, *args, **kwargs):
        # A kernel hive load cannot handle a Store differencing hive. It can
        # also recover logs on disk; only the in-memory Offline Registry reader
        # should be used, loaded from Windows' protected system directory.
        assert name == "offreg.dll"
        assert kwargs.get("winmode") == 0x800  # LOAD_LIBRARY_SEARCH_SYSTEM32
        loaded_libraries.append(name)
        return original_load(name, *args, **kwargs)

    monkeypatch.setattr(ctypes, "WinDLL", load_offline_reader)

    assert friture_settings_windows.read_store_settings(local_app_data) == {"custom": "from the private hive"}
    assert loaded_libraries == ["offreg.dll"]


def test_dirty_hive_requires_recovery_without_touching_source_or_leaving_temporary_files(
        tmp_path, monkeypatch):
    hive_path = (tmp_path / "Packages" / friture_settings_windows.STORE_PACKAGE_FAMILY
                 / "SystemAppData" / "Helium" / "User.dat")
    hive_path.parent.mkdir(parents=True)
    # Only the header is needed: different sequence numbers must be rejected
    # before the offline reader can inspect an unrecovered snapshot.
    hive_path.write_bytes(b"regf" + (1).to_bytes(4, "little") + (2).to_bytes(4, "little"))
    scratch = tmp_path / "reader-temporary-files"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    before = source_snapshot(hive_path.parent)

    def unexpected_offline_read():
        raise AssertionError("An unrecovered hive must not reach the offline reader")

    monkeypatch.setattr(friture_settings_windows, "_offline_registry_api", unexpected_offline_read)

    with pytest.raises(OSError, match="Open and close Friture normally"):
        friture_settings_windows.read_store_settings(tmp_path)

    assert source_snapshot(hive_path.parent) == before
    assert list(scratch.iterdir()) == []
