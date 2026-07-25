from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from PIL import Image, ImageTk

from .audio import AudioError, AudioPlayer
from .detector import FrameAnalysis, PhoneDetector, draw_analysis
from .settings import AppSettings, load_settings, save_settings
from .state import FocusPolicy, Phase, PolicyConfig, PolicySnapshot


@dataclass
class MonitorUpdate:
    frame_rgb: Any | None = None
    snapshot: PolicySnapshot | None = None
    detector_reason: str = ""
    message: str = ""
    fatal_error: str = ""
    stopped: bool = False
    audio_test_finished: bool = False


class MonitoringWorker(threading.Thread):
    def __init__(
        self,
        settings: AppSettings,
        updates: queue.Queue[MonitorUpdate],
        commands: queue.Queue[tuple[str, Any]],
    ) -> None:
        super().__init__(daemon=True, name="focus-guard-monitor")
        self.settings = settings
        self.updates = updates
        self.commands = commands
        self.stop_event = threading.Event()

    def request_stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        import cv2

        capture = None
        fatal_error = ""
        audio = AudioPlayer(self.settings.song_path, self.settings.volume)
        try:
            self._emit(
                MonitorUpdate(
                    message=(
                        "Loading the phone detector. The model downloads once "
                        "on first run..."
                    )
                )
            )
            detector = PhoneDetector(
                model_name=self.settings.model_name,
                confidence=self.settings.confidence,
                ignore_bottom_percent=self.settings.ignore_bottom_percent,
                require_person=self.settings.require_person,
            )
            if self.stop_event.is_set():
                return

            backend = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else 0
            capture = cv2.VideoCapture(self.settings.camera_index, backend)
            if not capture.isOpened() and backend:
                capture.release()
                capture = cv2.VideoCapture(self.settings.camera_index)
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            if not capture.isOpened():
                raise RuntimeError(
                    f"Camera {self.settings.camera_index} could not be opened. "
                    "It may be blocked, disconnected, or already in use."
                )

            policy = FocusPolicy(
                PolicyConfig(
                    trigger_seconds=self.settings.trigger_seconds,
                    clear_seconds=self.settings.clear_seconds,
                    cooldown_seconds=self.settings.cooldown_seconds,
                )
            )
            last_analysis = FrameAnalysis((), False, False, "Starting detector")
            last_snapshot = policy.update(False, time.monotonic())
            last_inference_at = 0.0
            inference_interval = 1.0 / self.settings.inference_fps
            failed_reads = 0
            message = "Work session is active"

            while not self.stop_event.is_set():
                message = self._handle_commands(policy, audio, message)

                ok, frame = capture.read()
                if not ok or frame is None:
                    failed_reads += 1
                    if failed_reads >= 20:
                        raise RuntimeError(
                            "The camera stopped returning frames. Reconnect it "
                            "or close any app that may be using it."
                        )
                    time.sleep(0.05)
                    continue
                failed_reads = 0

                now = time.monotonic()
                if now - last_inference_at >= inference_interval:
                    last_analysis = detector.analyze(frame)
                    last_snapshot = policy.update(
                        last_analysis.phone_in_use, now
                    )
                    last_inference_at = now

                    if last_snapshot.triggered:
                        try:
                            message = audio.play()
                        except AudioError as exc:
                            message = str(exc)
                    elif last_snapshot.cleared:
                        audio.stop()
                        message = "Nice — phone down. Back to focus."

                preview = draw_analysis(
                    frame.copy(),
                    last_analysis,
                    self.settings.ignore_bottom_percent,
                )
                preview = self._fit_preview(preview, 900, 560, cv2)
                frame_rgb = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
                self._emit(
                    MonitorUpdate(
                        frame_rgb=frame_rgb,
                        snapshot=last_snapshot,
                        detector_reason=last_analysis.reason,
                        message=message,
                    )
                )
        except Exception as exc:
            fatal_error = str(exc)
        finally:
            audio.close()
            if capture is not None:
                capture.release()
            self._emit(
                MonitorUpdate(fatal_error=fatal_error, stopped=True)
            )

    def _handle_commands(
        self, policy: FocusPolicy, audio: AudioPlayer, message: str
    ) -> str:
        while True:
            try:
                command, value = self.commands.get_nowait()
            except queue.Empty:
                return message

            now = time.monotonic()
            if command == "dismiss":
                policy.dismiss(now)
                audio.stop()
                message = "Reminder dismissed. Put the phone away to re-arm."
            elif command == "snooze":
                seconds = float(value)
                policy.snooze(now, seconds)
                audio.stop()
                message = f"Snoozed for {int(seconds // 60)} minutes."

    def _emit(self, update: MonitorUpdate) -> None:
        try:
            self.updates.put_nowait(update)
            return
        except queue.Full:
            pass

        try:
            self.updates.get_nowait()
        except queue.Empty:
            pass
        try:
            self.updates.put_nowait(update)
        except queue.Full:
            pass

    @staticmethod
    def _fit_preview(frame, max_width: int, max_height: int, cv2):
        height, width = frame.shape[:2]
        scale = min(max_width / width, max_height / height, 1.0)
        if scale >= 1.0:
            return frame
        return cv2.resize(
            frame,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_AREA,
        )


