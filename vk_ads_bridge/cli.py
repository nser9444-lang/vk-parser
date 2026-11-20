"""Безопасная загрузка остановленных объявлений ITALIAN SUNRISE в VK Ads API.

Поддерживается добавление баннеров в существующую ОСТАНОВЛЕННУЮ группу.
Сервис не запускает показы и не изменяет бюджеты/таргетинг.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image

BASE_URL = "https://ads.vk.com"
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
ALLOWED_HOSTS = {"vk.ru", "vk.com", "www.vk.com", "www.vk.ru", "m.vk.com"}


class IntegrationError(Exception):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise IntegrationError(message)


def positive_id(value, field: str) -> int:
    require(type(value) is int and value > 0, f"{field}: требуется положительное целое число")
    return value


def validate_landing(value: str) -> str:
    require(isinstance(value, str), "landing_url: требуется строка")
    parsed = urlparse(value)
    require(parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS
            and not parsed.username and not parsed.password,
            "landing_url: разрешена только HTTPS-ссылка на VK")
    return value


def path_inside(root: Path, relative: str) -> Path:
    require(isinstance(relative, str) and relative and not Path(relative).is_absolute(),
            "content: нужен относительный путь к файлу")
    p = (root / relative).resolve()
    require(p.is_relative_to(root.resolve()), "content: путь выходит за папку объявления")
    require(p.is_file(), f"Не найден креатив: {relative}")
    require(p.suffix.lower() in (".png", ".jpg", ".jpeg"),
            f"Не поддерживается формат изображения: {relative}")
    require(p.stat().st_size <= 15 * 1024 * 1024, f"Файл слишком велик: {relative}")
    return p


def prepare(spec_path: Path) -> tuple[dict, list[dict], str]:
    spec_path = spec_path.resolve()
    require(spec_path.is_file(), f"Не найден JSON: {spec_path}")
    doc = json.loads(spec_path.read_text(encoding="utf-8"))
    require(isinstance(doc, dict), "Корень файла должен быть JSON-объектом")
    positive_id(doc.get("ad_group_id"), "ad_group_id")
    validate_landing(doc.get("landing_url"))
    ads = doc.get("ads")
    require(isinstance(ads, list) and 1 <= len(ads) <= 20,
            "ads: от 1 до 20 объявлений за запуск")
    prepared = []
    digest = hashlib.sha256(spec_path.read_bytes())
    for idx, ad in enumerate(ads, 1):
        require(isinstance(ad, dict), f"ads[{idx}]: ожидается объект")
        name = ad.get("name")
        require(isinstance(name, str) and 1 <= len(name.strip()) <= 150,
                f"ads[{idx}].name: требуется название до 150 символов")
        blocks = ad.get("textblocks")
        require(isinstance(blocks, dict) and blocks, f"ads[{idx}].textblocks: нет текста")
        for key, value in blocks.items():
            require(bool(KEY_RE.fullmatch(key)), f"Недопустимое текстовое поле: {key}")
            require(isinstance(value, dict) and isinstance(value.get("text"), str)
                    and value["text"].strip() and len(value["text"]) <= 2000,
                    f"Неправильный блок: {key}")
        content = ad.get("content")
        require(isinstance(content, dict) and content, f"ads[{idx}].content: нет изображений")
        paths = {}
        for key, relative in content.items():
            require(bool(KEY_RE.fullmatch(key)), f"Недопустимый ключ изображения: {key}")
            file_path = path_inside(spec_path.parent, relative)
            with Image.open(file_path) as image:
                require(image.format in ("PNG", "JPEG"), f"Неверный файл: {relative}")
                width, height = image.size
                image.verify()
            require(width >= 100 and height >= 100, f"Маленькое изображение: {relative}")
            paths[key] = {"path": file_path, "width": width, "height": height}
            digest.update(key.encode("utf-8"))
            digest.update(file_path.read_bytes())
        prepared.append({"name": name.strip(), "textblocks": blocks, "content": paths})
    return doc, prepared, digest.hexdigest()[:16]


class VKAds:
    def __init__(self, client_id: str = "", client_secret: str = "",
                 session=None, access_token: str | None = None):
        # Агентский кабинет может выдать готовый Bearer access_token без client credentials.
        value = access_token if access_token is not None else os.getenv("VK_ADS_ACCESS_TOKEN", "")
        value = value.strip()
        if value.lower().startswith("bearer "):
            value = value[7:].strip()
        require("\r" not in value and "\n" not in value,
                "В токене обнаружен недопустимый перенос строки")
        require(bool(value or (client_id and client_secret)),
                "Нужен VK_ADS_ACCESS_TOKEN или пара VK_ADS_CLIENT_ID/VK_ADS_CLIENT_SECRET")
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = session or requests.Session()
        self._token = value or None

    def token(self) -> str:
        if not self._token:
            response = self.session.post(
                BASE_URL + "/api/v2/oauth2/token.json",
                data={"grant_type": "client_credentials",
                      "client_id": self.client_id, "client_secret": self.client_secret},
                timeout=30,
            )
            self._check_response(response, "Авторизация")
            data = response.json()
            require(bool(data.get("access_token")), "API не вернул access_token")
            self._token = data["access_token"]
        return self._token

    @staticmethod
    def _check_response(response, operation: str) -> None:
        if response.status_code >= 400:
            try:
                obj = response.json()
                err = obj.get("error", obj)
                msg = str(err.get("message", err))[:500] if isinstance(err, dict) else str(err)[:500]
            except (ValueError, TypeError):
                msg = f"HTTP {response.status_code}"
            raise IntegrationError(f"{operation}: HTTP {response.status_code}; {msg}")

    def request(self, method: str, path: str, *, params=None, json_body=None,
                data=None, files=None):
        require(path.startswith("/api/"), "Запрещён произвольный адрес API")
        response = self.session.request(
            method, BASE_URL + path,
            headers={"Authorization": "Bearer " + self.token()},
            params=params, json=json_body, data=data, files=files,
            timeout=60,
        )
        self._check_response(response, path)
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def ad_group(self, group_id: int) -> dict:
        return self.request("GET", f"/api/v2/ad_groups/{group_id}.json",
                            params={"fields": "id,name,status,ad_plan_id,package_id"})

    def list_groups(self) -> dict:
        return self.request("GET", "/api/v2/ad_groups.json",
                            params={"limit": 50, "fields": "id,name,status,ad_plan_id,package_id"})

    def register_url(self, url: str) -> int:
        res = self.request("GET", "/api/v1/urls/", params={"url": url})
        return positive_id(res.get("id"), "URL ID")

    def upload(self, media: dict) -> int:
        path = media["path"]
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        with path.open("rb") as fh:
            result = self.request(
                "POST", "/api/v2/content/static.json",
                data={"data": json.dumps({"width": media["width"],
                                           "height": media["height"]})},
                files={"file": (path.name, fh, mime)},
            )
        return positive_id(result.get("id"), "ID загруженного изображения")

    def add_banner(self, group_id: int, banner: dict) -> int:
        result = self.request("POST", f"/api/v2/ad_groups/{group_id}/banners.json",
                              json_body=banner)
        return positive_id(result.get("id"), "ID объявления")

    def banner(self, banner_id: int) -> dict:
        return self.request("GET", f"/api/v2/banners/{banner_id}.json",
                            params={"fields": "id,status,name,ad_group_id"})

    def stop_banner(self, banner_id: int) -> None:
        self.request("POST", f"/api/v2/banners/{banner_id}.json",
                     json_body={"status": "blocked"})


def do_upload(spec_path: Path, confirmation: int, receipt_dir: Path) -> dict:
    require(os.getenv("VK_ADS_ALLOW_CREATE") == "1",
            "Запись запрещена. Для ручного подтверждения задайте VK_ADS_ALLOW_CREATE=1")
    doc, ads, digest = prepare(spec_path)
    group_id = doc["ad_group_id"]
    require(group_id == confirmation,
            "Номер группы в подтверждении не совпадает с номером в JSON")
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = receipt_dir / f"vkads-{group_id}-{digest}.json"
    require(not receipt.exists(),
            f"Этот пакет уже отправляли; запись результата: {receipt}")
    client = VKAds(os.getenv("VK_ADS_CLIENT_ID", ""),
                   os.getenv("VK_ADS_CLIENT_SECRET", ""))
    group = client.ad_group(group_id)
    require(group.get("status") == "blocked",
            "Операция прервана: группа должна быть ОСТАНОВЛЕНА (status=blocked)")
    positive_id(group.get("ad_plan_id"), "ad_plan_id группы")
    url_id = client.register_url(doc["landing_url"])
    result = {"group_id": group_id, "package_id": group.get("package_id"),
              "landing_url": doc["landing_url"], "digest": digest, "ads": [],
              "complete": False}

    def save() -> None:
        receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                           encoding="utf-8")

    save()
    uploaded = {}
    for ad in ads:
        # Не создаём объявление, если кто-то включил группу во время выполнения.
        require(client.ad_group(group_id).get("status") == "blocked",
                "Группа была включена. Создание остановлено.")
        content_ids = {}
        for key, media in ad["content"].items():
            file_digest = hashlib.sha256(media["path"].read_bytes()).hexdigest()
            if file_digest not in uploaded:
                uploaded[file_digest] = client.upload(media)
            content_ids[key] = {"id": uploaded[file_digest]}
        payload = {"name": ad["name"], "status": "blocked",
                   "urls": {"primary": {"id": url_id}},
                   "content": content_ids, "textblocks": ad["textblocks"]}
        banner_id = client.add_banner(group_id, payload)
        result["ads"].append({"name": ad["name"], "id": banner_id, "status": "checking"})
        save()
        banner_state = client.banner(banner_id)
        if banner_state.get("status") != "blocked":
            client.stop_banner(banner_id)
            banner_state = client.banner(banner_id)
        require(banner_state.get("status") == "blocked",
                f"Не подтверждена остановка объявления {banner_id}; проверьте кабинет!")
        result["ads"][-1]["status"] = "blocked"
        save()
    result["complete"] = True
    save()
    return {"receipt": str(receipt), **result}


def main() -> int:
    parser = argparse.ArgumentParser(description="VK Ads: создание только остановленных объявлений")
    sub = parser.add_subparsers(dest="command", required=True)
    validate_parser = sub.add_parser("validate", help="Проверить JSON и изображения без сети")
    validate_parser.add_argument("spec", type=Path)
    sub.add_parser("groups", help="Получить список рекламных групп через API")
    sub.add_parser("check", help="Только чтение: проверить токен, не выводя данные кабинета")
    upload_parser = sub.add_parser("upload", help="Загрузить объявления в остановленную группу")
    upload_parser.add_argument("spec", type=Path)
    upload_parser.add_argument("--apply", action="store_true", required=True)
    upload_parser.add_argument("--confirm-group-id", type=int, required=True)
    upload_parser.add_argument("--receipt-dir", type=Path, default=Path("vkads-receipts"))
    args = parser.parse_args()
    try:
        if args.command == "validate":
            doc, ads, digest = prepare(args.spec)
            result = {"valid": True, "group_id": doc["ad_group_id"],
                      "count": len(ads), "digest": digest,
                      "images": [{k: [p["width"], p["height"]]
                                  for k, p in ad["content"].items()} for ad in ads]}
        elif args.command in ("groups", "check"):
            client = VKAds(os.getenv("VK_ADS_CLIENT_ID", ""),
                           os.getenv("VK_ADS_CLIENT_SECRET", ""))
            groups = client.list_groups()
            if args.command == "check":
                require(isinstance(groups, dict) and isinstance(groups.get("items"), list),
                        "VK Ads не вернул ожидаемый список групп; формат токена или API проверьте")
                result = {"connected": True, "mode": "read_only",
                          "groups_in_first_page": len(groups["items"])}
            else:
                result = groups
        else:
            result = do_upload(args.spec, args.confirm_group_id, args.receipt_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (IntegrationError, requests.RequestException, OSError, ValueError) as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
