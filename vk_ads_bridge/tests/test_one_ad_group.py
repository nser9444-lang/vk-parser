import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from vk_ads_bridge.one_ad_group import (
    CAMPAIGN_ID, IntegrationError, execute, load_spec, prepare_group_payload
)


class OneAdPerGroupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "assets").mkdir()
        Image.new("RGB", (256, 256), "#ffffff").save(self.root / "assets" / "icon.jpg")
        Image.new("RGB", (600, 600), "#ffffff").save(self.root / "assets" / "square.jpg")
        Image.new("RGB", (1080, 1350), "red").save(self.root / "assets" / "portrait45.jpg")
        Image.new("RGB", (1080, 607), "green").save(self.root / "assets" / "landscape.jpg")
        Image.new("RGB", (607, 1080), "blue").save(self.root / "assets" / "portrait916.jpg")
        self.spec = self.root / "job.json"
        self.data = {
            "campaign_id": CAMPAIGN_ID,
            "template_group_id": 169040836,
            "group_name": "Тест — пальто, аудитория 35–45, сообщения",
            "landing_url": "https://vk.ru/italiansunrise_sochi",
            "ad": {
                "name": "Тест №1 — сообщения",
                "content": {
                    "icon_256x256": "assets/icon.jpg",
                    "image_600x600": "assets/square.jpg",
                    "image_4_5": "assets/portrait45.jpg",
                    "image_1080x607": "assets/landscape.jpg",
                    "image_607x1080": "assets/portrait916.jpg"
                },
                "textblocks": {
                    "text_2000": {"text": "Реальный текст о товаре после проверки."},
                    "title_40_vkads": {"text": "Заголовок"},
                    "cta_community_vk": {"text": "contactUs"},
                    "about_company_115": {"text": "Заполнить юридические сведения"}
                }
            }
        }
        self.save()

    def save(self):
        self.spec.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def template(self):
        return {
            "id": 169040836, "ad_plan_id": CAMPAIGN_ID, "status": "active",
            "package_id": 3127,
            "targetings": {"sex": ["female"], "age": {"age_list": [35, 36]}},
            "budget_limit_day": 500, "autobidding_mode": "max_goals",
            "age_restrictions": "0+"
        }

    def test_preview_without_any_api_call(self):
        result = execute(self.spec, apply=False, confirm_campaign_id=None,
                         receipt_dir=self.root / "receipts")
        self.assertEqual(result["mode"], "dry_run")
        self.assertEqual(result["ad_count"], 1)
        self.assertEqual(result["main_image_formats"], 4)
        self.assertEqual(result["carousel_slides"], 0)
        self.assertEqual(result["status_on_create"], "blocked")
        self.assertFalse((self.root / "receipts").exists())

    def test_wrong_campaign_rejected(self):
        self.data["campaign_id"] = 111
        self.save()
        with self.assertRaises(IntegrationError):
            load_spec(self.spec)

    def test_two_ads_rejected(self):
        self.data["ads"] = [self.data["ad"], self.data["ad"]]
        self.save()
        with self.assertRaises(IntegrationError):
            load_spec(self.spec)

    def test_wrong_cta_rejected(self):
        self.data["ad"]["textblocks"]["cta_community_vk"]["text"] = "signUp"
        self.save()
        with self.assertRaises(IntegrationError):
            load_spec(self.spec)

    def test_missing_916_format_rejected(self):
        del self.data["ad"]["content"]["image_607x1080"]
        self.save()
        with self.assertRaisesRegex(IntegrationError, "4 формата"):
            load_spec(self.spec)

    def test_carousel_slots_rejected(self):
        self.data["ad"]["content"]["image_600x600_slide_1"] = "assets/square.jpg"
        self.save()
        with self.assertRaisesRegex(IntegrationError, "Карусель запрещена"):
            load_spec(self.spec)

    def test_wrong_image_dimensions_rejected(self):
        Image.new("RGB", (900, 900), "#ffffff").save(self.root / "assets" / "icon.jpg")
        with self.assertRaisesRegex(IntegrationError, "256x256"):
            load_spec(self.spec)

    def test_active_source_group_stays_active_but_new_group_blocked(self):
        banner = {"name": "Тест", "status": "blocked"}
        group = prepare_group_payload(self.template(), self.data, banner)
        self.assertEqual(group["status"], "blocked")
        self.assertEqual(group["ad_plan_id"], CAMPAIGN_ID)
        self.assertEqual(group["package_id"], 3127)
        self.assertEqual(group["banners"], [banner])
        self.assertEqual(group["targetings"], self.template()["targetings"])
        self.assertEqual(self.template()["status"], "active")

    def test_source_from_another_campaign_rejected(self):
        t = self.template()
        t["ad_plan_id"] = 11
        with self.assertRaises(IntegrationError):
            prepare_group_payload(t, self.data, {"status": "blocked"})

    def test_creation_one_group_with_one_stopped_banner(self):
        api = MagicMock()
        source = self.template()

        def request(method, path, **kwargs):
            if method == "GET" and path == f"/api/v2/ad_plans/{CAMPAIGN_ID}.json":
                return {"id": CAMPAIGN_ID, "status": "active"}
            if method == "GET" and path == "/api/v2/ad_groups/169040836.json":
                return source
            if method == "GET" and path == "/api/v2/ad_groups.json":
                return {"items": [{"id": 169040836, "ad_plan_id": CAMPAIGN_ID,
                                   "name": "Прежняя группа"}]}
            if method == "GET" and path == "/api/v2/banners.json":
                return {"items": [{"id": 253378451,
                       "textblocks": {"about_company_115": {"text": "Проверенная юридическая информация"}}}]}
            if method == "GET" and path == "/api/v2/banners/999.json":
                return {"id": 999, "status": "blocked", "content": {
                    "image_4_5": {"id": 903},
                    "image_1080x607": {"id": 904},
                    "image_607x1080": {"id": 905},
                    "image_600x600": {"id": 902},
                    "icon_256x256": {"id": 901},
                }}
            if method == "POST" and path == "/api/v2/ad_groups.json":
                payload = kwargs["json_body"]
                self.assertEqual(payload["status"], "blocked")
                self.assertEqual(payload["package_id"], 3127)
                self.assertEqual(payload["ad_plan_id"], CAMPAIGN_ID)
                self.assertEqual(len(payload["banners"]), 1)
                self.assertEqual(payload["banners"][0]["status"], "blocked")
                self.assertEqual(payload["banners"][0]["textblocks"]["cta_community_vk"]["text"], "contactUs")
                return {"id": 888, "banners": [{"id": 999}]}
            raise AssertionError(f"Неожиданный вызов: {method} {path}")

        api.request.side_effect = request
        api.register_url.return_value = 900
        api.upload.side_effect = [901, 902, 903, 904, 905]
        api.ad_group.return_value = {"id": 888, "ad_plan_id": CAMPAIGN_ID,
                                     "status": "blocked"}
        api.banner.return_value = {"id": 999, "status": "blocked"}
        with patch.dict(os.environ, {"VK_ADS_ALLOW_CREATE": "1"}):
            result = execute(self.spec, apply=True, confirm_campaign_id=CAMPAIGN_ID,
                             receipt_dir=self.root / "receipts", api=api)
        self.assertTrue(result["completed"])
        self.assertEqual(result["group_id"], 888)
        self.assertEqual(result["banner_ids"], [999])
        self.assertEqual(result["group_status"], "blocked")
        self.assertEqual(api.upload.call_count, 5)
        self.assertEqual(result["main_image_formats_saved"], 4)
        self.assertEqual(result["carousel_slides"], 0)
        api.stop_banner.assert_not_called()
        post_count = sum(1 for call in api.request.call_args_list
                         if call.args[0] == "POST")
        self.assertEqual(post_count, 1)
        with patch.dict(os.environ, {"VK_ADS_ALLOW_CREATE": "1"}):
            with self.assertRaisesRegex(IntegrationError, "Пакет уже использовался"):
                execute(self.spec, apply=True, confirm_campaign_id=CAMPAIGN_ID,
                        receipt_dir=self.root / "receipts", api=api)

    def test_confirmation_required_before_any_write(self):
        api = MagicMock()
        with patch.dict(os.environ, {"VK_ADS_ALLOW_CREATE": "1"}):
            with self.assertRaisesRegex(IntegrationError, "не подтверждён"):
                execute(self.spec, apply=True, confirm_campaign_id=111,
                        receipt_dir=self.root / "receipts", api=api)
        api.request.assert_not_called()
        api.upload.assert_not_called()

    def test_prevent_duplicate_group_name(self):
        api = MagicMock()
        api.request.side_effect = [
            {"id": CAMPAIGN_ID, "status": "active"},
            self.template(),
            {"items": [{"id": 777, "ad_plan_id": CAMPAIGN_ID,
                        "name": self.data["group_name"]}]}
        ]
        with patch.dict(os.environ, {"VK_ADS_ALLOW_CREATE": "1"}):
            with self.assertRaisesRegex(IntegrationError, "уже существует"):
                execute(self.spec, apply=True, confirm_campaign_id=CAMPAIGN_ID,
                        receipt_dir=self.root / "receipts", api=api)
        api.upload.assert_not_called()
        self.assertEqual([c.args[0] for c in api.request.call_args_list],
                         ["GET", "GET", "GET"])


if __name__ == "__main__":
    unittest.main()
