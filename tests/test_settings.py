from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from focus_guard import settings as settings_module
from focus_guard.settings import AppSettings


class SettingsPathTests(unittest.TestCase):
    def test_windows_path_uses_local_app_data(self) -> None:
        local_app_data = Path("C:/Users/tester/AppData/Local")

        path = settings_module.get_default_settings_path(
            platform="win32",
            environment={"LOCALAPPDATA": str(local_app_data)},
        )

        self.assertEqual(
            path,
            local_app_data / "Focus Guard" / "settings.json",
        )

    def test_windows_path_falls_back_when_local_app_data_is_missing(self) -> None:
        path = settings_module.get_default_settings_path(
            platform="win32",
            environment={},
        )

        self.assertEqual(path, settings_module.LEGACY_SETTINGS_PATH)

    def test_non_windows_path_preserves_existing_behavior(self) -> None:
        path = settings_module.get_default_settings_path(
            platform="linux",
            environment={"LOCALAPPDATA": "ignored"},
        )

        self.assertEqual(path, settings_module.LEGACY_SETTINGS_PATH)


class SettingsPersistenceTests(unittest.TestCase):
    def test_save_creates_parent_directory_and_loads_normalized_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "nested" / "settings.json"

            settings_module.save_settings(
                AppSettings(confidence=2.0, song_path=" song.mp3 "),
                path,
            )

            loaded = settings_module.load_settings(path)
            self.assertEqual(loaded.confidence, 0.95)
            self.assertEqual(loaded.song_path, "song.mp3")

    def test_default_load_migrates_legacy_settings_without_removing_them(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            legacy_path = root / "legacy" / "settings.json"
            default_path = root / "local-app-data" / "settings.json"
            expected = AppSettings(camera_index=2, volume=0.35)
            settings_module.save_settings(expected, legacy_path)

            with (
                mock.patch.object(
                    settings_module, "LEGACY_SETTINGS_PATH", legacy_path
                ),
                mock.patch.object(
                    settings_module, "DEFAULT_SETTINGS_PATH", default_path
                ),
            ):
                loaded = settings_module.load_settings()

            self.assertEqual(loaded, expected)
            self.assertTrue(legacy_path.exists())
            self.assertEqual(settings_module.load_settings(default_path), expected)

    def test_migration_uses_legacy_values_when_new_path_cannot_be_written(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            legacy_path = root / "legacy-settings.json"
            default_path = root / "local-app-data" / "settings.json"
            expected = AppSettings(trigger_seconds=9.0)
            settings_module.save_settings(expected, legacy_path)

            with (
                mock.patch.object(
                    settings_module, "LEGACY_SETTINGS_PATH", legacy_path
                ),
                mock.patch.object(
                    settings_module, "DEFAULT_SETTINGS_PATH", default_path
                ),
                mock.patch.object(
                    settings_module,
                    "save_settings",
                    side_effect=OSError("read-only directory"),
                ),
            ):
                loaded = settings_module.load_settings()

            self.assertEqual(loaded, expected)
            self.assertFalse(default_path.exists())
            self.assertTrue(legacy_path.exists())

    def test_invalid_legacy_file_is_not_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            legacy_path = root / "legacy-settings.json"
            default_path = root / "local-app-data" / "settings.json"
            legacy_path.write_text("[]", encoding="utf-8")

            with (
                mock.patch.object(
                    settings_module, "LEGACY_SETTINGS_PATH", legacy_path
                ),
                mock.patch.object(
                    settings_module, "DEFAULT_SETTINGS_PATH", default_path
                ),
            ):
                loaded = settings_module.load_settings()

            self.assertEqual(loaded, AppSettings())
            self.assertFalse(default_path.exists())
            self.assertEqual(
                json.loads(legacy_path.read_text(encoding="utf-8")),
                [],
            )


if __name__ == "__main__":
    unittest.main()
