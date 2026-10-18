# AGENTS.md

## Overview

**friture-monitor** is a fork of Friture, a real-time audio visualization and analysis application. It captures
live audio via PortAudio, processes it with NumPy, and renders visualizations in a
PyQt6 hybrid QWidget + QML GUI.

## Repository Organization

| Path                   | Purpose                                                   |
|------------------------|-----------------------------------------------------------|
| `main.py`              | Entry point; calls `friture_monitor.analyzer:main`                |
| `friture_monitor/`             | Main application package                                  |
| `friture_monitor/analyzer.py`  | `Friture` QMainWindow — sets up QML engine, audio backend, docks, timers; `main()` entry point |
| `friture_monitor/audiobackend.py` | Audio I/O via `sounddevice` + `rtmixer`; singleton accessed as `AudioBackend()` |
| `friture_monitor/audiobuffer.py` | `AudioBuffer` — ring buffer wrapper, forwards data to widgets |
| `friture_monitor/ringbuffer.py` | `RingBuffer` — circular buffer for audio samples            |
| `friture_monitor/audioproc.py`  | `audioproc` — FFT analysis for the spectrum widget         |
| `friture_monitor/dockmanager.py`| `DockManager` — manages dock creation/closure/ordering     |
| `friture_monitor/dock.py`       | `Dock` — QML dock container hosting an audio widget         |
| `friture_monitor/widgetdict.py` | Registry of available visualization widgets (8 types)      |
| `friture_monitor/store.py`      | `Store` singleton exposed to QML for dock state              |
| `friture_monitor/plotting/`     | Plotting infrastructure (CoordinateTransform, ScaleDivision, frequency scales, color maps) |
| `friture_monitor/signal/`       | Signal processing modules (IIR/FIR filters, resampling, transforms) |
| `friture_monitor/generators/`   | Built-in signal generator widgets (sine, white, pink, sweep, burst) |
| `friture_monitor/playback/`     | Audio playback subsystem                                   |
| `friture_monitor/test/`         | Test suite                                                 |
| `friture_monitor/*.qml`         | QML view files for visualizations and main window          |
| `ui/`                   | Qt Designer `.ui` files (settings, main window)             |
| `resources/`            | Qt resource files (`.qrc`, icons, splash)                   |
| `installer/`            | PyInstaller spec and hooks for packaging                     |

## Architecture

### Data Flow

```
Audio hardware → audiobackend (rtmixer ringbuffer) → AudioBuffer → DockManager → Widget.handle_new_data()
                                                                                            ↓
                    display_timer (10 ms)         slow_timer (1 s)
                          ↓                          ↓
             DockManager.canvasUpdate()    text/label refresh
             Widget.canvasUpdate()         → QML view update
```

1. **Audio capture**: `AudioBackend` (singleton in `audiobackend.py`) opens a
   PortAudio stream via `rtmixer` and fills a `rtmixer.RingBuffer`.
2. **Buffering**: `AudioBackend.fetchAudioData()` (called on the display timer)
   drains the ring buffer, emits `new_data_available`, which `AudioBuffer`
   receives and pushes into its own `RingBuffer`.
3. **Processing**: `AudioBuffer.new_data_available` fans out to every dock's
   audio widget. Each widget computes its own FFT/spectrogram/scattering in
   `handle_new_data()`.
4. **Rendering**: The display timer (10 ms) calls `DockManager.canvasUpdate()`,
   which calls each widget's `canvasUpdate()`, updating the QML views.

### Widget Architecture

Each visualization widget follows a consistent pattern:

- **Python class** (e.g. `Spectrum_Widget` in `spectrum.py`) — audio data
  processing, buffer management, settings dialog, state save/restore.
  Registered in `widgetdict.py` and instantiated by `Dock`.
- **QML file** (e.g. `Spectrum.qml`) — declarative rendering and UI layout.
- **View model** (e.g. `Scope_Data`, `Spectrum_Data`) — QObject subclass with
  `pyqtProperty` fields, bridged to QML.

Available widgets (see `widgetdict.py`):

| Widget ID | Class              | QML file        | Description             |
|-----------|--------------------|-----------------|-------------------------|
| 1         | `Scope_Widget`     | `Scope.qml`     | Oscilloscope            |
| 2         | `Spectrum_Widget`  | `Spectrum.qml`  | FFT spectrum analyzer   |
| 3         | `Spectrogram_Widget` | `Spectrogram.qml` | 2D rolling spectrogram |
| 4         | `OctaveSpectrum_Widget` | `OctaveSpectrum.qml` | Octave-band spectrum |
| 5         | `Generator_Widget` | `Generator.qml` | Signal generator        |
| 6         | `Delay_Estimator_Widget` | `DelayEstimator.qml` | Delay estimation |
| 7         | `LongLevelWidget`  | —               | Long-time level meters  |
| 8         | `PitchTrackerWidget` | `PitchView.qml` | Pitch tracking         |

### Signal Processing

`friture_monitor/signal/` contains reusable DSP modules:

- `lfilter.py` — IIR/FIR filtering, IIR-to-minimum-phase-FIR conversion
- `decimate.py` — decimation
- `exp_smoothing.py` — exponential smoothing for display
- `frequency_resampler.py` — resampling for FFT display
- `transform_pipeline.py` — generic pipeline of processing blocks
- `lookup_table.py` — fast lookup tables
- `linear_interp.py` — linear interpolation
- `correlation.py` — cross-correlation (used by delay estimator)
- `color_tranform.py` — color transformations

## Development Setup

```bash
uv sync
uv run python main.py
```

Dependencies are managed by `uv` (see `uv.lock`). See `INSTALL.md` for
platform-specific instructions.

## Testing & Tooling

| Command              | Tool   | Purpose                          |
|----------------------|--------|----------------------------------|
| `uv run pytest`      | pytest | Run the test suite (`friture_monitor/test/`) |
| `uv run mypy`        | mypy   | Type-check the codebase           |
| `uv run python main.py` | —   | Run the application              |

Tests live in `friture_monitor/test/` and cover signal processing, filters, pitch
tracking, and QML integration.

## Regenerating Generated Files

If UI or resource files change, regenerate:

```bash
uv run pyuic6 ui/settings.ui -o friture_monitor/ui_settings.py
uv run pyrcc6 resources/friture.qrc -o friture_monitor/friture_rc.py
uv run python friture_monitor/filter_design.py  # regenerate generated_filters.py / generated_fft.py
```

The Python package is `friture_monitor`; the application, command, settings, and
log identity is `friture-monitor`. Preserve upstream copyright and license notices.
`friture_monitor/ui_friture.py` is a hand-maintained main-window shell; only the
settings dialog currently has a Qt Designer source.
