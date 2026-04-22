import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from fastapi import UploadFile
from fastapi.testclient import TestClient

from server.app import config, db
from server.app.config import gemini_model_choices, get_settings
from server.app.main import app, format_analysis_error, parse_analysis
from server.app.services import activity_log, diagnostics, export_store, observation_cleanup
from server.app.services.connectivity import is_private_lan_ip, is_tailscale_ip, tailscale_https_urls_from_status
from server.app.services.gemini_cli import needs_gemini_auth, normalize_result, strip_model_args
from server.app.services.image_store import save_observation_images, looks_like_supported_image


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self._originals = {
            "config_data_dir": config.DATA_DIR,
            "config_image_dir": config.IMAGE_DIR,
            "config_log_dir": config.LOG_DIR,
            "config_export_dir": config.EXPORT_DIR,
            "config_db_path": config.DB_PATH,
            "db_path": db.DB_PATH,
            "export_db_path": export_store.DB_PATH,
            "export_image_dir": export_store.IMAGE_DIR,
            "export_export_dir": export_store.EXPORT_DIR,
            "cleanup_image_dir": observation_cleanup.IMAGE_DIR,
            "activity_log_dir": activity_log.LOG_DIR,
            "diagnostics_image_dir": diagnostics.IMAGE_DIR,
            "diagnostics_log_dir": diagnostics.LOG_DIR,
            "diagnostics_export_dir": diagnostics.EXPORT_DIR,
            "diagnostics_db_path": diagnostics.DB_PATH,
        }

    def tearDown(self):
        config.DATA_DIR = self._originals["config_data_dir"]
        config.IMAGE_DIR = self._originals["config_image_dir"]
        config.LOG_DIR = self._originals["config_log_dir"]
        config.EXPORT_DIR = self._originals["config_export_dir"]
        config.DB_PATH = self._originals["config_db_path"]
        db.DB_PATH = self._originals["db_path"]
        export_store.DB_PATH = self._originals["export_db_path"]
        export_store.IMAGE_DIR = self._originals["export_image_dir"]
        export_store.EXPORT_DIR = self._originals["export_export_dir"]
        observation_cleanup.IMAGE_DIR = self._originals["cleanup_image_dir"]
        activity_log.LOG_DIR = self._originals["activity_log_dir"]
        diagnostics.IMAGE_DIR = self._originals["diagnostics_image_dir"]
        diagnostics.LOG_DIR = self._originals["diagnostics_log_dir"]
        diagnostics.EXPORT_DIR = self._originals["diagnostics_export_dir"]
        diagnostics.DB_PATH = self._originals["diagnostics_db_path"]

    def test_image_signature_detection(self):
        self.assertTrue(looks_like_supported_image(b"\xff\xd8\xffabc", ".jpg"))
        self.assertTrue(looks_like_supported_image(b"\x89PNG\r\n\x1a\nabc", ".png"))
        self.assertTrue(looks_like_supported_image(b"RIFF1234WEBPabc", ".webp"))
        self.assertFalse(looks_like_supported_image(b"not image", ".jpg"))

    def test_save_observation_accepts_one_to_three_images(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            for count in [1, 2, 3]:
                files = [
                    UploadFile(filename=f"{index}.jpg", file=BytesIO(b"\xff\xd8\xfftest"))
                    for index in range(count)
                ]
                observation_id, paths = self._run_async(save_observation_images(files))
                self.assertTrue(observation_id)
                self.assertEqual(len(paths), count)
                self.assertTrue(all(path.exists() for path in paths))

    def test_tailscale_ip_detection(self):
        self.assertTrue(is_tailscale_ip("100.64.0.1"))
        self.assertTrue(is_tailscale_ip("100.127.255.254"))
        self.assertFalse(is_tailscale_ip("192.168.0.10"))
        self.assertTrue(is_private_lan_ip("192.168.0.10"))
        self.assertFalse(is_private_lan_ip("100.64.0.1"))

    def test_tailscale_https_url_from_status(self):
        status = {"Self": {"DNSName": "desktop-example.tailnet.ts.net."}}
        self.assertEqual(
            tailscale_https_urls_from_status(status),
            ["https://desktop-example.tailnet.ts.net/"],
        )

    def test_candidate_confidence_sum_is_normalized(self):
        result = normalize_result(
            {
                "confidence": "95%",
                "candidates": [
                    {"common_name_ja": "A", "confidence": 0.9, "reason": "a"},
                    {"common_name_ja": "B", "confidence": 0.8, "reason": "b"},
                    {"common_name_ja": "C", "confidence": 80, "reason": "c"},
                ],
                "visible_features": ["one"],
            }
        )
        self.assertEqual(result["confidence"], 0.95)
        total = sum(candidate["confidence"] for candidate in result["candidates"])
        self.assertAlmostEqual(total, 1.0)

    def test_manual_correction_preserves_ai_candidates(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            image_paths = self._create_fake_images("obs-correct")
            db.create_observation(
                observation_id="obs-correct",
                image_paths=image_paths,
                captured_at=None,
                note="before",
                location_label="old",
                latitude=None,
                longitude=None,
            )
            db.save_analysis_result(
                "obs-correct",
                {
                    "common_name_ja": "旧名",
                    "scientific_name": "Old name",
                    "confidence": 0.8,
                    "candidates": [
                        {"common_name_ja": "旧名", "scientific_name": "Old name", "confidence": 0.7, "reason": "first"},
                        {"common_name_ja": "別候補", "scientific_name": "Alt name", "confidence": 0.3, "reason": "second"},
                    ],
                },
            )
            db.apply_manual_correction(
                observation_id="obs-correct",
                common_name_ja="新名",
                scientific_name="New name",
                note="after",
                location_label="new",
            )
            observation = db.get_observation("obs-correct")
            analysis = parse_analysis(observation["raw_result_json"])
            self.assertEqual(analysis["candidates"][0]["common_name_ja"], "新名")
            self.assertEqual(len(analysis["ai_candidates"]), 2)

    def test_export_zip_contains_database_images_and_manifest(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            config.ensure_data_dirs()
            db.init_db()
            image_dir = config.IMAGE_DIR / "obs"
            image_dir.mkdir(parents=True)
            (image_dir / "1.jpg").write_bytes(b"fake")

            output_path = export_store.create_export_zip()
            with ZipFile(output_path) as archive:
                names = set(archive.namelist())

            self.assertIn("plants.sqlite", names)
            self.assertIn("images/obs/1.jpg", names)
            self.assertIn("manifest.json", names)

    def test_delete_observation_removes_images(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            image_paths = self._create_fake_images("obs-delete")
            db.create_observation(
                observation_id="obs-delete",
                image_paths=image_paths,
                captured_at=None,
                note=None,
                location_label=None,
                latitude=None,
                longitude=None,
            )
            db.save_analysis_result(
                "obs-delete",
                {
                    "common_name_ja": "削除テスト",
                    "scientific_name": "Delete test",
                    "confidence": 0.8,
                    "candidates": [],
                },
            )
            client = TestClient(app)
            response = client.delete(
                "/api/observations/obs-delete",
                headers={"X-Plant-Dex-Api-Key": get_settings().api_key},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(db.get_observation("obs-delete"))
            self.assertFalse((config.IMAGE_DIR / "obs-delete").exists())

    def test_main_pages_render(self):
        client = TestClient(app)
        for path in ["/", "/plants", "/settings", "/connect", "/diagnostics", "/upload", "/observations", "/review", "/export"]:
            with self.subTest(path=path):
                self.assertEqual(client.get(path).status_code, 200)

    def test_diagnostics_api_reports_checks(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            client = TestClient(app)
            response = client.get("/api/diagnostics")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIn("checks", payload)
            self.assertIn("connectivity", payload)
            self.assertTrue(any(item["key"] == "image_dir" for item in payload["checks"]))

    def test_timeout_error_is_user_friendly(self):
        message = format_analysis_error(RuntimeError("Command '['gemini']' timed out after 300 seconds"))
        self.assertEqual(
            message,
            "Gemini CLIがタイムアウトしました。Gemini CLIのログイン状態、APIキー、通信状態を確認してから再解析してください。",
        )

    def test_gemini_auth_prompt_is_detected(self):
        self.assertTrue(needs_gemini_auth("Opening authentication page in your browser.", ""))
        self.assertTrue(needs_gemini_auth("Do you want to continue? [Y/n]:", ""))
        self.assertFalse(needs_gemini_auth('{"ok": true}', ""))

    def test_gemini_model_choices_include_cli_models(self):
        values = [item["value"] for item in gemini_model_choices()]
        self.assertIn("gemini-3-flash-preview", values)
        self.assertIn("gemini-3.1-pro-preview", values)
        self.assertIn("gemini-2.5-flash-lite", values)

    def test_strip_model_args_allows_request_override(self):
        self.assertEqual(
            strip_model_args(["gemini", "--model", "gemini-2.5-pro", "--yolo"]),
            ["gemini", "--yolo"],
        )
        self.assertEqual(
            strip_model_args(["gemini", "--model=gemini-2.5-flash", "-p", "x"]),
            ["gemini", "-p", "x"],
        )

    def test_location_labels_can_be_added_and_removed(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            client = TestClient(app)
            response = client.post(
                "/api/settings/location-labels",
                data={"label": "北庭"},
                headers={"X-Plant-Dex-Api-Key": get_settings().api_key},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("北庭", response.json()["location_labels"])

            response = client.delete(
                "/api/settings/location-labels/%E5%8C%97%E5%BA%AD",
                headers={"X-Plant-Dex-Api-Key": get_settings().api_key},
            )
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("北庭", response.json()["location_labels"])

    def test_activity_log_writes_file(self):
        with TemporaryDirectory() as tmp:
            activity_log.LOG_DIR = Path(tmp)
            activity_log.write_log("test_event ok")
            content = (Path(tmp) / "server.log").read_text(encoding="utf-8")
            self.assertIn("test_event ok", content)

    def _use_temp_data_dir(self, tmp: str) -> None:
        root = Path(tmp) / "data"
        config.DATA_DIR = root
        config.IMAGE_DIR = root / "images"
        config.LOG_DIR = root / "logs"
        config.EXPORT_DIR = root / "exports"
        config.DB_PATH = root / "plants.sqlite"
        db.DB_PATH = config.DB_PATH
        export_store.DB_PATH = config.DB_PATH
        export_store.IMAGE_DIR = config.IMAGE_DIR
        export_store.EXPORT_DIR = config.EXPORT_DIR
        observation_cleanup.IMAGE_DIR = config.IMAGE_DIR
        diagnostics.IMAGE_DIR = config.IMAGE_DIR
        diagnostics.LOG_DIR = config.LOG_DIR
        diagnostics.EXPORT_DIR = config.EXPORT_DIR
        diagnostics.DB_PATH = config.DB_PATH
        config.ensure_data_dirs()
        db.init_db()

    def _create_fake_images(self, observation_id: str) -> list[Path]:
        observation_dir = config.IMAGE_DIR / observation_id
        observation_dir.mkdir(parents=True)
        paths = [observation_dir / f"{index}.jpg" for index in range(1, 4)]
        for path in paths:
            path.write_bytes(b"test")
        return paths

    def _run_async(self, coroutine):
        import asyncio

        return asyncio.run(coroutine)


if __name__ == "__main__":
    unittest.main()
