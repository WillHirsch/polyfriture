"""Read Friture's Windows preferences for import into Polyfriture.

The Store keeps HKCU writes in a package-private registry hive. Read a disposable
copy in memory rather than mounting a key in the user's registry or opening the
original hive with an API that can recover its transaction logs.
"""

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import shutil
import stat
from tempfile import TemporaryDirectory
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QSettings


STORE_PACKAGE_FAMILY = "53504SilentGain.Friture_xkk28cz8e24m6"
_FRITURE_KEY = r"Software\Friture\Friture"


def _read_registry_tree(root: Any, path: str) -> dict[str, tuple[Any, int]]:
    """Return native values, opening only existing keys with read permission."""
    import winreg

    try:
        settings_key = winreg.OpenKey(root, path, 0, winreg.KEY_READ)
    except FileNotFoundError:
        return {}

    values: dict[str, tuple[Any, int]] = {}
    # Qt exchanges separators: a registry '/' represents a literal backslash in
    # a settings key, whereas registry subkeys become settings groups.
    separators = str.maketrans({"\\": "/", "/": "\\"})

    def visit(key: Any, prefix: str = "") -> None:
        child_count, value_count, _ = winreg.QueryInfoKey(key)
        for index in range(value_count):
            name, value, value_type = winreg.EnumValue(key, index)
            settings_name = (prefix + (name or ".")).translate(separators)
            values[settings_name] = value, value_type
        for index in range(child_count):
            name = winreg.EnumKey(key, index)
            with winreg.OpenKey(key, name, 0, winreg.KEY_READ) as child:
                visit(child, prefix + name + "\\")

    with settings_key:
        visit(settings_key)
    return values


def _ini_string(value: str) -> str:
    # Escape UTF-16 code units individually. This preserves arbitrary Qt binary
    # payloads as well as quotes, separators, newlines and non-ASCII text.
    encoded = value.encode("utf-16-le", errors="surrogatepass")
    return '"' + "".join(
        f"\\x{int.from_bytes(encoded[index:index + 2], 'little'):04x}"
        for index in range(0, len(encoded), 2)
    ) + '"'


