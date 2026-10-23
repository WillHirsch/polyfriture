"""Pure settings schema upgrades, independent of settings stores and import."""

import pytest
from PyQt6.QtCore import QByteArray

from polyfriture import settings_schema


def test_unversioned_layout_is_upgraded_and_unknown_qt_values_are_preserved():
    geometry = QByteArray(b"\x00\xffgeometry")
    values = {
        "AudioBackend/deviceName": "Input",
        "Docks/widgetIdStack": None,
        "Docks/dockNames": ["Old levels", "Scope"],
        "Docks/Old levels/type": 0,
        "Docks/Old levels/obsolete": "discard",
        "Docks/Scope/type": 1,
        "CentralWidget/type": 2,
        "CentralWidget/customNested/value": "retained",
        "Unknown/QtValue": geometry,
    }

    settings_schema.apply_upgrades(values, 0)

    assert values == {
        "AudioBackend/deviceName": "Input",
        "AudioBackend/duoInput": -2,
        "Docks/widgetIdStack": [],
        "Docks/dockNames": ["Meters", "central", "Scope"],
        "Docks/Meters/type": 9,
        "Docks/Scope/type": 1,
        "Docks/central/type": 2,
        "Docks/central/customNested/value": "retained",
        "Unknown/QtValue": geometry,
    }
    assert values["Unknown/QtValue"] is geometry
    upgraded = values.copy()
    settings_schema.apply_upgrades(values, 0)
    assert values == upgraded


@pytest.mark.parametrize("names", [42, ["duplicate", "duplicate"], ["bad/name"], [42]])
def test_malformed_existing_layout_is_preserved_without_source_validation(names):
    values = {
        "Docks/dockNames": names,
        "CentralWidget/type": "invalid",
        "Docks/Unknown/type": "invalid",
        "Unknown/value": "retained",
    }
    original = values.copy()

    settings_schema.apply_upgrades(values, 0)

    assert values == original


@pytest.mark.parametrize("widget_id,expected_names", [(0, []), (1, ["Panel"])])
def test_singleton_string_layout_is_upgraded_like_a_list(widget_id, expected_names):
    values = {"Docks/dockNames": "Panel", "Docks/Panel/type": widget_id}

    settings_schema.apply_upgrades(values, 0)

    assert values["Docks/dockNames"] == ["Meters", *expected_names]
    assert values["Docks/Meters/type"] == 9
    assert ("Docks/Panel/type" in values) == bool(expected_names)
    upgraded = values.copy()
    settings_schema.apply_upgrades(values, 0)
    assert values == upgraded


@pytest.mark.parametrize("widget_id", [False, 0.0, " 0", "invalid", 2**40])
def test_malformed_or_unknown_widget_ids_are_retained(widget_id):
    values = {
        "Docks/dockNames": ["Panel"],
        "Docks/Panel/type": widget_id,
        "Docks/Panel/custom": "retained",
    }
    original = values.copy()

    settings_schema.apply_upgrades(values, 0)

    assert values == {**original, "Docks/dockNames": ["Meters", "Panel"], "Docks/Meters/type": 9}


@pytest.mark.parametrize("widget_id", [0, "0", "+00", "-0"])
def test_obsolete_level_widget_integer_representations_are_removed(widget_id):
    values = {
        "Docks/dockNames": ["Panel"],
        "Docks/Panel/type": widget_id,
        "Docks/Panel/custom": "discard",
    }

    settings_schema.apply_upgrades(values, 0)

    assert values == {"Docks/dockNames": ["Meters"], "Docks/Meters/type": 9}


@pytest.mark.parametrize("from_version", [0, 1])
def test_feature_removals_upgrade_existing_and_imported_profiles(from_version):
    geometry = QByteArray(b"\x00\xffgeometry")
    values = {
        "AudioBackend/showPlayback": 2,
        "AudioBackend/historyLength": 600,
        "AudioBackend/deviceName": "Input",
        "AudioBackend/duoInput": -3,
        "Docks/dockNames": ["Delay", "Levels", "Pitch", "Spectrum"],
        "Docks/Delay/type": 6,
        "Docks/Delay/delay_range": 4.5,
        "Docks/Levels/type": 7,
        "Docks/Levels/history_length": 600,
        "Docks/Pitch/type": 8,
        "Docks/Pitch/freqMin": 80,
        "Docks/Spectrum/type": 2,
        "Docks/Spectrum/fftSize": 9,
        "Docks/widgetIdStack": [6, 7, "+006", "8", 2],
        "Docks/lastSettings/6/delay_range": 4.5,
        "Docks/lastSettings/7/history_length": 300,
        "Unknown/QtValue": geometry,
    }

    settings_schema.apply_upgrades(values, from_version)

    assert values == {
        "AudioBackend/deviceName": "Input",
        "AudioBackend/duoInput": -3,
        "Docks/dockNames": ["Meters", "Levels", "Pitch", "Spectrum"],
        "Docks/Meters/type": 9,
        "Docks/Levels/type": 7,
        "Docks/Levels/history_length": 600,
        "Docks/Pitch/type": 8,
        "Docks/Pitch/freqMin": 80,
        "Docks/Spectrum/type": 2,
        "Docks/Spectrum/fftSize": 9,
        "Docks/widgetIdStack": [7, "8", 2],
        "Docks/lastSettings/7/history_length": 300,
        "Unknown/QtValue": geometry,
    }
    assert values["Unknown/QtValue"] is geometry
    upgraded = values.copy()
    settings_schema.apply_upgrades(values, from_version)
    assert values == upgraded


