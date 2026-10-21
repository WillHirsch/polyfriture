"""Shared assignment rules, atomic publication, and saved-profile recovery."""

from typing import Any, Mapping
from enum import Enum

import pytest
from PyQt6.QtCore import QByteArray, QSettings
from PyQt6.QtGui import QIntValidator

from polyfriture.settings_model import (
    BoolSetting, ChoiceSetting, EnumSetting, FloatSetting, IntSetting,
    ValueSetting, SettingsModel, SettingsValueError,
)


class ExampleSettings(SettingsModel):
    fields = {
        "gain": FloatSetting(0.0, minimum=-20, maximum=20),
        "mode": ChoiceSetting(0, labels=("Linear", "Logarithmic")),
        "enabled": BoolSetting(True),
    }


@pytest.mark.parametrize("key,value,expected", [
    ("gain", "1.25", 1.25), ("gain", -20, -20.0),
    ("mode", "1", 1), ("enabled", "false", False),
])
def test_runtime_and_saved_values_share_decoding_and_validation(tmp_path, key, value, expected):
    runtime = ExampleSettings()
    runtime.set(key, value)
    settings = QSettings(str(tmp_path / "profile.ini"), QSettings.Format.IniFormat)
    settings.setValue(key, value)
    restored = ExampleSettings()
    assert restored.restore(settings) == frozenset()
    assert runtime.get(key) == restored.get(key) == expected


@pytest.mark.parametrize("key,value", [
    ("gain", float("nan")), ("gain", float("inf")), ("gain", True),
    ("gain", 21), ("mode", -1), ("mode", 2), ("mode", 0.5),
    ("mode", True), ("mode", 2**40), ("enabled", "invalid"),
])
def test_invalid_update_does_not_publish_partial_changes(key, value):
    model = ExampleSettings()
    before = {name: model.get(name) for name in model.fields}
    with pytest.raises(SettingsValueError):
        model.update({"enabled": False, key: value})
    assert {name: model.get(name) for name in model.fields} == before


def test_restore_recovers_one_field_and_preserves_neighbor_and_unknown_qt_values(tmp_path, caplog):
    settings = QSettings(str(tmp_path / "profile.ini"), QSettings.Format.IniFormat)
    settings.setValue("gain", "broken")
    settings.setValue("mode", 1)
    settings.setValue("extension/geometry", QByteArray(b"\0\xffunknown"))
    settings.sync()
    original = {key: settings.value(key) for key in settings.allKeys()}
    model = ExampleSettings()
    assert model.restore(settings) == frozenset({"gain"})
    assert model.get("gain") == 0.0
    assert model.get("mode") == 1
    assert {key: settings.value(key) for key in settings.allKeys()} == original
    model.save(settings)
    assert settings.value("extension/geometry") == original["extension/geometry"]
    assert "gain" in caplog.text


class RelatedSettings(SettingsModel):
    fields = {
        "lower": IntSetting(1), "upper": IntSetting(2),
        "neighbor": ValueSetting("default"),
    }

    def validate(self, values: Mapping[str, Any]) -> None:
        if values["lower"] >= values["upper"]:
            raise SettingsValueError("lower must precede upper", keys=("lower", "upper"))


def test_related_values_can_be_assigned_as_one_candidate():
    model = RelatedSettings()
    with pytest.raises(SettingsValueError):
        model.set("lower", 3)
    assert model.get("lower") == 1
    model.update({"lower": 3, "upper": 4})
    assert (model.get("lower"), model.get("upper")) == (3, 4)


def test_saved_related_values_recover_only_the_dependent_group(tmp_path):
    settings = QSettings(str(tmp_path / "profile.ini"), QSettings.Format.IniFormat)
    for key, value in {"lower": 8, "upper": 4, "neighbor": "retained"}.items():
        settings.setValue(key, value)
    model = RelatedSettings()
    assert model.restore(settings) == frozenset({"lower", "upper"})
    assert model.get("lower") == 1
    assert model.get("upper") == 2
    assert model.get("neighbor") == "retained"


def test_restore_reports_field_and_dependent_group_recovery_together(tmp_path):
    settings = QSettings(str(tmp_path / "profile.ini"), QSettings.Format.IniFormat)
    for key, value in {"lower": 8, "upper": 4, "neighbor": ["invalid"]}.items():
        settings.setValue(key, value)
    model = RelatedSettings()
    assert model.restore(settings) == frozenset({"lower", "upper", "neighbor"})
    assert model.get("neighbor") == "default"


def test_missing_fields_use_defaults_without_reporting_recovery(tmp_path):
    settings = QSettings(str(tmp_path / "profile.ini"), QSettings.Format.IniFormat)
    model = ExampleSettings()
    assert model.restore(settings) == frozenset()
    assert settings.allKeys() == []


def test_mutable_defaults_and_reads_cannot_bypass_validation():
    class ListSettings(SettingsModel):
        fields = {"items": ValueSetting([])}
    one, two = ListSettings(), ListSettings()
    one.get("items").append("outside")
    assert one.get("items") == two.get("items") == []


def test_integer_limits_follow_qt_and_reject_both_overflows():
    qt = QIntValidator()
    field = IntSetting(0)
    assert (field.minimum, field.maximum) == (qt.bottom(), qt.top())
    for value in (qt.bottom(), qt.top()):
        assert field.coerce(str(value)) == value
    for value in (qt.bottom() - 1, qt.top() + 1):
        with pytest.raises(SettingsValueError):
            field.coerce(value)


def test_integer_definition_cannot_exceed_qt_limits():
    qt = QIntValidator()
    with pytest.raises(ValueError, match="bounds"):
        IntSetting(0, minimum=qt.bottom() - 1)
    with pytest.raises(ValueError, match="bounds"):
        IntSetting(0, maximum=qt.top() + 1)


def test_enum_values_are_members_rather_than_positions():
    class SparseEnum(Enum):
        FIRST = -2
        SECOND = 7
    field = EnumSetting(SparseEnum.FIRST)
    assert field.default == SparseEnum.FIRST.value
    assert field.values == (-2, 7)
    assert field.coerce(SparseEnum.SECOND) == field.coerce("7") == 7
    with pytest.raises(SettingsValueError):
        field.coerce(1)


@pytest.mark.parametrize("field,value", [
    (ValueSetting(""), 42),
    (ValueSetting(QByteArray()), b"not a Qt byte array"),
    (ValueSetting([]), "not a list"),
])
def test_plain_values_keep_the_default_type_contract(field, value):
    with pytest.raises(SettingsValueError):
        field.coerce(value)
