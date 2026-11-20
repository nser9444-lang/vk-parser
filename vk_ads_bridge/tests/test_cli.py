import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from PIL import Image

from vk_ads_bridge.cli import IntegrationError, VKAds, prepare, do_upload


class VKAdsUploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "assets").mkdir()
        self.image_path = root / "assets" / "image.jpg"
        Image.new("RGB", (1080, 607), "white").save(self.image_path)
        self.spec_path = root / "job.json"
        self.job = {
            "ad_group_id": 12345,
            "landing_url": "https://vk.ru/italiansunrise_sochi",
            "ads": [{
                "name": "Тестовый вариант",
                "content": {"image_1080x607": "assets/image.jpg"},
                "textblocks": {"text_2000": {"text": "Подтверждённое описание товара"}}
            }]
        }
        self.save_job()

    def save_job(self):
        self.spec_path.write_text(json.dumps(self.job, ensure_ascii=False), encoding="utf-8")

    def test_ready_bearer_token_needs_no_client_credentials(self):
        session = MagicMock()
        response = session.request.return_value
        response.status_code = 200
        response.content = b'{"count":0,"items":[]}'
        response.json.return_value = {"count": 0, "items": []}
        with patch.dict(os.environ, {"VK_ADS_ACCESS_TOKEN": "Bearer test-agency-token"}):
            client = VKAds(session=session)
            result = client.list_groups()
        self.assertEqual(result["count"], 0)
        self.assertEqual(session.request.call_args.kwargs["headers"],
                         {"Authorization": "Bearer test-agency-token"})
        session.post.assert_not_called()

    def test_token_injection_is_rejected(self):
        with self.assertRaisesRegex(IntegrationError, "перенос строки"):
            VKAds(access_token="token\r\nBad: header")

    def test_no_token_or_credentials_rejected(self):
        with patch.dict(os.environ, {"VK_ADS_ACCESS_TOKEN": ""}):
            with self.assertRaisesRegex(IntegrationError, "Нужен VK_ADS_ACCESS_TOKEN"):
                VKAds()

    def test_validate_good_job_without_network(self):
        doc, ads, fingerprint = prepare(self.spec_path)
        self.assertEqual(doc["ad_group_id"], 12345)
        self.assertEqual(ads[0]["content"]["image_1080x607"]["width"], 1080)
        self.assertEqual(len(fingerprint), 16)

    def test_landing_must_be_vkontakte(self):
        self.job["landing_url"] = "https://example.net"
        self.save_job()
        with self.assertRaises(IntegrationError):
            prepare(self.spec_path)

    def test_missing_image_fails_early(self):
        self.job["ads"][0]["content"]["image_1080x607"] = "assets/missing.jpg"
        self.save_job()
        with self.assertRaises(IntegrationError):
            prepare(self.spec_path)

    def test_directory_escape_rejected(self):
        self.job["ads"][0]["content"]["image_1080x607"] = "../image.jpg"
        self.save_job()
        with self.assertRaises(IntegrationError):
            prepare(self.spec_path)

    def test_active_group_rejected_before_upload(self):
        receipts = Path(self.tmp.name) / "receipts"
        with patch.dict(os.environ, {
            "VK_ADS_ALLOW_CREATE": "1", "VK_ADS_CLIENT_ID": "test-id",
            "VK_ADS_CLIENT_SECRET": "test-secret"
        }), patch("vk_ads_bridge.cli.VKAds") as klass:
            klass.return_value.ad_group.return_value = {
                "id": 12345, "status": "active", "ad_plan_id": 444
            }
            with self.assertRaisesRegex(IntegrationError, "ОСТАНОВЛЕНА"):
                do_upload(self.spec_path, 12345, receipts)
            klass.return_value.register_url.assert_not_called()
            klass.return_value.upload.assert_not_called()

    def test_confirmation_must_match_job(self):
        with patch.dict(os.environ, {"VK_ADS_ALLOW_CREATE": "1"}):
            with self.assertRaisesRegex(IntegrationError, "не совпадает"):
                do_upload(self.spec_path, 99, Path(self.tmp.name) / "receipts")

    def test_success_only_blocked_banner_and_receipt(self):
        receipts = Path(self.tmp.name) / "receipts"
        with patch.dict(os.environ, {
            "VK_ADS_ALLOW_CREATE": "1", "VK_ADS_CLIENT_ID": "test-id",
            "VK_ADS_CLIENT_SECRET": "test-secret"
        }), patch("vk_ads_bridge.cli.VKAds") as klass:
            service = klass.return_value
            service.ad_group.return_value = {
                "id": 12345, "status": "blocked", "ad_plan_id": 444, "package_id": 3122
            }
            service.register_url.return_value = 9900
            service.upload.return_value = 8800
            service.add_banner.return_value = 7700
            service.banner.return_value = {"id": 7700, "status": "blocked"}
            result = do_upload(self.spec_path, 12345, receipts)
            self.assertTrue(result["complete"])
            self.assertEqual(result["ads"][0]["status"], "blocked")
            data = service.add_banner.call_args.args[1]
            self.assertEqual(data["status"], "blocked")
            self.assertEqual(data["urls"]["primary"]["id"], 9900)
            self.assertEqual(data["content"]["image_1080x607"]["id"], 8800)
            self.assertTrue(Path(result["receipt"]).exists())
            with self.assertRaisesRegex(IntegrationError, "уже отправляли"):
                do_upload(self.spec_path, 12345, receipts)


if __name__ == "__main__":
    unittest.main()