@pytest.mark.parametrize("widget_id", [6, "6", "006", "+006", " 6 "])
@pytest.mark.parametrize("names", [["Delay"], "Delay"])
def test_retired_delay_representations_leave_only_the_new_meter_panel(widget_id, names):
    values = {
        "Docks/dockNames": names,
        "Docks/Delay/type": widget_id,
        "Docks/Delay/custom": "discard",
    }

    settings_schema.apply_upgrades(values, 1)

    assert values == {"Docks/dockNames": ["Meters"], "Docks/Meters/type": 9}


@pytest.mark.parametrize("names", [None, [], "Surviving"])
def test_v1_optional_and_singleton_layout_encodings_are_normalized(names):
    values = {"Docks/dockNames": names}

    settings_schema.apply_upgrades(values, 1)

    assert values == {"Docks/dockNames": ["Meters", names] if isinstance(names, str) else ["Meters"],
                      "Docks/Meters/type": 9}


@pytest.mark.parametrize("stack,expected", [
    (None, []), ([], []), (6, []), ("+006", []), (7, [7]), ("8", ["8"]),
    ([6, "006", "+6", " 6 ", 7, "8", 6.5, "other"], [7, "8", 6.5, "other"]),
    (False, False), (6.0, 6.0), ({"unknown": 6}, {"unknown": 6}),
])
def test_v1_stack_encodings_remove_only_retired_ids(stack, expected):
    values = {"Docks/widgetIdStack": stack}

    settings_schema.apply_upgrades(values, 1)

    assert values == {"Docks/widgetIdStack": expected}


@pytest.mark.parametrize("widget_id", [False, 6.0, "6.0", "invalid", 2**40, 7, 8])
def test_unknown_and_malformed_delay_ids_are_retained(widget_id):
    opaque = QByteArray(b"\x00unknown")
    values = {
        "Docks/dockNames": ["Panel"],
        "Docks/Panel/type": widget_id,
        "Docks/Panel/custom": opaque,
        "Docks/widgetIdStack": [widget_id],
    }
    original = values.copy()

    settings_schema.apply_upgrades(values, 1)

    assert values == {**original, "Docks/dockNames": ["Meters", "Panel"], "Docks/Meters/type": 9}
    assert values["Docks/Panel/custom"] is opaque


@pytest.mark.parametrize("names", [42, ["duplicate", "duplicate"], ["bad/name"], [42]])
@pytest.mark.parametrize("from_version", [0, 1])
def test_malformed_layout_does_not_prevent_independent_feature_cleanup(names, from_version):
    values = {
        "Docks/dockNames": names,
        "Docks/Unknown/type": "invalid",
        "AudioBackend/showPlayback": 2,
        "AudioBackend/historyLength": 30,
        "Docks/widgetIdStack": [6, 7],
        "Docks/lastSettings/6/delay_range": 4.5,
        "Docks/lastSettings/8/freqMin": 80,
    }

    settings_schema.apply_upgrades(values, from_version)

    assert values == {
        "Docks/dockNames": names,
        "Docks/Unknown/type": "invalid",
        "Docks/widgetIdStack": [7],
        "Docks/lastSettings/8/freqMin": 80,
    }


@pytest.mark.parametrize("names", [None, ["Spectrum"], "Spectrum"])
def test_v1_central_relocation_runs_before_retired_delay_cleanup(names):
    values = {
        "CentralWidget/type": 6,
        "CentralWidget/delay_range": 4.5,
        "Docks/dockNames": names,
    }
    if names is not None:
        values["Docks/Spectrum/type"] = 2
        values["Docks/Spectrum/fftSize"] = 9

    settings_schema.apply_upgrades(values, 0)

    assert not any(key.startswith(("CentralWidget/", "Docks/central/")) for key in values)
    assert values["Docks/dockNames"] == (["Meters", "Spectrum"] if names is not None else ["Meters"])
    if names is not None:
        assert values["Docks/Spectrum/fftSize"] == 9


def test_v2_does_not_reapply_existing_v1_layout_upgrades():
    values = {
        "CentralWidget/type": 2,
        "Docks/dockNames": ["Old level"],
        "Docks/Old level/type": 0,
        "AudioBackend/showPlayback": 2,
    }

    settings_schema.apply_upgrades(values, 1)

    assert values == {
        "CentralWidget/type": 2,
        "Docks/dockNames": ["Meters", "Old level"],
        "Docks/Meters/type": 9,
        "Docks/Old level/type": 0,
    }


