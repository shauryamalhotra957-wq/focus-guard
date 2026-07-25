from __future__ import annotations

import threading
from pathlib import Path


class AudioError(RuntimeError):
    pass


class AudioPlayer:
    """Single-stream audio player. Calls are serialized to avoid overlap."""

    def __init__(self, song_path: str, volume: float) -> None:
        self.song_path = Path(song_path).expanduser() if song_path else None
        self.volume = min(1.0, max(0.0, volume))
        self._initialized = False
        self._lock = threading.Lock()

    def play(self) -> str:
        with self._lock:
            if self.song_path is None:
                self._system_beep()
                return "No song selected; played the system alert instead."
            if not self.song_path.is_file():
                raise AudioError(f"Song file not found: {self.song_path}")

            pygame = self._pygame()
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.load(str(self.song_path))
                pygame.mixer.music.set_volume(self.volume)
                pygame.mixer.music.play(loops=0)
            except Exception as exc:
                raise AudioError(f"Could not play the song: {exc}") from exc
            return f"Playing {self.song_path.name}"

    def stop(self) -> None:
        with self._lock:
            if not self._initialized:
                return
            try:
                self._pygame().mixer.music.stop()
            except Exception:
                pass

    def is_playing(self) -> bool:
        with self._lock:
            if not self._initialized:
                return False
            try:
                return bool(self._pygame().mixer.music.get_busy())
            except Exception:
                return False

    def close(self) -> None:
        with self._lock:
            if not self._initialized:
                return
            try:
                pygame = self._pygame()
                pygame.mixer.music.stop()
                pygame.mixer.quit()
            except Exception:
                pass
            finally:
                self._initialized = False

    def _pygame(self):
        import pygame

        if not self._initialized:
            try:
                pygame.mixer.init()
            except Exception as exc:
                raise AudioError(f"Audio output is unavailable: {exc}") from exc
            self._initialized = True
        return pygame

    @staticmethod
    def _system_beep() -> None:
        try:
            import winsound

            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except (ImportError, RuntimeError):
            pass
