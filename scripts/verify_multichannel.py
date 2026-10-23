"""Measure the real multichannel window without audio hardware or user settings.

Each case runs in a fresh process with a temporary INI profile. The synthetic
capture ring generates deterministic 48 kHz tones according to wall time, so a
blocked GUI accumulates backlog and can overflow just as a live source would.
These are synthetic capture overflows, not measurements of a physical driver.
Run with --help for the case format and output files.
"""

import argparse
from collections import deque
import ctypes
import ctypes.util
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import faulthandler
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import traceback


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class Case:
    name: str
    channels: int
    columns: int
    width: int
    height: int
    scale: float = 1.
    rotated: bool = False


CASES = {
    case.name: case for case in (
        Case("single", 1, 1, 1280, 900),
        Case("partial", 5, 3, 1920, 1080),
        Case("rotated-hidpi", 5, 3, 1280, 900, 1.5, True),
        Case("dense", 16, 4, 3840, 2160),
    )
}


def positive_float(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return result


def parse_case(value):
    if value in CASES:
        return CASES[value]
    try:
        name, channels, columns, size, scale, orientation = value.split(":")
        width, height = map(int, size.lower().split("x"))
        result = Case(name, int(channels), int(columns), width, height,
                      positive_float(scale), orientation == "rotated")
        if (not name or name in {".", ".."} or Path(name).name != name or any(c in name for c in "/\\:")
                or min(result.channels, result.columns, width, height) <= 0
                or orientation not in {"normal", "rotated"}):
            raise ValueError
        return result
    except (ValueError, argparse.ArgumentTypeError):
        raise argparse.ArgumentTypeError(
            "use a built-in case or NAME:CHANNELS:COLUMNS:WIDTHxHEIGHT:SCALE:normal|rotated"
        ) from None


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def memory_bytes():
    """Current and peak resident memory, using operating-system interfaces."""
    if sys.platform == "win32":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        query = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        query.restype = wintypes.BOOL
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not query(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.WorkingSetSize, counters.PeakWorkingSetSize

    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        resident = int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
        return resident, peak * 1024
    if sys.platform == "darwin":
        # mach_task_basic_info_data_t starts with virtual_size/resident_size.
        library = ctypes.CDLL(ctypes.util.find_library("c"))
        library.mach_task_self.restype = ctypes.c_uint
        information = (ctypes.c_uint32 * 12)()
        count = ctypes.c_uint32(len(information))
        if library.task_info(library.mach_task_self(), 20, information, ctypes.byref(count)) == 0:
            resident = ctypes.cast(information, ctypes.POINTER(ctypes.c_uint64))[1]
            return resident, peak
    return None, peak * 1024


def child(case, duration, warmup, directory):
    # Qt environment is configured in the parent before any Qt module imports.
    import numpy as np
    from types import SimpleNamespace
    from unittest.mock import patch
    from PyQt6.QtCore import (QSettings, QTimer, Qt,
                              QT_VERSION_STR, PYQT_VERSION_STR, qVersion)
    from PyQt6.QtGui import QFont, QFontDatabase
    from PyQt6.QtWidgets import QApplication
    from polyfriture import (analyzer, application as application_module, audiobackend, generator,
                             settings as settings_module, spectrogram,
                             statisticswidget, theme_manager)
    from polyfriture.settings_initialization import initialize_settings

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    # The Windows offscreen platform can start with an empty font database.
    # Explicitly load real system fonts for legible, reproducible screenshots.
    if sys.platform == "win32":
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for filename in ("segoeui.ttf", "consola.ttf"):
            if (fonts / filename).is_file():
                QFontDatabase.addApplicationFont(str(fonts / filename))
        app.setFont(QFont("Segoe UI", 9))

    sample_rate = audiobackend.SAMPLING_RATE
    packet_size = audiobackend.FRAMES_PER_BUFFER
    action = SimpleNamespace(stats=SimpleNamespace(input_overflows=0))

    class CaptureRing:
        """Wall-clock capture with the production ring's frame capacity.

        Samples are generated lazily from their absolute frame indices. The
        producer clock continues during DSP and Qt rendering, without a Python
        thread or GUI timer incorrectly slowing production when the GUI stalls.
        """
        capacity = 2 ** int(math.log2(3. * sample_rate))

        def __init__(self):
            self.epoch = None
            self.read_index = 0
            self.write_index = 0
            self.produced = 0
            self.dropped = 0
            self.max_backlog = 0
            self.segments = deque()

        def update(self):
            if self.epoch is None:
                return
            produced = int((time.perf_counter() - self.epoch) * sample_rate)
            incoming = produced - self.produced
            available = self.write_index - self.read_index
            accepted = min(incoming, self.capacity - available)
            dropped = incoming - accepted
            if accepted:
                stop = self.produced + accepted
                if self.segments and self.segments[-1][1] == self.produced:
                    self.segments[-1] = (self.segments[-1][0], stop)
                else:
                    self.segments.append((self.produced, stop))
                self.write_index += accepted
            self.produced = produced
            self.max_backlog = max(self.max_backlog, self.write_index - self.read_index)
            if dropped:
                self.dropped += dropped
                action.stats.input_overflows += 1

        @property
        def read_available(self):
            self.update()
            return self.write_index - self.read_index

        def get_read_buffers(self, count):
            # Gaps appear after rejected writes; retained samples stay ordered.
            arrays = []
            remaining = count
            for start, stop in self.segments:
                taken = min(remaining, stop - start)
                arrays.append(np.arange(start, start + taken, dtype=np.float64))
                remaining -= taken
                if not remaining:
                    break
            assert remaining == 0
            frames = np.concatenate(arrays)
            physical = np.arange(case.channels, dtype=np.float64)
            frequencies = 220. * 2. ** (physical / 12.)
            samples = (.1 * np.sin(2. * np.pi * frames[:, None]
                                   * frequencies[None, :] / sample_rate)).astype(np.float32)
            return count, samples.tobytes(), b""

        def advance_read_index(self, count):
            self.read_index += count
            while count:
                start, stop = self.segments.popleft()
                taken = min(count, stop - start)
                count -= taken
                if start + taken < stop:
                    self.segments.appendleft((start + taken, stop))

        def flush(self):
            self.update()
            self.read_index = self.write_index
            self.segments.clear()

    ring = CaptureRing()

    class Stream:
        device = 0
        active = False

        @property
        def time(self):
            return time.perf_counter()

        def start(self):
            self.active = True

        def stop(self):
            self.active = False

        close = stop

    device = {"name": "Synthetic multichannel input", "index": 0,
              "max_input_channels": case.channels, "hostapi": 0}
    backend_type = getattr(audiobackend, "__AudioBackend")
    settings_directory = Path(os.environ["POLYFRITURE_MEASUREMENT_SETTINGS"])
    profile_path = settings_directory / "profile.ini"
    profile = QSettings(str(profile_path), QSettings.Format.IniFormat)
    source = QSettings(str(settings_directory / "empty-friture.ini"), QSettings.Format.IniFormat)
    profile.setFallbacksEnabled(False)
    source.setFallbacksEnabled(False)
    names = ("Scope", "FFT", "Spectrogram", "Octave", "Long", "Pitch", "Meter")
    profile.setValue("Docks/dockNames", list(names))
    for name, identifier in zip(names, (1, 2, 3, 4, 7, 8, 9)):
        profile.setValue(f"Docks/{name}/type", identifier)
    profile.setValue("Docks/Spectrogram/rotated", case.rotated)
    profile.setValue("AudioBackend/deviceName", device["name"])
    profile.setValue("AudioBackend/deviceHostApi", "Synthetic API")
    profile.setValue("AudioBackend/selectedChannels", list(range(case.channels)))
    profile.setValue("AudioBackend/channelGridColumns", case.columns)
    initialize_settings(profile, source)

    errors, qml_warnings = [], []
    result = {"case": asdict(case), "duration_requested_seconds": duration,
              "warmup_requested_seconds": warmup, "python": sys.version,
              "platform": platform.platform(), "machine": platform.machine(),
              "processor": platform.processor(), "logical_cpus": os.cpu_count(),
              "qt_compiled": QT_VERSION_STR, "qt_runtime": qVersion(),
              "pyqt": PYQT_VERSION_STR, "numpy": np.__version__,
              "capture": "synthetic wall-clock 48000 Hz; no physical driver",
              "capture_ring_capacity_frames": ring.capacity,
              "capture_overflow_policy": "reject new synthetic frames when full",
              "renderer": os.environ.get("QT_QUICK_BACKEND", "default"),
              "rhi_backend": os.environ.get("QSG_RHI_BACKEND", "default"),
              "render_loop": os.environ.get("QSG_RENDER_LOOP", "default"),
              "qt_platform": os.environ.get("QT_QPA_PLATFORM", "default")}
    result["native_window_visible"] = os.environ.get("POLYFRITURE_MEASUREMENT_VISIBLE") == "1"
    # Patching enumeration and open_stream is the only hardware substitution.
    # The real backend, AudioBuffer, dock processing and QML rendering all run.
    with (
        patch.object(backend_type, "get_input_devices", lambda self: [device]),
        patch.object(backend_type, "get_output_devices", lambda self: []),
        patch.object(backend_type, "open_stream", lambda self, selected:
                     (Stream(), ring, action, case.channels)),
        patch.object(audiobackend.sounddevice, "query_devices",
                     lambda *args, kind=None: device if kind == "input" else [device]),
        patch.object(audiobackend.sounddevice, "query_hostapis", lambda index: {"name": "Synthetic API"}),
    ):
        backend = backend_type()
        # Cover both imported aliases and any future singleton lookup.
        audiobackend.__audiobackendInstance = backend
        for module in (analyzer, audiobackend, generator, settings_module,
                       spectrogram, statisticswidget):
            module.AudioBackend = lambda: backend
        analyzer.application_settings = lambda: profile
        application_module.application_settings = lambda: profile
        theme_manager.application_settings = lambda: profile
        window = analyzer.Friture()

        def exception_hook(kind, value, stack):
            errors.append("".join(traceback.format_exception(kind, value, stack)))
            sys.__excepthook__(kind, value, stack)
            app.quit()

        sys.excepthook = exception_hook
        window.qml_engine.warnings.connect(
            lambda warnings: qml_warnings.extend(warning.toString() for warning in warnings))
        window.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus)
        window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        window.resize(case.width, case.height)
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen" and not result["native_window_visible"]:
            window.move(-30000, -30000)
        elif result["native_window_visible"]:
            window.move(40, 40)
        window.show()
        # Keep startup/render allocation outside the timed audio interval.
        window.display_timer.stop()
        window.slow_timer.stop()
        app.processEvents()
        assert len(window.dockmanager.docks) == 7
        assert backend.channel_configuration.channel_ids == tuple(range(case.channels))
        result["window_logical_pixels"] = [window.width(), window.height()]
        result["window_position"] = [window.x(), window.y()]
        result["device_pixel_ratio"] = window.devicePixelRatioF()
        result["font_family"] = app.font().family()
        result["fixed_font_family"] = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
        # Native windows outside the desktop can defer polishing until a grab.
        # Give dependent layouts a second event/render pass before recording.
        window.quick_view.grabWindow()
        app.processEvents()
        window.quick_view.grabWindow().save(str(directory / "initial.png"))
        result["graphics_api"] = window.quick_view.rendererInterface().graphicsApi().name
        write_json(directory / "progress.json", {**result, "phase": "starting capture"})

        heartbeat = QTimer()
        heartbeat.setInterval(50)
        heartbeat_times, memory_samples = [], []
        measured_at = None
        cpu_at = 0.
        first_chunk = 0
        dropped_at = 0
        overflows_at = 0
        last_progress = 0.
        finished = False

        def snapshot(now):
            backlog = ring.read_available
            resident, peak = memory_bytes()
            return {"elapsed_seconds": now - measured_at,
                    "process_cpu_seconds": time.process_time() - cpu_at,
                    "resident_bytes": resident, "peak_resident_bytes": peak,
                    "processed_packets": backend.chunk_number - first_chunk,
                    "synthetic_overflow_events": action.stats.input_overflows - overflows_at,
                    "synthetic_dropped_frames": ring.dropped - dropped_at,
                    "capture_backlog_frames": backlog,
                    "maximum_capture_backlog_frames": ring.max_backlog,
                    "heartbeat_count": len(heartbeat_times)}

        def finish_teardown():
            nonlocal finished
            result["qml_teardown_warnings"] = qml_warnings[len(result["qml_warnings"]):]
            result["python_slot_errors"] = list(errors)
            finished = True
            app.quit()

        def finish_measurement(now):
            window.display_timer.stop()
            window.slow_timer.stop()
            heartbeat.stop()
            # Freeze timing before screenshots and explicit native teardown.
            result.update(snapshot(now))
            intervals = np.diff(heartbeat_times) * 1000.
            result["heartbeat_interval_ms"] = {
                "requested": 50., "p50": float(np.percentile(intervals, 50)) if len(intervals) else None,
                "p95": float(np.percentile(intervals, 95)) if len(intervals) else None,
                "maximum": float(intervals.max()) if len(intervals) else None}
            result["cpu_percent_one_core"] = (100. * result["process_cpu_seconds"] / result["elapsed_seconds"])
            result["processed_audio_seconds"] = result["processed_packets"] * packet_size / sample_rate
            result["resident_first_sample_bytes"] = memory_samples[0] if memory_samples else None
            write_json(directory / "metrics.json", {**result, "status": "capturing screenshot"})
            # Keep this complex window and its external QML engine within the
            # live event loop until rendering and native teardown are complete.
            image = window.quick_view.grabWindow()
            if image.isNull() or not image.save(str(directory / "window.png")):
                raise RuntimeError("Could not capture the rendered QML window")
            result["screenshot_pixels"] = [image.width(), image.height()]
            result["qml_warnings"] = list(qml_warnings)
            result["python_slot_errors"] = list(errors)
            write_json(directory / "metrics.json", {**result, "status": "tearing down window"})
            # Native scenegraph destruction may need Python on its render
            # thread. Let Qt delete the objects from its event dispatcher,
            # rather than holding the GIL in a synchronous Python delete call.
            engine = window.qml_engine

            def retire_backend():
                backend.close()
                backend.deleteLater()

            window.destroyed.connect(engine.deleteLater)
            engine.destroyed.connect(retire_backend)
            backend.destroyed.connect(finish_teardown)
            window.deleteLater()

        def tick():
            nonlocal measured_at, cpu_at, first_chunk, dropped_at, overflows_at, last_progress
            now = time.perf_counter()
            if measured_at is None:
                if now - ring.epoch < warmup:
                    return
                measured_at, cpu_at = now, time.process_time()
                first_chunk = backend.chunk_number
                dropped_at, overflows_at = ring.dropped, action.stats.input_overflows
                ring.max_backlog = ring.read_available
                heartbeat_times.append(now)
            else:
                heartbeat_times.append(now)
            if now - last_progress >= .25:
                sample = snapshot(now)
                memory_samples.append(sample["resident_bytes"])
                write_json(directory / "progress.json", {**result, "phase": "measuring", **sample})
                last_progress = now
            if now - measured_at >= duration:
                finish_measurement(now)

        heartbeat.timeout.connect(tick)
        heartbeat.start()
        # Startup rendering did not produce samples. Align the real backend's
        # read clock with the start of synthetic live capture, not construction.
        backend.restart()
        ring.epoch = time.perf_counter()
        window.display_timer.start()
        window.slow_timer.start()
        app.exec()
        if not finished:
            raise RuntimeError("GUI stopped before measurement and teardown completed")
    result["status"] = "failed" if errors or result["qml_warnings"] else "completed"
    write_json(directory / "metrics.json", result)
    return 1 if result["status"] == "failed" else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", action="append", type=parse_case,
                        help="repeat to select cases; built-ins: " + ", ".join(CASES)
                        + "; custom: NAME:CHANNELS:COLUMNS:WIDTHxHEIGHT:SCALE:normal|rotated")
    parser.add_argument("--duration", type=positive_float, default=5., help="measured seconds per case (default: 5)")
    parser.add_argument("--warmup", type=positive_float, default=1., help="audio warmup seconds per case (default: 1)")
    parser.add_argument("--timeout", type=positive_float, default=60., help="parent watchdog seconds per case (default: 60)")
    parser.add_argument("--renderer", choices=("default", "software"), default="default",
                        help="Qt Quick renderer; default follows the application's normal rendering path")
    parser.add_argument("--platform", default="offscreen",
                        help="Qt platform plugin (default: offscreen); e.g. windows, cocoa or xcb for native graphics")
    parser.add_argument("--visible", action="store_true",
                        help="show the native test window for graphics verification; otherwise native windows are placed outside the desktop")
    parser.add_argument("--output", type=Path, default=ROOT / "tools" / "multichannel-verification",
                        help="JSON, PNG and child logs directory; defaults under ignored tools/")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    cases = arguments.case or list(CASES.values())
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if arguments.child:
        if len(cases) != 1:
            parser.error("child invocation requires one case")
        # Leave a native/Python stack before the parent kills a starved loop.
        faulthandler.dump_traceback_later(arguments.timeout * .8)
        try:
            return child(cases[0], arguments.duration, arguments.warmup, output)
        finally:
            faulthandler.cancel_dump_traceback_later()
    if len({case.name for case in cases}) != len(cases):
        parser.error("case names must be unique")
    if arguments.visible and arguments.platform == "offscreen":
        parser.error("--visible requires a native --platform")
    results = []
    for case in cases:
        directory = output / case.name
        directory.mkdir(parents=True, exist_ok=True)
        for filename in ("metrics.json", "progress.json", "initial.png", "window.png", "stdout.txt", "stderr.txt"):
            (directory / filename).unlink(missing_ok=True)
        environment = os.environ.copy()
        environment.update(QT_QPA_PLATFORM=arguments.platform, QT_QUICK_CONTROLS_STYLE="Basic",
                           QT_SCALE_FACTOR=str(case.scale))
        environment["POLYFRITURE_MEASUREMENT_VISIBLE"] = "1" if arguments.visible else "0"
        if arguments.renderer == "default":
            environment.pop("QT_QUICK_BACKEND", None)
        else:
            environment["QT_QUICK_BACKEND"] = arguments.renderer
        specification = (f"{case.name}:{case.channels}:{case.columns}:{case.width}x{case.height}:"
                         f"{case.scale}:{'rotated' if case.rotated else 'normal'}")
        # Temporary INIs are removed on success, failure or watchdog timeout.
        # Keep logs and last heartbeat independently of the child exit path.
        with tempfile.TemporaryDirectory(prefix="polyfriture-measure-") as temporary:
            environment["POLYFRITURE_MEASUREMENT_SETTINGS"] = temporary
            command = [sys.executable, "-X", "faulthandler", str(Path(__file__).resolve()),
                       "--child", "--case", specification, "--duration", str(arguments.duration),
                       "--warmup", str(arguments.warmup), "--timeout", str(arguments.timeout),
                       "--output", str(directory)]
            started_at_utc = datetime.now(timezone.utc).isoformat()
            started = time.perf_counter()
            try:
                process = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
                                         text=True, timeout=arguments.timeout)
                status = {"returncode": process.returncode, "timed_out": False}
                stdout, stderr = process.stdout, process.stderr
            except subprocess.TimeoutExpired as error:
                status = {"returncode": None, "timed_out": True}
                stdout, stderr = error.stdout or b"", error.stderr or b""
                if isinstance(stdout, bytes):
                    stdout = stdout.decode("utf-8", "replace")
                if isinstance(stderr, bytes):
                    stderr = stderr.decode("utf-8", "replace")
            (directory / "stdout.txt").write_text(stdout, encoding="utf-8")
            (directory / "stderr.txt").write_text(stderr, encoding="utf-8")
        metrics_path = directory / "metrics.json"
        progress_path = directory / "progress.json"
        metric = (json.loads(metrics_path.read_text()) if metrics_path.exists() else
                  json.loads(progress_path.read_text()) if progress_path.exists() else {"case": asdict(case)})
        metric.update(status, subprocess_wall_seconds=time.perf_counter() - started,
                      started_at_utc=started_at_utc)
        if status["timed_out"] or status["returncode"] != 0:
            metric["status"] = "watchdog_timeout" if status["timed_out"] else "child_failed"
        write_json(metrics_path, metric)
        results.append(metric)
        print(f"{case.name}: {metric['status']} ({metric['subprocess_wall_seconds']:.1f}s)", flush=True)
    write_json(output / "summary.json", results)
    return 0 if all(result["status"] == "completed" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