def test_only_pending_schema_upgrades_run_in_order(monkeypatch):
    calls = []

    def already_applied(values):
        raise AssertionError("Completed schema upgrades must not run again")

    def second(values):
        calls.append(2)
        values["new"] = "second"

    def third(values):
        calls.append(3)
        assert values["new"] == "second"
        values["new"] = "third"

    monkeypatch.setattr(settings_schema, "UPGRADES", (already_applied, second, third))
    monkeypatch.setattr(settings_schema, "CURRENT_VERSION", 3)
    values = {"existing": "retained"}

    settings_schema.apply_upgrades(values, 1)
    settings_schema.apply_upgrades(values, 3)

    assert calls == [2, 3]
    assert values == {"existing": "retained", "new": "third"}


@pytest.mark.parametrize("version", [None, True, 0.0, "invalid", -1, "-1"])
def test_invalid_schema_version_is_rejected_before_changing_snapshot(version):
    values = {"CentralWidget/type": 1}
    original = values.copy()

    with pytest.raises(settings_schema.SettingsSchemaError, match="Invalid Polyfriture"):
        settings_schema.apply_upgrades(values, version)

    assert values == original


def test_future_schema_version_is_rejected_before_changing_snapshot():
    values = {"CentralWidget/type": 1}
    original = values.copy()

    with pytest.raises(settings_schema.SettingsSchemaError, match="newer Polyfriture version"):
        settings_schema.apply_upgrades(values, settings_schema.CURRENT_VERSION + 1)

    assert values == original


@pytest.mark.parametrize("version", [0, "0", settings_schema.CURRENT_VERSION,
                                   str(settings_schema.CURRENT_VERSION)])
def test_native_and_ini_schema_versions_are_accepted(version):
    assert settings_schema.parse_version(version) == int(version)


@pytest.mark.parametrize("names", [None, [], "Scope", ["Scope"]])
def test_v3_moves_former_permanent_meters_into_an_explicit_layout(names):
    values = {"Docks/dockNames": names, "Docks/Scope/type": 1,
              "unknown/opaque": QByteArray(b"retained")}
    settings_schema.apply_upgrades(values, 2)
    assert values["Docks/dockNames"] == ["Meters", *(["Scope"] if names else [])]
    assert values["Docks/Meters/type"] == 9
    assert values["Docks/Scope/type"] == 1
    assert values["unknown/opaque"] == QByteArray(b"retained")
    upgraded = values.copy()
    settings_schema.apply_upgrades(values, 2)
    assert values == upgraded


@pytest.mark.parametrize("widget_id", [9, "9", "+009", " 9 "])
def test_v3_does_not_duplicate_existing_active_meter_panels(widget_id):
    values = {"Docks/dockNames": ["Scope", "Custom meter"],
              "Docks/Scope/type": 1, "Docks/Custom meter/type": widget_id}
    original = values.copy()
    settings_schema.apply_upgrades(values, 2)
    assert values == original


@pytest.mark.parametrize("widget_id", [True, 9.0, "9.0", "unknown"])
def test_v3_unknown_or_malformed_ids_do_not_hide_the_former_meters(widget_id):
    values = {"Docks/dockNames": ["Unknown"], "Docks/Unknown/type": widget_id}
    settings_schema.apply_upgrades(values, 2)
    assert values == {"Docks/dockNames": ["Meters", "Unknown"],
                      "Docks/Unknown/type": widget_id, "Docks/Meters/type": 9}


def test_v3_unique_meter_name_preserves_inactive_groups_and_layout_order():
    values = {"Docks/dockNames": ["Meters", "Scope"], "Docks/Meters/type": 2,
              "Docks/Scope/type": 1, "Docks/Meters 2/custom/nested": QByteArray(b"keep"),
              "Docks/Meters 3": "opaque group value", "Docks/lastSettings/9/custom": "cached"}
    original = values.copy()
    settings_schema.apply_upgrades(values, 2)
    assert values == {**original, "Docks/dockNames": ["Meters 4", "Meters", "Scope"],
                      "Docks/Meters 4/type": 9}


@pytest.mark.parametrize("values", [{}, {"Docks/Scope/type": 1},
                                   {"Docks/dockNames": 42}, {"Docks/dockNames": ["bad/name"]},
                                   {"Docks/dockNames": ["Scope", "Scope"]}])
def test_v3_missing_and_malformed_layouts_are_not_materialized_or_repaired(values):
    original = values.copy()
    settings_schema.apply_upgrades(values, 2)
    assert values == original


def test_meters_removed_from_current_layout_are_not_readded_on_later_launches():
    values = {"Docks/dockNames": []}
    settings_schema.apply_upgrades(values, settings_schema.CURRENT_VERSION)
    assert values == {"Docks/dockNames": []}
