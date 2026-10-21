"""Generator runtime edits and saved profiles use the same settings models."""

import numpy as np
import pytest
from PyQt6.QtCore import QByteArray, QSettings

from polyfriture.generator import GENERATOR_TYPES, GeneratorSettings, GeneratorDeviceSettings, Generator_View_Model
from polyfriture.generators.burst import BurstSettings, Burst_Generator_Settings_View_Model
from polyfriture.generators.sine import SineSettings, Sine_Generator_Settings_View_Model
from polyfriture.generators.sweep import SweepGenerator, SweepSettings, Sweep_Generator_Settings_View_Model
from polyfriture.settings_model import SettingsValueError


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "generator.ini"), QSettings.Format.IniFormat)


@pytest.mark.parametrize("model_type,key,value", [
    (SineSettings, "sine frequency", "440.5"),
    (SweepSettings, "sweep start frequency", "20.5"),
    (SweepSettings, "sweep stop frequency", "21999.5"),
    (SweepSettings, "sweep period", "0.25"),
    (BurstSettings, "burst period", "0.25"),
    (GeneratorSettings, "generator kind", "4"),
])
def test_assignment_and_restore_normalize_identically(settings, model_type, key, value):
    assigned = model_type()
    assigned.set(key, value)
    settings.setValue(key, value)
    restored = model_type()
    restored.restore(settings)
    assert restored.get(key) == assigned.get(key)


@pytest.mark.parametrize("model_type,key", [
    (SineSettings, "sine frequency"),
    (SweepSettings, "sweep start frequency"),
    (SweepSettings, "sweep stop frequency"),
    (SweepSettings, "sweep period"),
    (BurstSettings, "burst period"),
])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True, "broken"])
def test_invalid_values_rejected_by_assignment_and_defaulted_on_restore(settings, model_type, key, value):
    model = model_type()
    default = model.get(key)
    with pytest.raises(SettingsValueError):
        model.set(key, value)
    assert model.get(key) == default
    settings.setValue(key, value)
    model.restore(settings)
    assert model.get(key) == default


@pytest.mark.parametrize("vm_type,attribute,signal_name,valid", [
    (Sine_Generator_Settings_View_Model, "frequency", "frequency_changed", 880.5),
    (Sweep_Generator_Settings_View_Model, "start_frequency", "start_frequency_changed", 40.5),
    (Sweep_Generator_Settings_View_Model, "stop_frequency", "stop_frequency_changed", 20000.5),
    (Sweep_Generator_Settings_View_Model, "period", "peiod_changed", 2.5),
    (Burst_Generator_Settings_View_Model, "period", "period_changed", 2.5),
])
def test_invalid_view_model_assignment_retains_value_and_emits_nothing(vm_type, attribute, signal_name, valid):
    vm = vm_type(None)
    setattr(vm, attribute, valid)
    changes = []
    getattr(vm, signal_name).connect(changes.append)
    for invalid in (float("nan"), float("inf"), float("-inf"), -1., 1e10):
        setattr(vm, attribute, invalid)
        assert getattr(vm, attribute) == valid
    assert changes == []


def test_sweep_restore_publishes_complete_candidate_and_keeps_valid_siblings(settings):
    vm = Sweep_Generator_Settings_View_Model(None)
    vm.start_frequency = 200.
    settings.setValue("sweep start frequency", "nan")
    settings.setValue("sweep stop frequency", "100.5")
    settings.setValue("sweep period", "2.5")
    observed = []
    for signal in (vm.start_frequency_changed, vm.stop_frequency_changed, vm.peiod_changed):
        signal.connect(lambda _: observed.append((vm.start_frequency, vm.stop_frequency, vm.period)))
    vm.restoreState(settings)
    assert observed == [(20., 100.5, 2.5)] * 3
    assert settings.value("sweep start frequency") == "nan"


def test_sine_rejected_assignment_does_not_change_phase():
    vm = Sine_Generator_Settings_View_Model(None)
    vm.lastt = 0.125
    vm.frequency = 440.5
    previous = (vm.frequency, vm.offset)
    vm.frequency = float("nan")
    assert (vm.frequency, vm.offset) == previous


