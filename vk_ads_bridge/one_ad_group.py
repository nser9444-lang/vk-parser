"""Create one BLOCKED VK Ads ad group with exactly one BLOCKED message ad.

A new group is created under an existing campaign, using an existing group
in that campaign as an explicit targeting/auction template. No live delivery.
No writes happen in validate mode. Never reads secrets from job JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from PIL import Image
import requests

from .cli import (
    VKAds, IntegrationError, positive_id, require, validate_landing, path_inside
)

CAMPAIGN_ID = 42378407
PACKAGE_MESSAGES = 3127
EXPECTED_ASSETS = {"icon_256x256": (256, 256), "image_1080x607": (1080, 607)}
GROUP_FIELDS = (
    "id,name,status,ad_plan_id,package_id,targetings,"
    "age_restrictions,autobidding_mode,budget_limit,budget_limit_day,"
    "max_price,price,objective,enable_utm,priced_goal"
)
COPY_FIELDS = (
    "targetings", "age_restrictions", "autobidding_mode",
    "budget_limit", "budget_limit_day", "max_price",
    "price", "objective", "enable_utm", "priced_goal"
)


def _nonblank(value, field: str, max_len: int) -> str:
    require(isinstance(value, str) and 0 < len(value.strip()) <= max_len,
            f"{field}: ожидается строка длиной до {max_len}")
    return value.strip()


def load_spec(path: Path):
    path = path.resolve()
    require(path.is_file(), "Не найден JSON с данными объявления")
    raw = path.read_bytes()
    spec = json.loads(raw.decode("utf-8"))
    require(isinstance(spec, dict), "Требуется JSON-объект")
    require(positive_id(spec.get("campaign_id"), "campaign_id") == CAMPAIGN_ID,
            f"Разрешена только кампания {CAMPAIGN_ID}")
    positive_id(spec.get("template_group_id"), "template_group_id")
    _nonblank(spec.get("group_name"), "group_name", 150)
    validate_landing(spec.get("landing_url"))
    ad = spec.get("ad")
    require(isinstance(ad, dict), "ad: нужен ровно один объект объявления")
    _nonblank(ad.get("name"), "ad.name", 150)
    blocks = ad.get("textblocks")
    require(isinstance(blocks, dict), "ad.textblocks: нет текстовых полей")
    expected = {"text_2000": 2000, "title_40_vkads": 40,
                "about_company_115": 115}
    for key, maxlength in expected.items():
        entry = blocks.get(key)
        require(isinstance(entry, dict), f"Отсутствует поле {key}")
        _nonblank(entry.get("text"), key, maxlength)
    cta = blocks.get("cta_community_vk")
    require(isinstance(cta, dict) and cta.get("text") == "contactUs",
            "Для кампании сообщений нужен cta_community_vk=contactUs")
    require(set(blocks).issubset(set(expected) | {"cta_community_vk"}),
            "В JSON присутствуют неразрешённые текстовые поля")
    require("ads" not in spec, "Нужен один объект ad, а не список ads")
    content = ad.get("content")
    require(isinstance(content, dict) and set(content) == set(EXPECTED_ASSETS),
            "Нужны ровно icon_256x256 и image_1080x607")
    assets = {}
    digest = hashlib.sha256(raw)
    for key, expected_size in EXPECTED_ASSETS.items():
        file_path = path_inside(path.parent, content[key])
        with Image.open(file_path) as image:
            require(image.format in ("PNG", "JPEG"), "Допустимы только PNG/JPEG")
            require(image.size == expected_size,
                    f"{key}: ожидается {expected_size[0]}x{expected_size[1]}, "
                    f"получено {image.size[0]}x{image.size[1]}")
            image.verify()
        digest.update(file_path.read_bytes())
        assets[key] = file_path
    return spec, assets, digest.hexdigest()[:20]


def prepare_group_payload(template: dict, spec: dict, banner: dict) -> dict:
    require(template.get("id") == spec["template_group_id"], "ID группы-шаблона не совпадает")
    require(template.get("ad_plan_id") == CAMPAIGN_ID,
            "Группа-шаблон относится к другой кампании")
    require(template.get("package_id") == PACKAGE_MESSAGES,
            "Группа-шаблон должна иметь пакет 3127 — сообщения")
    require(isinstance(template.get("targetings"), dict) and template["targetings"],
            "API не вернул настройки таргетинга исходной группы")
    payload = {"ad_plan_id": CAMPAIGN_ID, "name": spec["group_name"],
               "status": "blocked", "package_id": PACKAGE_MESSAGES,
               "banners": [banner]}
    for key in COPY_FIELDS:
        val = template.get(key)
        if val is not None:
            payload[key] = val
    # Defence in depth: regardless of template status, no new delivery.
    payload["status"] = "blocked"
    require(len(payload["banners"]) == 1, "В группе допускается одно объявление")
    require(payload["banners"][0].get("status") == "blocked",
            "Объявление не остановлено")
    return payload


def find_duplicate_group(api: VKAds, name: str) -> bool:
    for page in range(40):
        data = api.request("GET", "/api/v2/ad_groups.json",
                           params={"_ad_plan_id__in": str(CAMPAIGN_ID),
                                   "fields": "id,name,ad_plan_id",
                                   "limit": 50, "offset": page * 50})
        items = data.get("items", [])
        require(isinstance(items, list), "Некорректный список групп")
        for item in items:
            # Never assume filter is applied; check target campaign.
            if item.get("name") == name and item.get("ad_plan_id") == CAMPAIGN_ID:
                return True
        if len(items) < 50:
            return False
    raise IntegrationError("Слишком много групп: проверка уникальности имени не завершена")


def execute(path: Path, *, apply: bool, confirm_campaign_id: int | None,
            receipt_dir: Path, api: VKAds | None = None) -> dict:
    spec, assets, fingerprint = load_spec(path)
    if not apply:
        return {"validated": True, "mode": "dry_run", "campaign_id": CAMPAIGN_ID,
                "template_group_id": spec["template_group_id"],
                "group_name": spec["group_name"],
                "ad_count": 1, "status_on_create": "blocked",
                "asset_sizes": {k: list(EXPECTED_ASSETS[k]) for k in assets},
                "fingerprint": fingerprint}
    require(os.environ.get("VK_ADS_ALLOW_CREATE") == "1", "Запись отключена")
    require(confirm_campaign_id == CAMPAIGN_ID, "ID кампании не подтверждён")
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = receipt_dir / f"italian-one-ad-{fingerprint}.json"
    require(not receipt.exists(), f"Пакет уже использовался: {receipt}")
    api = api or VKAds(os.getenv("VK_ADS_CLIENT_ID", ""),
                       os.getenv("VK_ADS_CLIENT_SECRET", ""))
    campaign = api.request("GET", f"/api/v2/ad_plans/{CAMPAIGN_ID}.json",
                           params={"fields": "id,status"})
    require(campaign.get("id") == CAMPAIGN_ID, "Кампания не найдена")
    template = api.request(
        "GET", f"/api/v2/ad_groups/{spec['template_group_id']}.json",
        params={"fields": GROUP_FIELDS})
    require(template.get("ad_plan_id") == CAMPAIGN_ID, "Неверная исходная группа")
    require(template.get("package_id") == PACKAGE_MESSAGES,
            "Исходная группа не относится к цели сообщений")
    require(not find_duplicate_group(api, spec["group_name"]),
            "Группа с таким именем уже существует: запись отменена")
    url_id = api.register_url(spec["landing_url"])
    content_ids = {key: {"id": api.upload({"path": p,
                       "width": EXPECTED_ASSETS[key][0],
                       "height": EXPECTED_ASSETS[key][1]})}
                   for key, p in assets.items()}
    banner = {"name": spec["ad"]["name"], "status": "blocked",
              "urls": {"primary": {"id": url_id}},
              "content": content_ids,
              "textblocks": spec["ad"]["textblocks"]}
    payload = prepare_group_payload(template, spec, banner)
    # Write a receipt before the non-idempotent POST.
    summary = {"campaign_id": CAMPAIGN_ID, "group_name": spec["group_name"],
               "fingerprint": fingerprint, "submitted": False, "completed": False}
    receipt.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    response = api.request("POST", "/api/v2/ad_groups.json", json_body=payload)
    group_id = positive_id(response.get("id"), "created_group_id")
    summary.update({"submitted": True, "group_id": group_id,
                    "banner_ids": [b.get("id") for b in response.get("banners", [])]})
    receipt.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    created = api.ad_group(group_id)
    if created.get("status") != "blocked":
        # Preserve safety even if API has not obeyed the requested blocked status.
        api.request("POST", f"/api/v2/ad_groups/{group_id}.json",
                    json_body={"status": "blocked"})
        created = api.ad_group(group_id)
    require(created.get("status") == "blocked",
            "НЕ ПОДТВЕРЖДЕНА ОСТАНОВКА НОВОЙ ГРУППЫ! Проверьте кабинет.")
    require(created.get("ad_plan_id") == CAMPAIGN_ID,
            "Новая группа неожиданно попала в другую кампанию")
    require(len(response.get("banners", [])) == 1,
            "API не подтвердил создание ровно одного объявления")
    banner_id = positive_id(response["banners"][0].get("id"), "banner_id")
    state = api.banner(banner_id)
    if state.get("status") != "blocked":
        api.stop_banner(banner_id)
        state = api.banner(banner_id)
    require(state.get("status") == "blocked",
            "НЕ ПОДТВЕРЖДЕНА ОСТАНОВКА ОБЪЯВЛЕНИЯ! Проверьте кабинет.")
    summary.update({"completed": True, "group_status": "blocked",
                    "banner_status": "blocked", "banner_ids": [banner_id]})
    receipt.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="ITALIAN SUNRISE: 1 группа = 1 объявление")
    parser.add_argument("spec", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-campaign-id", type=int)
    parser.add_argument("--receipt-dir", type=Path, default=Path("vkads-receipts"))
    args = parser.parse_args()
    try:
        result = execute(args.spec, apply=args.apply,
                         confirm_campaign_id=args.confirm_campaign_id,
                         receipt_dir=args.receipt_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (IntegrationError, ValueError, KeyError, OSError, requests.RequestException) as exc:
        # Never print tokens, Authorization headers or HTTP request details.
        print(f"ОШИБКА: {str(exc)[:350]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
