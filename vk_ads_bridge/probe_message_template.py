"""Read-only readiness check for message-ad group cloning. No targeting/budget details in logs."""
import json
import os
import sys

from .cli import VKAds, IntegrationError, require
from .one_ad_group import CAMPAIGN_ID, PACKAGE_MESSAGES, GROUP_FIELDS


def main() -> int:
    api = VKAds(os.getenv("VK_ADS_CLIENT_ID", ""),
                os.getenv("VK_ADS_CLIENT_SECRET", ""))
    template_id = 169040836
    try:
        data = api.request("GET", f"/api/v2/ad_groups/{template_id}.json",
                           params={"fields": GROUP_FIELDS})
        require(data.get("id") == template_id, "Неверный ID исходной группы")
        require(data.get("ad_plan_id") == CAMPAIGN_ID,
                "Исходная группа не принадлежит кампании")
        require(data.get("package_id") == PACKAGE_MESSAGES, "Неверная цель кампании")
        targetings = data.get("targetings")
        can_clone = isinstance(targetings, dict) and bool(targetings)
        print(json.dumps({
            "campaign_id": CAMPAIGN_ID,
            "template_group_id": template_id,
            "package_id": data.get("package_id"),
            "template_group_status": data.get("status"),
            "targetings_available": can_clone,
            "budget_setting_available": any(data.get(x) is not None for x in
                                            ("budget_limit", "budget_limit_day")),
            "ready_for_group_template": can_clone,
            "read_only": True
        }, ensure_ascii=False, indent=2))
        return 0 if can_clone else 1
    except (IntegrationError, ValueError, OSError) as exc:
        print("Ошибка безопасной проверки: " + str(exc)[:250], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
