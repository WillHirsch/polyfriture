# AGENTS.md

## Overview

**Polyfriture** is a fork of Friture, a real-time audio visualization and analysis application. It captures live audio via PortAudio, processes it with NumPy, and renders visualizations in a PyQt6 hybrid QWidget + QML GUI.

## Repository Organization

| Path                   | Purpose                                                   |
|------------------------|-----------------------------------------------------------|
| `main.py`              | Entry point; calls `polyfriture.analyzer:main`                |
| `polyfriture/`             | Main application package                                  |
| `polyfriture/analyzer.py`  | `Friture` QMainWindow — sets up QML engine, audio backend, docks, timers; `main()` entry point |
| `polyfriture/audiobackend.py` | Audio I/O via `sounddevice` + `rtmixer`; singleton accessed as `AudioBackend()` |
| `polyfriture/audiobuffer.py` | `AudioBuffer` — ring buffer wrapper, forwards data to widgets |
| `polyfriture/ringbuffer.py` | `RingBuffer` — circular buffer for audio samples            |
| `polyfriture/audioproc.py`  | `audioproc` — FFT analysis for the spectrum widget         |
| `polyfriture/dockmanager.py`| `DockManager` — manages dock creation/closure/ordering     |
| `polyfriture/dock.py`       | `Dock` — QML dock container hosting an audio widget         |
| `polyfriture/widgetdict.py` | Registry of available panels (8 types, including Generator) |
| `polyfriture/store.py`      | `Store` singleton exposed to QML for dock state              |
| `polyfriture/plotting/`     | Plotting infrastructure (CoordinateTransform, ScaleDivision, frequency scales, color maps) |
| `polyfriture/signal/`       | Signal processing modules (IIR/FIR filters, resampling, transforms) |
| `polyfriture/generators/`   | Built-in signal generator widgets (sine, white, pink, sweep, burst) |
| `polyfriture/test/`         | Test suite                                                 |
| `polyfriture/*.qml`         | QML view files for visualizations and main window          |
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

1. **Audio capture**: `AudioBackend` (singleton in `audiobackend.py`) opens a PortAudio stream via `rtmixer` and fills a `rtmixer.RingBuffer`.
2. **Buffering**: `AudioBackend.fetchAudioData()` (called on the display timer) drains the ring buffer, emits `new_data_available`, which `AudioBuffer` receives and pushes into its own `RingBuffer`.
3. **Processing**: `AudioBuffer.new_data_available` fans out to every dock's audio widget. Each widget computes its own FFT/spectrogram/scattering in `handle_new_data()`.
4. **Rendering**: The display timer (10 ms) calls `DockManager.canvasUpdate()`, which calls each widget's `canvasUpdate()`, updating the QML views.

### Widget Architecture

Each visualization widget follows a consistent pattern:

- **Python class** (e.g. `Spectrum_Widget` in `spectrum.py`) — audio data processing, buffer management, settings dialog, state save/restore.
  Registered in `widgetdict.py` and instantiated by `Dock`.
- **QML file** (e.g. `Spectrum.qml`) — declarative rendering and UI layout.
- **View model** (e.g. `Scope_Data`, `Spectrum_Data`) — QObject subclass with `pyqtProperty` fields, bridged to QML.

Available widgets (see `widgetdict.py`):

| Widget ID | Class              | QML file        | Description             |
|-----------|--------------------|-----------------|-------------------------|
| 1         | `Scope_Widget`     | `Scope.qml`     | Oscilloscope            |
| 2         | `Spectrum_Widget`  | `Spectrum.qml`  | FFT spectrum analyzer   |
| 3         | `Spectrogram_Widget` | `Spectrogram.qml` | 2D rolling spectrogram |
| 4         | `OctaveSpectrum_Widget` | `OctaveSpectrum.qml` | Octave-band spectrum |
| 5         | `Generator_Widget` | `Generator.qml` | Signal generator        |
| 7         | `LongLevelWidget`  | `LongLevels.qml` | Long-time level histories |
| 8         | `PitchTrackerWidget` | `PitchView.qml` | Pitch tracking         |
| 9         | `Levels_Widget`    | `Levels.qml`    | Channel-grid level meters |
| 9         | `Levels_Widget` | `Levels.qml` | Channel peak/RMS meters |

### Signal Processing

`polyfriture/signal/` contains reusable DSP modules:

- `lfilter.py` — IIR/FIR filtering, IIR-to-minimum-phase-FIR conversion
- `decimate.py` — decimation
- `exp_smoothing.py` — exponential smoothing for display
- `frequency_resampler.py` — resampling for FFT display
- `transform_pipeline.py` — generic pipeline of processing blocks
- `lookup_table.py` — fast lookup tables
- `linear_interp.py` — linear interpolation
- `color_tranform.py` — color transformations

## Development Setup

```bash
uv sync
uv run python main.py
```

Dependencies are managed by `uv` (see `uv.lock`). See `INSTALL.md` for platform-specific instructions.

## Testing & Tooling

| Command              | Tool   | Purpose                          |
|----------------------|--------|----------------------------------|
| `uv run --frozen pytest -ra` | pytest | Run the full discovered source suite (`polyfriture/test/`) |
| `uv run mypy`        | mypy   | Type-check the codebase           |
| `uv run python main.py` | —   | Run the application              |

Tests live in `polyfriture/test/` and cover signal processing, filters, pitch tracking, and QML integration.

See [TESTING.md](TESTING.md) for the source-test CI matrix and merge/release
policy. The suite supplies headless Qt defaults and isolates settings and audio
access. Source tests run separately from packaging; tagged releases require both.

## Regenerating Generated Files

If UI or resource files change, regenerate:

```bash
uv run pyuic6 ui/settings.ui -o polyfriture/ui_settings.py
uv run pyrcc6 resources/friture.qrc -o polyfriture/friture_rc.py
uv run python polyfriture/filter_design.py  # regenerate generated_filters.py / generated_fft.py
```

The Python package is `polyfriture`; the application, command, settings, and log identity is `polyfriture`. Preserve upstream copyright and license notices.
`polyfriture/ui_friture.py` is a hand-maintained main-window shell; only the settings dialog currently has a Qt Designer source.
