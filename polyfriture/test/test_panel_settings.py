"""Panel settings use the same definitions for restoration and runtime edits."""

from collections import defaultdict

from PyQt6.QtCore import QByteArray, QSettings
from PyQt6.QtWidgets import QApplication
import pytest

from polyfriture.longlevels_settings import LongLevelsSettings, LongLevels_Settings_Dialog
from polyfriture.octavespectrum_settings import OctaveSpectrumSettings, OctaveSpectrum_Settings_Dialog
from polyfriture.pitch_tracker_settings import PitchTrackerSettings, PitchTrackerSettingsDialog
from polyfriture.scope import ScopeSettings, Scope_Settings_Dialog
from polyfriture.settings_model import SettingsValueError
from polyfriture.spectrogram_settings import SpectrogramSettings, Spectrogram_Settings_Dialog
from polyfriture.spectrum_settings import SpectrumSettings, Spectrum_Settings_Dialog


@pytest.fixture(scope="module")
def application():
    app = QApplication.instance() or QApplication([])
    yield app


class ViewModel:
    """Record dialog effects without constructing audio or DSP components."""

    def __init__(self):
        self.calls = defaultdict(list)
        self.PlotZoneSpect = self

    def __getattr__(self, name):
        return lambda value: self.calls[name].append(value)


PANELS = [
    (ScopeSettings, Scope_Settings_Dialog, "timeRange", "not numeric", None, None),
    (SpectrumSettings, Spectrum_Settings_Dialog, "fftSize", -1, "freqMin", 123),
    (SpectrogramSettings, Spectrogram_Settings_Dialog, "timeRange", "nan", "freqMin", 123),
    (OctaveSpectrumSettings, OctaveSpectrum_Settings_Dialog, "bandsPerOctave", 999, "Min", -61),
    (LongLevelsSettings, LongLevels_Settings_Dialog, "RespTime", 0, "TimeMax", 120),
    (PitchTrackerSettings, PitchTrackerSettingsDialog, "conf", "nan", "duration", 30),
]


@pytest.mark.parametrize("model_type,dialog_type,key,invalid,other,valid", PANELS)
def test_panel_restore_recovers_invalid_field_and_preserves_neighbors(
        application, tmp_path, model_type, dialog_type, key, invalid, other, valid):
    settings = QSettings(str(tmp_path / "panel.ini"), QSettings.Format.IniFormat)
    settings.setValue(key, invalid)
    if other is not None:
        settings.setValue(other, valid)
    settings.setValue("future/opaque", QByteArray(b"\x00future\xff"))
    settings.sync()
    original = (tmp_path / "panel.ini").read_bytes()

    model = model_type()
    with pytest.raises(SettingsValueError):
        model.set(key, invalid)
    assert model.get(key) == model.fields[key].default

    view_model = ViewModel()
    dialog = dialog_type(None, view_model)
    try:
        # Dialog construction must not call into an engine that is still being
        # initialized by its owning widget.
        assert not view_model.calls
        restore = dialog.restore_state if isinstance(dialog, PitchTrackerSettingsDialog) else dialog.restoreState
        restore(settings)
        assert dialog.model.get(key) == model.fields[key].default
        if other is not None:
            assert dialog.model.get(other) == valid
        # Restoring recovery defaults must not rewrite the saved profile.
        settings.sync()
        assert (tmp_path / "panel.ini").read_bytes() == original

        save = dialog.save_state if isinstance(dialog, PitchTrackerSettingsDialog) else dialog.saveState
        save(settings)
        assert settings.value("future/opaque") == QByteArray(b"\x00future\xff")
    finally:
        dialog.close()
        dialog.deleteLater()


def test_spectrum_choice_controls_reject_invalid_runtime_index(application):
    view_model = ViewModel()
    dialog = Spectrum_Settings_Dialog(None, view_model)
    try:
        dialog.comboBox_fftsize.setCurrentIndex(0)
        assert dialog.model.get("fftSize") == 0
        assert view_model.calls["setfftsize"] == [32]
        dialog.comboBox_fftsize.setCurrentIndex(-1)
        assert dialog.comboBox_fftsize.currentIndex() == 0
        assert dialog.model.get("fftSize") == 0
        assert view_model.calls["setfftsize"] == [32]
    finally:
        dialog.close()
        dialog.deleteLater()


@pytest.mark.parametrize("model_type,low,high", [
    (SpectrumSettings, "freqMin", "freqMax"),
    (SpectrumSettings, "Min", "Max"),
    (SpectrogramSettings, "freqMin", "freqMax"),
    (SpectrogramSettings, "colorMin", "colorMax"),
    (OctaveSpectrumSettings, "Min", "Max"),
    (LongLevelsSettings, "Min", "Max"),
    (PitchTrackerSettings, "min_freq", "max_freq"),
])
def test_reversed_display_ranges_remain_supported(model_type, low, high):
    model = model_type()
    model.update({low: model.fields[high].default, high: model.fields[low].default})
    assert model.get(low) > model.get(high)


@pytest.mark.parametrize("model_type", [SpectrumSettings, SpectrogramSettings])
def test_frequency_choices_follow_available_scales(model_type):
    from polyfriture.plotting.frequency_scales import ALL

    model = model_type()
    assert model.fields["freqScale"].labels == tuple(scale.NAME for scale in ALL)
    assert model.set("freqScale", len(ALL) - 1) == len(ALL) - 1
    with pytest.raises(SettingsValueError):
        model.set("freqScale", len(ALL))