class FocusGuardApp:
    BG = "#10131a"
    PANEL = "#181d27"
    TEXT = "#f2f4f8"
    MUTED = "#a7b0c0"
    BLUE = "#61a5fa"
    GREEN = "#58d68d"
    ORANGE = "#ffb454"
    RED = "#ff6677"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.settings = load_settings()
        self.worker: MonitoringWorker | None = None
        self.audio_test_running = False
        self.updates: queue.Queue[MonitorUpdate] = queue.Queue(maxsize=2)
        self.commands: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.preview_image: ImageTk.PhotoImage | None = None

        self.root.title("Focus Guard")
        self.root.geometry("1240x820")
        self.root.minsize(1000, 700)
        self.root.configure(bg=self.BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.song_var = tk.StringVar(value=self.settings.song_path)
        self.camera_var = tk.StringVar(value=str(self.settings.camera_index))
        self.confidence_var = tk.StringVar(
            value=f"{self.settings.confidence:.2f}"
        )
        self.trigger_var = tk.StringVar(
            value=f"{self.settings.trigger_seconds:g}"
        )
        self.clear_var = tk.StringVar(
            value=f"{self.settings.clear_seconds:g}"
        )
        self.cooldown_var = tk.StringVar(
            value=f"{self.settings.cooldown_seconds:g}"
        )
        self.ignore_bottom_var = tk.StringVar(
            value=f"{self.settings.ignore_bottom_percent:g}"
        )
        self.volume_var = tk.DoubleVar(value=self.settings.volume * 100.0)
        self.require_person_var = tk.BooleanVar(
            value=self.settings.require_person
        )
        self.status_var = tk.StringVar(value="Ready to start a work session")
        self.detail_var = tk.StringVar(
            value="Your camera stays off until you press Start."
        )
        self.progress_var = tk.DoubleVar(value=0.0)

        self._build_styles()
        self._build_ui()
        self.root.bind("<Escape>", lambda _event: self._dismiss())
        self.root.after(50, self._poll_updates)

    def _build_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=self.BG)
        style.configure("Panel.TFrame", background=self.PANEL)
        style.configure(
            "TLabel",
            background=self.BG,
            foreground=self.TEXT,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Panel.TLabel",
            background=self.PANEL,
            foreground=self.TEXT,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Muted.TLabel",
            background=self.PANEL,
            foreground=self.MUTED,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Title.TLabel",
            background=self.BG,
            foreground=self.TEXT,
            font=("Segoe UI Semibold", 22),
        )
        style.configure(
            "Status.TLabel",
            background=self.PANEL,
            foreground=self.GREEN,
            font=("Segoe UI Semibold", 15),
        )
        style.configure(
            "TButton",
            font=("Segoe UI Semibold", 10),
            padding=(12, 8),
        )
        style.configure(
            "Primary.TButton",
            background=self.BLUE,
            foreground="#07111f",
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#8bc0ff"), ("disabled", "#394456")],
        )
        style.configure(
            "Danger.TButton",
            background=self.RED,
            foreground="#25060a",
        )
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor="#252c39",
            background=self.ORANGE,
            bordercolor="#252c39",
            lightcolor=self.ORANGE,
            darkcolor=self.ORANGE,
        )
        style.configure(
            "TCheckbutton",
            background=self.PANEL,
            foreground=self.TEXT,
        )
        style.map("TCheckbutton", background=[("active", self.PANEL)])

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 14))
        ttk.Label(header, text="Focus Guard", style="Title.TLabel").pack(
            side="left"
        )
        ttk.Label(
            header,
            text="Local phone-distraction reminder",
            foreground=self.MUTED,
        ).pack(side="left", padx=(14, 0), pady=(8, 0))

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        preview_panel = ttk.Frame(
            body, style="Panel.TFrame", padding=12
        )
        preview_panel.grid(
            row=0, column=0, sticky="nsew", padx=(0, 14)
        )
        preview_panel.rowconfigure(0, weight=1)
        preview_panel.columnconfigure(0, weight=1)

        self.preview_label = tk.Label(
            preview_panel,
            text="Camera preview\n\nPress Start when your work session begins.",
            bg="#090b10",
            fg=self.MUTED,
            font=("Segoe UI", 13),
            justify="center",
        )
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        status_box = ttk.Frame(
            preview_panel, style="Panel.TFrame", padding=(4, 12, 4, 0)
        )
        status_box.grid(row=1, column=0, sticky="ew")
        self.status_label = ttk.Label(
            status_box,
            textvariable=self.status_var,
            style="Status.TLabel",
        )
        self.status_label.pack(anchor="w")
        ttk.Label(
            status_box,
            textvariable=self.detail_var,
            style="Muted.TLabel",
            wraplength=760,
        ).pack(anchor="w", pady=(3, 8))
        ttk.Progressbar(
            status_box,
            variable=self.progress_var,
            maximum=100.0,
        ).pack(fill="x")

        controls = ttk.Frame(body, style="Panel.TFrame", padding=18)
        controls.grid(row=0, column=1, sticky="nsew")
        controls.columnconfigure(0, weight=1)

        row = 0
        ttk.Label(
            controls,
            text="Reminder song",
            style="Panel.TLabel",
            font=("Segoe UI Semibold", 11),
        ).grid(row=row, column=0, sticky="w")
        row += 1
        self.song_label = ttk.Label(
            controls,
            text=self._song_display_name(),
            style="Muted.TLabel",
            wraplength=280,
        )
        self.song_label.grid(row=row, column=0, sticky="ew", pady=(4, 8))
        row += 1
        song_buttons = ttk.Frame(controls, style="Panel.TFrame")
        song_buttons.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        self.choose_song_button = ttk.Button(
            song_buttons, text="Choose file", command=self._choose_song
        )
        self.choose_song_button.pack(side="left")
        self.test_song_button = ttk.Button(
            song_buttons, text="Test", command=self._test_song
        )
        self.test_song_button.pack(side="left", padx=(8, 0))

        row += 1
        ttk.Separator(controls).grid(
            row=row, column=0, sticky="ew", pady=(0, 14)
        )
        row += 1
        settings_grid = ttk.Frame(controls, style="Panel.TFrame")
        settings_grid.grid(row=row, column=0, sticky="ew")
        settings_grid.columnconfigure(1, weight=1)

        setting_rows = [
            ("Camera", self.camera_var, 0, 10, 1),
            ("Trigger after (s)", self.trigger_var, 1, 120, 1),
            ("Clear after (s)", self.clear_var, 0.5, 30, 0.5),
            ("Confidence", self.confidence_var, 0.1, 0.95, 0.05),
            ("Cooldown (s)", self.cooldown_var, 0, 3600, 10),
            (
                "Ignore bottom (%)",
                self.ignore_bottom_var,
                0,
                60,
                1,
            ),
        ]
        for index, (label, variable, low, high, step) in enumerate(
            setting_rows
        ):
            ttk.Label(
                settings_grid, text=label, style="Panel.TLabel"
            ).grid(row=index, column=0, sticky="w", pady=4)
            ttk.Spinbox(
                settings_grid,
                textvariable=variable,
                from_=low,
                to=high,
                increment=step,
                width=9,
            ).grid(row=index, column=1, sticky="e", pady=4)

        volume_row = len(setting_rows)
        ttk.Label(
            settings_grid, text="Volume", style="Panel.TLabel"
        ).grid(row=volume_row, column=0, sticky="w", pady=4)
        ttk.Scale(
            settings_grid,
            variable=self.volume_var,
            from_=0,
            to=100,
            orient="horizontal",
        ).grid(row=volume_row, column=1, sticky="ew", pady=4)

        ttk.Checkbutton(
            settings_grid,
            text="Require phone near primary person",
            variable=self.require_person_var,
        ).grid(
            row=volume_row + 1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(9, 0),
        )

        row += 1
        ttk.Label(
            controls,
            text=(
                "The shaded bottom strip is ignored, so a phone parked on "
                "your desk is less likely to trigger."
            ),
            style="Muted.TLabel",
            wraplength=280,
        ).grid(row=row, column=0, sticky="ew", pady=(8, 14))

        row += 1
        self.start_button = ttk.Button(
            controls,
            text="Start work session",
            style="Primary.TButton",
            command=self._start,
        )
        self.start_button.grid(row=row, column=0, sticky="ew")

        row += 1
        self.stop_button = ttk.Button(
            controls,
            text="Stop session",
            command=self._stop,
            state="disabled",
        )
        self.stop_button.grid(row=row, column=0, sticky="ew", pady=(8, 0))

        row += 1
        actions = ttk.Frame(controls, style="Panel.TFrame")
        actions.grid(row=row, column=0, sticky="ew", pady=(12, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        self.dismiss_button = ttk.Button(
            actions,
            text="I'm back",
            command=self._dismiss,
            state="disabled",
        )
        self.dismiss_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.snooze_button = ttk.Button(
            actions,
            text="Snooze 5 min",
            command=self._snooze,
            state="disabled",
        )
        self.snooze_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        row += 1
        ttk.Label(
            controls,
            text=(
                "Privacy: frames are processed in memory on this computer. "
                "Nothing is recorded or uploaded."
            ),
            style="Muted.TLabel",
            wraplength=280,
        ).grid(row=row, column=0, sticky="sew", pady=(20, 0))
        controls.rowconfigure(row, weight=1)

    def _read_settings(self) -> AppSettings:
        try:
            settings = AppSettings(
                camera_index=int(float(self.camera_var.get())),
                song_path=self.song_var.get(),
                model_name=self.settings.model_name,
                confidence=float(self.confidence_var.get()),
                trigger_seconds=float(self.trigger_var.get()),
                clear_seconds=float(self.clear_var.get()),
                cooldown_seconds=float(self.cooldown_var.get()),
                inference_fps=self.settings.inference_fps,
                volume=float(self.volume_var.get()) / 100.0,
                ignore_bottom_percent=float(self.ignore_bottom_var.get()),
                require_person=self.require_person_var.get(),
            ).normalized()
        except ValueError as exc:
            raise ValueError(
                "One of the numeric settings is invalid. Use numbers only."
            ) from exc
        return settings

    def _start(self) -> None:
        if (
            self.audio_test_running
            or (self.worker is not None and self.worker.is_alive())
        ):
            return
        try:
            self.settings = self._read_settings()
            save_settings(self.settings)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        if (
            self.settings.song_path
            and not Path(self.settings.song_path).is_file()
        ):
            messagebox.showerror(
                "Song not found",
                "Choose an existing MP3, OGG, or WAV file first.",
            )
            return

        self._clear_queues()
        self.worker = MonitoringWorker(
            self.settings, self.updates, self.commands
        )
        self.worker.start()
        self.start_button.configure(state="disabled")
        self.choose_song_button.configure(state="disabled")
        self.test_song_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.dismiss_button.configure(state="normal")
        self.snooze_button.configure(state="normal")
        self.status_var.set("Starting...")
        self.detail_var.set(
            "The first run may download the small detection model."
        )

    def _stop(self) -> None:
        if self.worker is not None:
            self.worker.request_stop()
        self.stop_button.configure(state="disabled")
        self.dismiss_button.configure(state="disabled")
        self.snooze_button.configure(state="disabled")
        self.status_var.set("Stopping...")
        self.detail_var.set("Releasing the camera and audio output.")

    def _dismiss(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            self.commands.put(("dismiss", None))

    def _snooze(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            self.commands.put(("snooze", 5 * 60.0))

    def _choose_song(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose your reminder song",
            filetypes=[
                ("Audio files", "*.mp3 *.ogg *.wav"),
                ("MP3", "*.mp3"),
                ("Ogg Vorbis", "*.ogg"),
                ("Wave audio", "*.wav"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return
        self.song_var.set(selected)
        self.song_label.configure(text=self._song_display_name())
        try:
            self.settings = self._read_settings()
            save_settings(self.settings)
        except (ValueError, OSError):
            pass

    def _test_song(self) -> None:
        if self.audio_test_running:
            return
        if self.worker is not None and self.worker.is_alive():
            self.detail_var.set("Stop the work session before testing audio.")
            return
        try:
            settings = self._read_settings()
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        self.audio_test_running = True
        self.start_button.configure(state="disabled")
        self.choose_song_button.configure(state="disabled")
        self.test_song_button.configure(state="disabled")
        self.detail_var.set("Playing a five-second audio test...")

        def play() -> None:
            player = AudioPlayer(settings.song_path, settings.volume)
            message = ""
            try:
                player.play()
                deadline = time.monotonic() + 5.0
                while player.is_playing() and time.monotonic() < deadline:
                    time.sleep(0.2)
            except AudioError as exc:
                message = f"Audio test failed: {exc}"
            finally:
                player.close()
                if not message:
                    message = "Audio test finished."
                self._put_app_update(
                    MonitorUpdate(
                        message=message,
                        audio_test_finished=True,
                    )
                )

        threading.Thread(target=play, daemon=True).start()

    def _put_app_update(self, update: MonitorUpdate) -> None:
        try:
            self.updates.put_nowait(update)
            return
        except queue.Full:
            pass
        try:
            self.updates.get_nowait()
        except queue.Empty:
            pass
        try:
            self.updates.put_nowait(update)
        except queue.Full:
            pass

    def _poll_updates(self) -> None:
        newest: MonitorUpdate | None = None
        while True:
            try:
                newest = self.updates.get_nowait()
            except queue.Empty:
                break

        if newest is not None:
            self._apply_update(newest)
        self.root.after(50, self._poll_updates)

    def _apply_update(self, update: MonitorUpdate) -> None:
        if update.frame_rgb is not None:
            image = Image.fromarray(update.frame_rgb)
            self.preview_image = ImageTk.PhotoImage(image=image)
            self.preview_label.configure(
                image=self.preview_image,
                text="",
            )

        if update.snapshot is not None:
            snapshot = update.snapshot
            self.progress_var.set(snapshot.progress * 100.0)
            self.status_var.set(snapshot.phase.value)
            detail = update.detector_reason
            if snapshot.phase == Phase.SUSPECTED:
                remaining = max(
                    0.0,
                    self.settings.trigger_seconds
                    - snapshot.evidence_seconds,
                )
                detail = f"{detail} · reminder in {remaining:.1f}s"
            elif snapshot.phase == Phase.COOLDOWN:
                detail = f"Re-arming in {snapshot.cooldown_remaining:.0f}s"
                if update.message.startswith("Nice"):
                    detail = f"{update.message} · {detail}"
            elif snapshot.phase == Phase.SNOOZED:
                detail = f"Snoozed for {snapshot.snooze_remaining:.0f}s"
            elif snapshot.phase == Phase.ALERT:
                detail = "Put the phone down; audio stops after it is clear."
            elif snapshot.phase == Phase.WAITING_FOR_CLEAR:
                detail = "Move the phone out of view to re-arm the reminder."

            if update.message and snapshot.phase in {
                Phase.FOCUSED,
                Phase.ALERT,
            }:
                detail = update.message
            self.detail_var.set(detail)
            self._color_status(snapshot.phase)
        elif update.message:
            self.detail_var.set(update.message)

        if update.audio_test_finished:
            self.audio_test_running = False
            if self.worker is None:
                self.start_button.configure(state="normal")
                self.choose_song_button.configure(state="normal")
                self.test_song_button.configure(state="normal")

        if update.fatal_error:
            self.status_var.set("Session error")
            self.detail_var.set(update.fatal_error)
            self.status_label.configure(foreground=self.RED)
            messagebox.showerror("Focus Guard", update.fatal_error)

        if update.stopped:
            self.worker = None
            self.start_button.configure(state="normal")
            self.choose_song_button.configure(state="normal")
            self.test_song_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            self.dismiss_button.configure(state="disabled")
            self.snooze_button.configure(state="disabled")
            if not update.fatal_error:
                self.status_var.set("Session stopped")
                self.detail_var.set(
                    "Camera released. Press Start for another work session."
                )
                self.status_label.configure(foreground=self.MUTED)
            self.progress_var.set(0.0)

    def _color_status(self, phase: Phase) -> None:
        colors = {
            Phase.FOCUSED: self.GREEN,
            Phase.SUSPECTED: self.ORANGE,
            Phase.ALERT: self.RED,
            Phase.COOLDOWN: self.BLUE,
            Phase.WAITING_FOR_CLEAR: self.ORANGE,
            Phase.SNOOZED: self.BLUE,
        }
        self.status_label.configure(foreground=colors[phase])

    def _song_display_name(self) -> str:
        path = self.song_var.get().strip()
        if not path:
            return "No file selected — system beep fallback"
        return Path(path).name

    def _clear_queues(self) -> None:
        for target_queue in (self.updates, self.commands):
            while True:
                try:
                    target_queue.get_nowait()
                except queue.Empty:
                    break

    def _on_close(self) -> None:
        if self.worker is not None:
            self.worker.request_stop()
            self.worker.join(timeout=2.0)
        self.root.destroy()


def run_app() -> None:
    root = tk.Tk()
    FocusGuardApp(root)
    root.mainloop()
