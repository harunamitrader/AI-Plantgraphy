import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

from fastapi import UploadFile
from fastapi.testclient import TestClient
from PIL import Image

from server.app import config, db, main
from server.app.config import gemini_model_choices, get_settings
from server.app.main import app, format_analysis_error, parse_analysis
from server.app.services import activity_log, diagnostics, export_store, observation_cleanup
from server.app.services.connectivity import is_private_lan_ip, is_tailscale_ip, tailscale_https_urls_from_status
from server.app.services.gemini_cli import (
    analyze_images,
    build_identifier_prompt,
    build_identifier_retry_prompt,
    extract_forbidden_top_level_keys,
    extract_gemini_response,
    generate_plant_profile,
    needs_gemini_auth,
    normalize_result,
    parse_json_output,
    resolve_plant_identity_from_name,
    strip_model_args,
    validate_identifier_payload,
)
from server.app.services.image_store import MAX_IMAGE_EDGE, save_observation_images, looks_like_supported_image


class ServiceTests(unittest.TestCase):
    def setUp(self):
        main.ANALYSIS_PROGRESS.clear()
        main.ANALYSIS_RUNS.clear()
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
        main.ANALYSIS_PROGRESS.clear()
        main.ANALYSIS_RUNS.clear()
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
                    UploadFile(filename=f"{index}.jpg", file=BytesIO(self._jpeg_bytes(size=(640, 480))))
                    for index in range(count)
                ]
                observation_id, paths = self._run_async(save_observation_images(files))
                self.assertTrue(observation_id)
                self.assertEqual(len(paths), count)
                self.assertTrue(all(path.exists() for path in paths))
                self.assertTrue(all(path.suffix == ".jpg" for path in paths))

    def test_save_observation_optimizes_large_images(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            files = [
                UploadFile(filename="large.png", file=BytesIO(self._png_bytes(size=(2400, 1800))))
            ]
            _, paths = self._run_async(save_observation_images(files))
            self.assertEqual(paths[0].suffix, ".jpg")
            with Image.open(paths[0]) as image:
                self.assertLessEqual(max(image.size), MAX_IMAGE_EDGE)
                self.assertEqual(image.format, "JPEG")

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

    def test_delete_plant_keeps_observations_and_clears_relation(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            image_paths = self._create_fake_images("obs-plant-delete")
            db.create_observation(
                observation_id="obs-plant-delete",
                image_paths=image_paths,
                captured_at=None,
                note=None,
                location_label=None,
                latitude=None,
                longitude=None,
            )
            plant_id = db.save_analysis_result(
                "obs-plant-delete",
                {
                    "common_name_ja": "削除テスト植物",
                    "scientific_name": "Delete plant",
                    "confidence": 0.91,
                    "candidates": [],
                },
            )
            client = TestClient(app)
            response = client.delete(
                f"/api/plants/{plant_id}",
                headers={"X-Plant-Dex-Api-Key": get_settings().api_key},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(db.get_plant(plant_id))
            observation = db.get_observation("obs-plant-delete")
            self.assertIsNotNone(observation)
            self.assertIsNone(observation["plant_id"])

    def test_restore_plant_from_observation_recreates_relation(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            image_paths = self._create_fake_images("obs-plant-restore")
            db.create_observation(
                observation_id="obs-plant-restore",
                image_paths=image_paths,
                captured_at=None,
                note=None,
                location_label=None,
                latitude=None,
                longitude=None,
            )
            original_plant_id = db.save_analysis_result(
                "obs-plant-restore",
                {
                    "common_name_ja": "復元植物",
                    "scientific_name": "Restore plant",
                    "confidence": 0.82,
                    "candidates": [],
                },
            )
            db.delete_plant(original_plant_id)

            client = TestClient(app)
            response = client.post(
                "/api/observations/obs-plant-restore/restore-plant",
                headers={"X-Plant-Dex-Api-Key": get_settings().api_key},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "restored")
            observation = db.get_observation("obs-plant-restore")
            self.assertTrue(observation["plant_id"])
            self.assertIsNotNone(db.get_plant(observation["plant_id"]))

    def test_create_manual_plant_generates_library_entry_without_observation(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            client = TestClient(app)
            with patch(
                "server.app.main.resolve_plant_identity_from_name",
                return_value={
                    "common_name_ja": "シクラメン",
                    "scientific_name": "Cyclamen persicum",
                    "confidence": 0.94,
                    "uncertainty_notes": "",
                },
            ), patch(
                "server.app.main.generate_plant_profile",
                return_value={
                    "basic_profile_text": "冬から春に花を楽しめる多年草です。",
                    "visual_appeal_text": "反り返る花弁と模様のある葉が魅力です。",
                    "care_notes": "風通しのよい明るい場所で管理します。",
                },
            ):
                response = client.post(
                    "/api/plants",
                    headers={"X-Plant-Dex-Api-Key": get_settings().api_key},
                    data={"common_name_ja": "シクラメン"},
                )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "created")
            plant = payload["plant"]
            self.assertEqual(plant["display_name"], "シクラメン")
            self.assertEqual(plant["scientific_name"], "Cyclamen persicum")
            stored = db.get_plant(plant["id"])
            self.assertIsNotNone(stored)
            self.assertEqual(stored["observation_count"], 0)
            self.assertEqual(stored["care_notes"], "風通しのよい明るい場所で管理します。")

    def test_create_manual_plant_returns_existing_without_generating(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            plant_id = db.upsert_manual_plant(
                common_name_ja="シクラメン",
                scientific_name="Cyclamen persicum",
                profile={
                    "basic_profile_text": "既存の基本特徴",
                    "visual_appeal_text": "既存の見た目",
                    "care_notes": "既存の手入れ",
                },
            )
            client = TestClient(app)
            with patch("server.app.main.resolve_plant_identity_from_name") as mocked_identity, patch(
                "server.app.main.generate_plant_profile"
            ) as mocked_profile:
                response = client.post(
                    "/api/plants",
                    headers={"X-Plant-Dex-Api-Key": get_settings().api_key},
                    data={"common_name_ja": "シクラメン"},
                )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "exists")
            self.assertEqual(payload["plant"]["id"], plant_id)
            mocked_identity.assert_not_called()
            mocked_profile.assert_not_called()

    def test_create_manual_plant_rejects_name_only_when_identity_is_uncertain(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            client = TestClient(app)
            with patch(
                "server.app.main.resolve_plant_identity_from_name",
                return_value={
                    "common_name_ja": "サツキツツジ",
                    "scientific_name": None,
                    "confidence": 0.42,
                    "uncertainty_notes": "園芸名が広く、画像なしでは断定しにくいです。",
                },
            ):
                response = client.post(
                    "/api/plants",
                    headers={"X-Plant-Dex-Api-Key": get_settings().api_key},
                    data={"common_name_ja": "サツキツツジ"},
                )

            self.assertEqual(response.status_code, 400)
            self.assertIn("学名も入力して再実行してください", response.json()["detail"])

    def test_main_pages_render(self):
        client = TestClient(app)
        for path in ["/", "/plants", "/settings", "/connect", "/diagnostics", "/upload", "/pending-local", "/observations", "/review", "/export"]:
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

    def test_bootstrap_api_reports_server_metadata(self):
        client = TestClient(app)
        response = client.get("/api/bootstrap")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["app_name"], "AI Plantgraphy")
        self.assertIn("server_name", payload)
        self.assertIn("base_url", payload)
        self.assertIn("gemini_model_choices", payload)

    def test_list_apis_return_page_data(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            image_paths = self._create_fake_images("obs-list")
            db.create_observation(
                observation_id="obs-list",
                image_paths=image_paths,
                captured_at="2026-04-27T09:00:00+09:00",
                note="庭の花",
                location_label="自宅庭",
                latitude=None,
                longitude=None,
            )
            db.save_analysis_result(
                "obs-list",
                {
                    "common_name_ja": "サクラ",
                    "scientific_name": "Cerasus x yedoensis",
                    "confidence": 0.95,
                    "candidates": [
                        {
                            "common_name_ja": "サクラ",
                            "scientific_name": "Cerasus x yedoensis",
                            "confidence": 0.95,
                            "reason": "test",
                        }
                    ],
                },
            )
            client = TestClient(app)

            plants_response = client.get("/api/plants")
            self.assertEqual(plants_response.status_code, 200)
            plant = plants_response.json()["plants"][0]
            self.assertEqual(plant["display_name"], "サクラ")
            self.assertIn("/plants/", plant["detail_url"])
            self.assertIn("/media/", plant["representative_image_url"])

            plant_detail_response = client.get(f"/api/plants/{plant['id']}")
            self.assertEqual(plant_detail_response.status_code, 200)
            plant_detail = plant_detail_response.json()
            self.assertEqual(plant_detail["plant"]["display_name"], "サクラ")
            self.assertTrue(plant_detail["photo_urls"])

            observations_response = client.get("/api/observations")
            self.assertEqual(observations_response.status_code, 200)
            observation = observations_response.json()["observations"][0]
            self.assertEqual(observation["display_name"], "サクラ")
            self.assertEqual(observation["location_label"], "自宅庭")
            self.assertIn("/observations/", observation["detail_url"])
            self.assertTrue(observation["image_urls"])

            observation_detail_response = client.get("/api/observations/obs-list")
            self.assertEqual(observation_detail_response.status_code, 200)
            observation_detail = observation_detail_response.json()
            self.assertEqual(observation_detail["display_name"], "サクラ")
            self.assertTrue(observation_detail["image_urls"])

            review_response = client.get("/api/review")
            self.assertEqual(review_response.status_code, 200)
            self.assertEqual(review_response.json()["observations"], [])

    def test_timeout_error_is_user_friendly(self):
        message = format_analysis_error(RuntimeError("Command '['gemini']' timed out after 300 seconds"))
        self.assertEqual(
            message,
            "Gemini CLIがタイムアウトしました。Gemini CLIのログイン状態、Gemini側のAPIキー、通信状態を確認してから再解析してください。",
        )

    def test_gemini_auth_prompt_is_detected(self):
        self.assertTrue(needs_gemini_auth("Opening authentication page in your browser.", ""))
        self.assertTrue(needs_gemini_auth("Do you want to continue? [Y/n]:", ""))
        self.assertFalse(needs_gemini_auth('{"ok": true}', ""))

    def test_extract_gemini_response_reads_response_field_from_json_wrapper(self):
        output = (
            'MCP issues detected. Run /mcp list for status.'
            '{"session_id":"abc","response":"{\\"common_name_ja\\":\\"アヤメ\\",\\"confidence\\":0.9}","stats":{}}'
            'YOLO mode is enabled.'
        )
        self.assertEqual(
            extract_gemini_response(output, output_format="json"),
            '{"common_name_ja":"アヤメ","confidence":0.9}',
        )

    def test_parse_json_output_handles_gemini_json_wrapper_response(self):
        wrapped = extract_gemini_response(
            'MCP issues detected. Run /mcp list for status.'
            '{"session_id":"abc","response":"{\\"common_name_ja\\":\\"アヤメ\\",\\"scientific_name\\":\\"Iris sanguinea\\",\\"confidence\\":0.9,\\"candidates\\":[],\\"visible_features\\":[],\\"uncertainty_notes\\":\\"\\"}","stats":{}}',
            output_format="json",
        )
        parsed = parse_json_output(wrapped)
        self.assertEqual(parsed["common_name_ja"], "アヤメ")
        self.assertEqual(parsed["scientific_name"], "Iris sanguinea")

    def test_build_identifier_prompt_uses_skill_contract_fields(self):
        with patch("server.app.services.gemini_cli.load_identifier_contract", return_value={
            "required_json": '{"common_name_ja":null,"scientific_name":null,"confidence":0.0,"candidates":[],"visible_features":[],"uncertainty_notes":""}',
            "forbidden_keys": ["common_name", "plant_name", "status"],
        }):
            prompt = build_identifier_prompt()

        self.assertIn("common_name_ja を使う", prompt)
        self.assertIn('{"common_name_ja":null,"scientific_name":null,"confidence":0.0,"candidates":[],"visible_features":[],"uncertainty_notes":""}', prompt)
        self.assertIn("- common_name は使わない", prompt)
        self.assertIn("- plant_name は使わない", prompt)
        self.assertIn("- status は使わない", prompt)

    def test_extract_forbidden_top_level_keys_strips_or_prefix(self):
        text = "- No alternate top-level keys such as `common_name`, `plant_name`, `observation_summary`, `characteristics`, `care_advice`, or `status`"
        self.assertEqual(
            extract_forbidden_top_level_keys(text),
            ["common_name", "plant_name", "observation_summary", "characteristics", "care_advice", "status"],
        )

    def test_validate_identifier_payload_rejects_nested_schema(self):
        violations = validate_identifier_payload(
            {
                "plant_identification": {"common_name": "キャラボク"},
                "observation_details": {"characteristics": ["密生"]},
                "confidence": 0.0,
            }
        )
        self.assertTrue(any("extra keys:" in item for item in violations))
        self.assertTrue(any("missing keys:" in item for item in violations))

    def test_build_identifier_retry_prompt_mentions_schema_violation(self):
        prompt = build_identifier_retry_prompt(["extra keys: plant_identification, observation_details"])
        self.assertIn("前回の返答はスキーマ違反でした。", prompt)
        self.assertIn("plant_identification", prompt)
        self.assertIn("common_name_ja, scientific_name, confidence, candidates, visible_features, uncertainty_notes", prompt)

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

    def test_plant_needs_profile_requires_all_three_fields(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            image_paths = self._create_fake_images("obs-profile")
            db.create_observation(
                observation_id="obs-profile",
                image_paths=image_paths,
                captured_at=None,
                note=None,
                location_label=None,
                latitude=None,
                longitude=None,
            )
            plant_id = db.save_analysis_result(
                "obs-profile",
                {
                    "common_name_ja": "プロフィール不足植物",
                    "scientific_name": "Profile test",
                    "confidence": 0.9,
                    "care_notes": "手入れだけある状態です。",
                    "candidates": [],
                },
            )
            self.assertTrue(db.plant_needs_profile(plant_id))
            db.update_plant_profile(
                plant_id,
                {
                    "basic_profile_text": "基本情報あり",
                    "visual_appeal_text": "見た目情報あり",
                    "care_notes": "手入れあり",
                },
            )
            self.assertFalse(db.plant_needs_profile(plant_id))

    def test_generate_plant_profile_uses_fallback_for_missing_basic_and_visual(self):
        responses = iter(
            [
                '{"care_notes":"日当たりの良い場所を好みます。"}',
                '{"basic_profile_text":"常緑針葉樹で低木状にまとまりやすい。","visual_appeal_text":"密な緑葉が整った球形をつくりやすい。"}',
            ]
        )

        with patch("server.app.services.gemini_cli.run_gemini_prompt", side_effect=lambda *args, **kwargs: next(responses)):
            profile = generate_plant_profile("キャラボク", "Taxus cuspidata var. nana")

        self.assertEqual(profile["care_notes"], "日当たりの良い場所を好みます。")
        self.assertTrue(profile["basic_profile_text"])
        self.assertTrue(profile["visual_appeal_text"])

    def test_generate_plant_profile_uses_fallback_for_missing_care_notes(self):
        responses = iter(
            [
                '{"basic_profile_text":"群生しやすい多年草です。","visual_appeal_text":"花色が明るく花壇で目立ちます。","care_notes":""}',
                '{"care_notes":"乾きすぎと蒸れを避け、土の表面が乾いたら水を与えます。"}',
            ]
        )

        with patch("server.app.services.gemini_cli.run_gemini_prompt", side_effect=lambda *args, **kwargs: next(responses)):
            profile = generate_plant_profile("アヤメ", "Iris sanguinea")

        self.assertEqual(profile["basic_profile_text"], "群生しやすい多年草です。")
        self.assertEqual(profile["visual_appeal_text"], "花色が明るく花壇で目立ちます。")
        self.assertEqual(profile["care_notes"], "乾きすぎと蒸れを避け、土の表面が乾いたら水を与えます。")

    def test_resolve_plant_identity_from_name_returns_scientific_name(self):
        with patch(
            "server.app.services.gemini_cli.run_gemini_prompt",
            return_value='{"common_name_ja":"サツキツツジ","scientific_name":"Rhododendron indicum","confidence":0.91,"uncertainty_notes":""}',
        ):
            identity = resolve_plant_identity_from_name("サツキツツジ", None)

        self.assertEqual(identity["common_name_ja"], "サツキツツジ")
        self.assertEqual(identity["scientific_name"], "Rhododendron indicum")
        self.assertEqual(identity["confidence"], 0.91)

    def test_analyze_images_retries_with_text_to_json_coercion_when_first_response_is_prose(self):
        responses = iter(
            [
                "この植物はジャーマンアイリス（Iris germanica）と推定されます。花は紫色で、剣状の葉が見えます。",
                '{"common_name_ja":"ジャーマンアイリス","scientific_name":"Iris germanica","confidence":0.9,"candidates":[{"common_name_ja":"ジャーマンアイリス","scientific_name":"Iris germanica","confidence":0.9,"reason":"元テキストに最有力候補として明記されているため。"}],"visible_features":["紫色の花","剣状の葉"],"uncertainty_notes":""}',
            ]
        )
        settings = SimpleNamespace(
            gemini_enabled=True,
            gemini_model="gemini-3-flash-preview",
            gemini_command="gemini",
            gemini_timeout_seconds=30,
        )

        with TemporaryDirectory() as tmp:
            image_dir = Path(tmp)
            paths = []
            for index in range(1, 4):
                path = image_dir / f"{index}.jpg"
                path.write_bytes(b"fake")
                paths.append(path)

            with patch("server.app.services.gemini_cli.get_settings", return_value=settings):
                with patch("server.app.services.gemini_cli.run_gemini_prompt", side_effect=lambda *args, **kwargs: next(responses)):
                    result = analyze_images(paths, gemini_model="gemini-3-flash-preview")

        self.assertEqual(result["common_name_ja"], "ジャーマンアイリス")
        self.assertEqual(result["scientific_name"], "Iris germanica")
        self.assertEqual(result["visible_features"], ["紫色の花", "剣状の葉"])

    def test_force_stop_marks_stale_pending_observation_as_failed(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            image_paths = self._create_fake_images("obs-force-stop")
            db.create_observation(
                observation_id="obs-force-stop",
                image_paths=image_paths,
                captured_at=None,
                note=None,
                location_label=None,
                latitude=None,
                longitude=None,
            )
            db.set_observation_status("obs-force-stop", "analyzing")
            with db.connect() as conn:
                conn.execute(
                    "UPDATE observations SET updated_at = ? WHERE id = ?",
                    ("2026-01-01T00:00:00+00:00", "obs-force-stop"),
                )

            client = TestClient(app)
            response = client.post(
                "/api/observations/obs-force-stop/force-stop",
                headers={"X-Plant-Dex-Api-Key": get_settings().api_key},
            )
            self.assertEqual(response.status_code, 200)
            observation = db.get_observation("obs-force-stop")
            self.assertEqual(observation["status"], "analysis_failed")
            self.assertEqual(observation["error_message"], main.FORCE_STOPPED_ANALYSIS_MESSAGE)

    def test_observation_api_recovers_stale_analyzing_status(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            image_paths = self._create_fake_images("obs-stale")
            db.create_observation(
                observation_id="obs-stale",
                image_paths=image_paths,
                captured_at=None,
                note=None,
                location_label=None,
                latitude=None,
                longitude=None,
            )
            db.set_observation_status("obs-stale", "analyzing")
            with db.connect() as conn:
                conn.execute(
                    "UPDATE observations SET updated_at = ? WHERE id = ?",
                    ("2026-01-01T00:00:00+00:00", "obs-stale"),
                )

            client = TestClient(app)
            response = client.get("/api/observations/obs-stale")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "analysis_failed")
            self.assertEqual(payload["error_message"], main.STALE_ANALYSIS_MESSAGE)

    def test_analyze_images_retries_when_first_response_has_nested_json_schema(self):
        responses = iter(
            [
                '{"plant_identification":{"common_name":"キャラボク","scientific_name":"Taxus cuspidata var. nana"},"observation_details":{"characteristics":["針葉樹で、葉は短く密生している"]},"common_name_ja":null,"scientific_name":null,"confidence":0.0,"candidates":[],"visible_features":[],"uncertainty_notes":""}',
                '{"common_name_ja":"キャラボク","scientific_name":"Taxus cuspidata var. nana","confidence":0.82,"candidates":[{"common_name_ja":"キャラボク","scientific_name":"Taxus cuspidata var. nana","confidence":0.82,"reason":"葉が短く密生し、球形に整えられた姿が一致します。"}],"visible_features":["葉が短く密生","球形に剪定"],"uncertainty_notes":""}',
            ]
        )
        settings = SimpleNamespace(
            gemini_enabled=True,
            gemini_model="gemini-3-flash-preview",
            gemini_command="gemini",
            gemini_timeout_seconds=30,
        )

        with TemporaryDirectory() as tmp:
            image_dir = Path(tmp)
            paths = []
            for index in range(1, 4):
                path = image_dir / f"{index}.jpg"
                path.write_bytes(b"fake")
                paths.append(path)

            with patch("server.app.services.gemini_cli.get_settings", return_value=settings):
                with patch("server.app.services.gemini_cli.run_gemini_prompt", side_effect=lambda *args, **kwargs: next(responses)) as mocked:
                    result = analyze_images(paths, gemini_model="gemini-3-flash-preview")

        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(result["common_name_ja"], "キャラボク")
        self.assertEqual(result["scientific_name"], "Taxus cuspidata var. nana")
        self.assertEqual(result["visible_features"], ["葉が短く密生", "球形に剪定"])

    def test_normalize_result_rejects_placeholder_profile_texts(self):
        result = normalize_result(
            {
                "basic_profile_text": "基本的な特徴",
                "visual_appeal_text": "見た目の特徴と魅力",
                "care_notes": "手入れメモ",
                "visible_features": [],
                "candidates": [],
            }
        )
        self.assertNotIn("basic_profile_text", result)
        self.assertNotIn("visual_appeal_text", result)
        self.assertEqual(result["care_notes"], "")

    def test_normalize_result_maps_common_name_aliases(self):
        result = normalize_result(
            {
                "common_name": "シクラメン",
                "scientific_name": "Cyclamen persicum",
                "confidence": 0.82,
                "candidates": [],
                "visible_features": [],
                "uncertainty_notes": "",
            }
        )
        self.assertEqual(result["common_name_ja"], "シクラメン")
        self.assertEqual(result["scientific_name"], "Cyclamen persicum")

    def test_normalize_result_uses_top_candidate_when_main_fields_are_inconsistent(self):
        result = normalize_result(
            {
                "common_name_ja": "ジャーマンアイリス",
                "scientific_name": "Hydrangea macrophylla",
                "confidence": 0.0,
                "candidates": [
                    {
                        "common_name_ja": "ジャーマンアイリス",
                        "scientific_name": "Iris germanica",
                        "confidence": 0.95,
                        "reason": "一致",
                    }
                ],
                "visible_features": [],
                "uncertainty_notes": "",
            }
        )
        self.assertEqual(result["scientific_name"], "Iris germanica")
        self.assertEqual(result["confidence"], 0.95)

    def test_normalize_result_fills_lightweight_model_alias_fields(self):
        result = normalize_result(
            {
                "common_name": "パキラ",
                "scientific_name": "Pachira aquatica",
                "observation_summary": "鮮やかな緑色の葉が放射状に広がっており、非常に健康的な状態です。",
                "observations": [
                    {"part": "葉", "description": "5〜6枚の小葉が手のひら状に広がっています。"},
                    {"part": "新芽", "description": "中央付近から新しい葉が展開しようとしています。"},
                ],
                "characteristics": {
                    "flower_type": "手のひら状の複葉",
                    "leaf_shape": "手のひら状",
                    "growth_form": "常緑性の観葉植物",
                },
                "care_advice": "土の表面が乾いたらたっぷりと水を与えます。",
                "confidence": 0.0,
                "candidates": [],
                "visible_features": [],
                "uncertainty_notes": "",
            }
        )
        self.assertEqual(result["common_name_ja"], "パキラ")
        self.assertEqual(result["scientific_name"], "Pachira aquatica")
        self.assertGreaterEqual(result["confidence"], 0.75)
        self.assertTrue(result["candidates"])
        self.assertTrue(result["basic_profile_text"])
        self.assertTrue(result["visual_appeal_text"])
        self.assertEqual(result["care_notes"], "土の表面が乾いたらたっぷりと水を与えます。")
        self.assertTrue(result["visible_features"])
        self.assertIn("手のひら状の複葉", result["visible_features"])

    def test_normalize_result_reads_nested_identification_and_observation_details(self):
        result = normalize_result(
            {
                "plant_identification": {
                    "common_name": "キャラボク",
                    "scientific_name": "Taxus cuspidata var. nana",
                },
                "observation_details": {
                    "characteristics": [
                        "針葉樹で、葉は短く密生している",
                        "樹形は円形に剪定されている",
                    ]
                },
                "common_name_ja": None,
                "scientific_name": None,
                "confidence": 0.0,
                "candidates": [],
                "visible_features": [],
                "uncertainty_notes": "",
            }
        )
        self.assertEqual(result["common_name_ja"], "キャラボク")
        self.assertEqual(result["scientific_name"], "Taxus cuspidata var. nana")
        self.assertGreaterEqual(result["confidence"], 0.78)
        self.assertTrue(result["candidates"])
        self.assertIn("針葉樹で、葉は短く密生している", result["visible_features"])

    def test_normalize_result_splits_combined_name(self):
        result = normalize_result(
            {
                "plant_name": "アヤメ (Iris sanguinea)",
                "observation_details": {
                    "characteristics": [
                        "紫色",
                        "剣状の細長い葉",
                        "群生",
                    ]
                },
                "confidence": 0.0,
                "candidates": [],
                "visible_features": [],
                "uncertainty_notes": "",
            }
        )
        self.assertEqual(result["common_name_ja"], "アヤメ")
        self.assertEqual(result["scientific_name"], "Iris sanguinea")
        self.assertTrue(result["candidates"])
        self.assertEqual(result["uncertainty_notes"], "")

    def test_normalize_result_adds_uncertainty_for_low_confidence_single_candidate(self):
        result = normalize_result(
            {
                "plant_name": "アヤメ",
                "confidence": 0.68,
                "candidates": [
                    {
                        "common_name_ja": "アヤメ",
                        "scientific_name": None,
                        "confidence": 0.68,
                        "reason": "候補",
                    }
                ],
                "visible_features": ["紫色"],
                "uncertainty_notes": "",
            }
        )
        self.assertIn("他候補は十分に絞り込めませんでした。", result["uncertainty_notes"])

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

    def test_regenerate_plant_profile_api_updates_profile(self):
        with TemporaryDirectory() as tmp:
            self._use_temp_data_dir(tmp)
            image_paths = self._create_fake_images("obs-plant-profile")
            db.create_observation(
                observation_id="obs-plant-profile",
                image_paths=image_paths,
                captured_at=None,
                note=None,
                location_label=None,
                latitude=None,
                longitude=None,
            )
            plant_id = db.save_analysis_result(
                "obs-plant-profile",
                {
                    "common_name_ja": "ユズ",
                    "scientific_name": "Citrus junos",
                    "confidence": 0.9,
                    "candidates": [],
                },
            )
            client = TestClient(app)
            with patch("server.app.main.generate_plant_profile", return_value={
                "basic_profile_text": "香りの強い柑橘です。",
                "visual_appeal_text": "黄色い実とつやのある葉が魅力です。",
                "care_notes": "日当たりを好みます。",
            }):
                response = client.post(
                    f"/api/plants/{plant_id}/regenerate-profile",
                    headers={"X-Plant-Dex-Api-Key": get_settings().api_key},
                )
            self.assertEqual(response.status_code, 200)
            updated = db.get_plant(plant_id)
            self.assertEqual(updated["basic_profile_text"], "香りの強い柑橘です。")
            self.assertEqual(updated["visual_appeal_text"], "黄色い実とつやのある葉が魅力です。")

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

    def _jpeg_bytes(self, size: tuple[int, int] = (100, 80)) -> bytes:
        output = BytesIO()
        Image.new("RGB", size, (80, 140, 90)).save(output, format="JPEG")
        return output.getvalue()

    def _png_bytes(self, size: tuple[int, int] = (100, 80)) -> bytes:
        output = BytesIO()
        Image.new("RGB", size, (80, 140, 90)).save(output, format="PNG")
        return output.getvalue()

    def _run_async(self, coroutine):
        import asyncio

        return asyncio.run(coroutine)


if __name__ == "__main__":
    unittest.main()