def test_generator_choices_and_instances_share_one_definition(settings):
    generators = [generator(None) for generator in GENERATOR_TYPES]
    vm = Generator_View_Model(None, generators)
    assert vm.generatorNames == [generator.name for generator in generators]
    changes = []
    vm.generatorChanged.connect(lambda: changes.append(vm.generatorIndex))
    vm.generatorIndex = len(generators) - 1
    for invalid in (-1, len(generators), True, 0.5, "broken"):
        vm.generatorIndex = invalid
    assert changes == [len(generators) - 1]
    settings.setValue("generator kind", len(generators))
    vm.restoreState(settings)
    assert vm.generatorIndex == 0
    assert changes == [len(generators) - 1, 0]


def test_output_device_names_are_not_restricted_to_current_hardware(settings):
    model = GeneratorDeviceSettings()
    settings.setValue("deviceName", "Currently disconnected interface")
    model.restore(settings)
    assert model.get("deviceName") == "Currently disconnected interface"


def test_saving_known_generator_fields_preserves_unknown_qt_values(settings):
    value = QByteArray(b"\x00unknown\xff")
    settings.setValue("extensionState", value)
    model = SweepSettings()
    model.set("sweep start frequency", "20.5")
    model.save(settings)
    assert settings.value("extensionState") == value


@pytest.mark.parametrize("frequency", [20., 440.5, 22000.])
def test_equal_sweep_endpoints_reject_assignment_and_recover_saved_group(settings, frequency):
    model = SweepSettings()
    endpoints = ("sweep start frequency", "sweep stop frequency")
    with pytest.raises(SettingsValueError) as error:
        model.update({key: frequency for key in endpoints})
    assert error.value.keys == endpoints
    assert [model.get(key) for key in endpoints] == [20., 22000.]

    for key in endpoints:
        settings.setValue(key, frequency)
    settings.setValue("sweep period", 2.5)
    generator = SweepGenerator(None)
    with np.errstate(all="raise"):
        generator.view_model().restoreState(settings)
        assert np.isfinite(generator.nextParams).all()
    restored = generator.view_model()
    assert (restored.start_frequency, restored.stop_frequency, restored.period) == (20., 22000., 2.5)
    assert [settings.value(key) for key in endpoints] == [frequency, frequency]


@pytest.mark.parametrize("attribute,other", [
    ("start_frequency", "stop_frequency"),
    ("stop_frequency", "start_frequency"),
])
def test_equal_runtime_endpoint_retains_previous_values_and_emits_nothing(attribute, other):
    vm = Sweep_Generator_Settings_View_Model(None)
    previous = (vm.start_frequency, vm.stop_frequency, vm.period)
    changes = []
    vm.start_frequency_changed.connect(changes.append)
    vm.stop_frequency_changed.connect(changes.append)
    setattr(vm, attribute, getattr(vm, other))
    assert (vm.start_frequency, vm.stop_frequency, vm.period) == previous
    assert changes == []


def test_swapping_sweep_endpoints_during_restore_commits_before_computation(settings):
    settings.setValue("sweep start frequency", 22000.)
    settings.setValue("sweep stop frequency", 20.)
    settings.setValue("sweep period", 2.5)
    generator = SweepGenerator(None)
    vm = generator.view_model()
    observed = []
    for signal in (vm.start_frequency_changed, vm.stop_frequency_changed, vm.peiod_changed):
        signal.connect(lambda _: observed.append((vm.start_frequency, vm.stop_frequency, vm.period)))
    with np.errstate(all="raise"):
        vm.restoreState(settings)
        assert np.isfinite(generator.nextParams).all()
    assert observed == [(22000., 20., 2.5)] * 3


@pytest.mark.parametrize("start,stop", [(20.5, 21999.5), (21999.5, 20.5)])
def test_valid_sweep_directions_still_produce_finite_samples(start, stop):
    generator = SweepGenerator(None)
    with np.errstate(all="raise"):
        generator.L, generator.K, generator.T = generator.computeParams(start, stop, .01)
        assert np.isfinite(generator.signal(np.arange(4096) / 48000.)).all()