def _decode_registry_values(raw: dict[str, tuple[Any, int]]) -> dict[str, Any]:
    """Use Qt's own serializer for native @ByteArray/@Variant encodings."""
    import winreg

    if not raw:
        return {}
    values: dict[str, Any] = {}
    encoded_strings: list[str] = []
    string_keys: dict[str, list[int]] = {}
    list_keys: set[str] = set()
    for key, (value, value_type) in raw.items():
        if value_type in (winreg.REG_DWORD, winreg.REG_QWORD):
            bits = 32 if value_type == winreg.REG_DWORD else 64
            # Qt reads these native types as signed integers.
            values[key] = value if value < 1 << (bits - 1) else value - (1 << bits)
            continue
        if value_type == winreg.REG_MULTI_SZ:
            strings = value
            list_keys.add(key)
        elif value_type in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
            strings = [value]
        elif value_type in (winreg.REG_BINARY, winreg.REG_NONE):
            # Qt stores serialized variants as UTF-16 text even for REG_BINARY.
            strings = [value[:len(value) // 2 * 2].decode("utf-16-le", errors="surrogatepass")]
        else:
            # QSettings also returns an invalid QVariant for unsupported types.
            values[key] = None
            continue
        string_keys[key] = []
        for string in strings:
            string_keys[key].append(len(encoded_strings))
            encoded_strings.append(string)

    if encoded_strings:
        with TemporaryDirectory(prefix="polyfriture-settings-") as temporary:
            ini_path = Path(temporary) / "values.ini"
            ini_path.write_text(
                "[General]\n" + "".join(
                    f"v{index}={_ini_string(value)}\n"
                    for index, value in enumerate(encoded_strings)
                ),
                encoding="ascii",
            )
            settings = QSettings(str(ini_path), QSettings.Format.IniFormat)
            settings.setFallbacksEnabled(False)
            try:
                decoded = [settings.value(f"v{index}") for index in range(len(encoded_strings))]
                if settings.status() != QSettings.Status.NoError:
                    raise OSError("Cannot decode Friture's registry settings")
            finally:
                sip.delete(settings)
        for key, indices in string_keys.items():
            items = [decoded[index] for index in indices]
            values[key] = items if key in list_keys else items[0]
    # Empty REG_MULTI_SZ values have no encoded string entries.
    for key in list_keys - values.keys():
        values[key] = []
    return values


def read_native_settings() -> dict[str, Any]:
    """Read the ordinary current-user store without creating an absent key."""
    import winreg

    # HKCU\Software\Friture is shared between 32- and 64-bit registry views.
    return _decode_registry_values(_read_registry_tree(winreg.HKEY_CURRENT_USER, _FRITURE_KEY))


def _offline_registry_api() -> Any:
    """Load only Windows' system copy; expose no hive-writing operations."""
    try:
        api = ctypes.WinDLL("offreg.dll", winmode=0x800)  # LOAD_LIBRARY_SEARCH_SYSTEM32
    except OSError as error:
        raise OSError(
            "Cannot read Friture's Store settings: Windows' Offline Registry library "
            "(offreg.dll) is unavailable. Repair the Windows component and retry."
        ) from error
    handle = wintypes.HANDLE
    dword_pointer = ctypes.POINTER(wintypes.DWORD)
    signatures = {
        "OROpenHive": (wintypes.LPCWSTR, ctypes.POINTER(handle)),
        "ORCloseHive": (handle,),
        "OROpenKey": (handle, wintypes.LPCWSTR, ctypes.POINTER(handle)),
        "ORCloseKey": (handle,),
        "OREnumKey": (
            handle, wintypes.DWORD, wintypes.LPWSTR, dword_pointer,
            wintypes.LPWSTR, dword_pointer, ctypes.POINTER(wintypes.FILETIME),
        ),
        "OREnumValue": (
            handle, wintypes.DWORD, wintypes.LPWSTR, dword_pointer,
            dword_pointer, ctypes.c_void_p, dword_pointer,
        ),
    }
    for name, parameters in signatures.items():
        function = getattr(api, name)
        function.argtypes = parameters
        function.restype = wintypes.DWORD
    return api


def _offline_value(data: bytes, value_type: int) -> Any:
    import winreg

    if value_type in (winreg.REG_SZ, winreg.REG_EXPAND_SZ, winreg.REG_MULTI_SZ):
        text = data[:len(data) // 2 * 2].decode("utf-16-le", errors="surrogatepass")
        parts = text.split("\0")
        if value_type == winreg.REG_MULTI_SZ:
            return parts[:parts.index("")] if "" in parts else parts
        return parts[0]
    if value_type in (winreg.REG_DWORD, winreg.REG_QWORD):
        return int.from_bytes(data, "little")
    return data


def _ensure_clean_hive(path: Path) -> None:
    # Offline Registry validates but does not recover transaction logs. Unequal
    # base-block sequence numbers mean the hive needs recovery; do not import a
    # potentially stale on-disk snapshot instead of the last saved preferences.
    with path.open("rb") as hive:
        header = hive.read(12)
    if len(header) != 12 or header[:4] != b"regf":
        raise OSError("Friture's Store settings are not a valid registry hive")
    if header[4:8] != header[8:12]:
        raise OSError(
            "Friture's Store settings have an unfinished registry transaction. "
            "Open and close Friture normally, close any Registry Editor opened "
            "in its package context, then retry."
        )


def _read_offline_registry_tree(path: Path) -> dict[str, tuple[Any, int]]:
    """Read Store differencing hives, which RegLoadAppKey cannot load alone."""
    api = _offline_registry_api()
    root = wintypes.HANDLE()
    error = api.OROpenHive(str(path), ctypes.byref(root))
    if error:
        raise ctypes.WinError(error)
    values: dict[str, tuple[Any, int]] = {}
    separators = str.maketrans({"\\": "/", "/": "\\"})

    def visit(key: Any, prefix: str = "") -> None:
        index = 0
        while True:
            # The documented limits are 16,383 characters for value names and
            # 255 for subkey names. Payload buffers use the queried actual size.
            name = ctypes.create_unicode_buffer(16384)
            name_size = wintypes.DWORD(len(name))
            value_type = wintypes.DWORD()
            data_size = wintypes.DWORD()
            error = api.OREnumValue(
                key, index, name, ctypes.byref(name_size), ctypes.byref(value_type),
                None, ctypes.byref(data_size),
            )
            if error == 259:  # ERROR_NO_MORE_ITEMS
                break
            if error not in (0, 234):  # ERROR_MORE_DATA reports the required payload size.
                raise ctypes.WinError(error)
            data = ctypes.create_string_buffer(max(1, data_size.value))
            name_size.value = len(name)
            error = api.OREnumValue(
                key, index, name, ctypes.byref(name_size), ctypes.byref(value_type),
                data, ctypes.byref(data_size),
            )
            if error:
                raise ctypes.WinError(error)
            settings_name = (prefix + (name.value or ".")).translate(separators)
            values[settings_name] = _offline_value(data.raw[:data_size.value], value_type.value), value_type.value
            index += 1

        index = 0
        while True:
            name = ctypes.create_unicode_buffer(256)
            name_size = wintypes.DWORD(len(name))
            error = api.OREnumKey(key, index, name, ctypes.byref(name_size), None, None, None)
            if error == 259:
                break
            if error:
                raise ctypes.WinError(error)
            child = wintypes.HANDLE()
            error = api.OROpenKey(key, name.value, ctypes.byref(child))
            if error:
                raise ctypes.WinError(error)
            try:
                visit(child, prefix + name.value + "\\")
            finally:
                api.ORCloseKey(child)
            index += 1

    try:
        settings_key = wintypes.HANDLE()
        error = api.OROpenKey(root, _FRITURE_KEY, ctypes.byref(settings_key))
        if error == 2:  # ERROR_FILE_NOT_FOUND
            return {}
        if error:
            raise ctypes.WinError(error)
        try:
            visit(settings_key)
        finally:
            api.ORCloseKey(settings_key)
    finally:
        api.ORCloseHive(root)
    return values


def read_store_settings(local_app_data: Path | None = None) -> dict[str, Any]:
    """Read a disposable snapshot of the official Microsoft Store installation.

    An absent installation returns an empty snapshot. An existing unreadable or
    corrupt hive raises OSError so first launch can retry without recording an
    irreversible 'absent' import. Friture and package-context Registry Editors
    must be closed while the snapshot is copied.
    """
    if local_app_data is None:
        location = os.environ.get("LOCALAPPDATA")
        if not location:
            return {}
        local_app_data = Path(location)
    source = local_app_data / "Packages" / STORE_PACKAGE_FAMILY / "SystemAppData" / "Helium" / "User.dat"
    try:
        source_stat = source.stat()
    except FileNotFoundError:
        return {}
    if not stat.S_ISREG(source_stat.st_mode):
        raise OSError(f"Friture's Store settings hive is not a file: {source}")

    try:
        with TemporaryDirectory(prefix="polyfriture-store-") as temporary:
            copy = Path(temporary) / source.name
            shutil.copyfile(source, copy)
            after_copy = source.stat()
            if (source_stat.st_size, source_stat.st_mtime_ns) != (after_copy.st_size, after_copy.st_mtime_ns):
                raise OSError("Friture's Store settings changed while being copied; close Friture and retry")
            _ensure_clean_hive(copy)
            raw = _read_offline_registry_tree(copy)
            return _decode_registry_values(raw)
    except OSError as error:
        if isinstance(error, PermissionError) or getattr(error, "winerror", None) == 32:
            raise OSError(
                "Cannot access Friture's Store settings. Close Friture and any Registry Editor "
                "opened in its package context, then retry. If access is still denied, check "
                "the hive file's read permissions."
            ) from error
        raise
