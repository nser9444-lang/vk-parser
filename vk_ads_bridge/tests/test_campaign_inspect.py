import unittest
from unittest.mock import MagicMock

from vk_ads_bridge.campaign_inspect import inspect_campaign
from vk_ads_bridge.cli import IntegrationError


class CampaignInspectionTests(unittest.TestCase):
    def test_only_requested_campaign_and_no_mutation(self):
        api = MagicMock()
        api.request.side_effect = [
            {"id": 42378407, "status": "active"},
            {"items": [
                {"id": 111, "ad_plan_id": 42378407, "status": "blocked", "package_id": 3122},
                {"id": 222, "ad_plan_id": 42378407, "status": "active", "package_id": 3122},
            ]}
        ]
        result = inspect_campaign(api, 42378407)
        self.assertEqual(result["groups_total"], 2)
        self.assertTrue(result["groups"][0]["safe_to_upload"])
        self.assertFalse(result["groups"][1]["safe_to_upload"])
        self.assertEqual(result["campaign_id"], 42378407)
        self.assertTrue(result["read_only"])
        self.assertEqual(api.request.call_count, 2)
        for call in api.request.call_args_list:
            self.assertEqual(call.args[0], "GET")
        self.assertEqual(api.request.call_args_list[1].kwargs["params"]["_ad_plan_id__in"], "42378407")
        api.add_banner.assert_not_called()
        api.upload.assert_not_called()

    def test_parent_mismatch_raises_without_mutation(self):
        api = MagicMock()
        api.request.side_effect = [
            {"id": 42378407, "status": "blocked"},
            {"items": [{"id": 555, "ad_plan_id": 999999, "status": "blocked"}]},
        ]
        api.ad_group.return_value = {"id": 555, "ad_plan_id": 999999}
        with self.assertRaisesRegex(IntegrationError, "не принадлежит"):
            inspect_campaign(api, 42378407)
        api.add_banner.assert_not_called()

    def test_missing_parent_confirmed_with_single_get(self):
        api = MagicMock()
        api.request.side_effect = [
            {"id": 42378407, "status": "blocked"},
            {"items": [{"id": 555, "status": "blocked"}]},
        ]
        api.ad_group.return_value = {"id": 555, "ad_plan_id": 42378407,
                                     "status": "blocked", "package_id": 3122}
        result = inspect_campaign(api, 42378407)
        self.assertEqual(result["groups"][0]["id"], 555)
        api.ad_group.assert_called_once_with(555)


if __name__ == "__main__":
    unittest.main()
