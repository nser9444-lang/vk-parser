"""Read-only inspection of one VK Ads ad plan and its ad groups.

Never prints access tokens, campaign/group names, budgets, targets, or audiences.
"""
import argparse
import json
import os

from .cli import VKAds, IntegrationError, require, positive_id


def inspect_campaign(api: VKAds, campaign_id: int) -> dict:
    positive_id(campaign_id, "campaign_id")
    campaign = api.request(
        "GET", f"/api/v2/ad_plans/{campaign_id}.json",
        params={"fields": "id,status"},
    )
    require(campaign.get("id") == campaign_id,
            "API не подтвердил идентификатор рекламной кампании")
    groups = []
    page_size = 50
    for page in range(200):
        data = api.request(
            "GET", "/api/v2/ad_groups.json",
            params={"_ad_plan_id__in": str(campaign_id),
                    "fields": "id,ad_plan_id,status,package_id",
                    "limit": page_size, "offset": page * page_size},
        )
        items = data.get("items")
        require(isinstance(items, list), "Список групп имеет неожиданный формат")
        for item in items:
            require(isinstance(item, dict), "Неверный объект группы")
            gid = positive_id(item.get("id"), "group_id")
            parent = item.get("ad_plan_id")
            if parent != campaign_id:
                # The list API may omit fields, or ignore filter. Confirm parent independently.
                details = api.ad_group(gid)
                parent = details.get("ad_plan_id")
                require(parent == campaign_id,
                        f"Группа {gid} не принадлежит указанной кампании; проверка остановлена")
                item = details
            status = item.get("status")
            require(status in {"active", "blocked", "deleted"},
                    f"Неизвестный статус группы {gid}; проверка остановлена")
            groups.append({"id": gid, "status": status,
                           "package_id": item.get("package_id"),
                           "safe_to_upload": status == "blocked"})
        if len(items) < page_size:
            break
    else:
        raise IntegrationError("Превышен безопасный предел пагинации")
    return {
        "campaign_id": campaign_id, "campaign_status": campaign.get("status"),
        "groups_total": len(groups), "groups": groups,
        "read_only": True,
        "note": "safe_to_upload подтверждает только остановку группы, не поддержку формата",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверить группы VK Ads кампании — только чтение")
    parser.add_argument("--campaign-id", type=int, required=True)
    args = parser.parse_args()
    try:
        client = VKAds(os.getenv("VK_ADS_CLIENT_ID", ""),
                       os.getenv("VK_ADS_CLIENT_SECRET", ""))
        result = inspect_campaign(client, args.campaign_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (IntegrationError, ValueError, OSError) as error:
        # Do not include token values or request headers in logs.
        print("Проверка кампании не завершена: " + str(error)[:350])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
