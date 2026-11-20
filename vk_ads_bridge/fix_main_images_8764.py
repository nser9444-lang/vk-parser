"""Correct existing stopped ITALIAN SUNRISE ad: photos belong in main Images.

One-time workflow for ad 253388295 / group 169050043 / plan 42378407:
- retain square and icon
- upload 4:5, 16:9, 9:16 media to their VK community image roles
- verify them through GET
- remove erroneous carousel_slide roles after success
- verify 4 image roles and no carousel roles
Never change statuses to active or edit targeting or budget.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from PIL import Image

from .build_test_8764 import ROOT, download, render
from .cli import IntegrationError, VKAds, require
from .correct_carousel_8764 import GROUP_ID, BANNER_ID, CAMPAIGN_ID, minimal_ids

ADDITIONAL_IMAGES={
    "image_4_5": ((1080,1350), "portrait", "main_4_5.jpg",2),
    "image_1080x607": ((1080,607), "wide", "main_16_9.jpg",0),
    "image_607x1080": ((607,1080), "story", "main_9_16.jpg",1),
}
BASE_IMAGE_ROLES={"image_600x600","icon_256x256"}
FULL_IMAGE_ROLES=BASE_IMAGE_ROLES | set(ADDITIONAL_IMAGES)
PREFIX="image_600x600_slide_"
DIR=ROOT / "main_images"

class ThrottledVKAds(VKAds):
    """Space requests and retry transient VK Ads 429 responses."""
    def request(self, method, path, *, params=None, json_body=None, data=None, files=None):
        for attempt in range(6):
            # VK Ads response indicates one request allowed in each rate window.
            time.sleep(1.8)
            try:
                return super().request(
                    method, path, params=params, json_body=json_body,
                    data=data, files=files)
            except IntegrationError as exc:
                if "HTTP 429" not in str(exc) or attempt == 5:
                    raise
                delay=min(6*(attempt+1),30)
                print(f"VK Ads API временно ограничил запросы; повтор после {delay} сек.",
                      file=sys.stderr)
                time.sleep(delay)
        raise IntegrationError("Не удалось обойти ограничение частоты API")



def identify_carousel_roles(content: dict)->list[str]:
    return [key for key in content if key.startswith(PREFIX)]


def prepare_original_product_creatives()->dict[str,dict]:
    photos=download()  # SHA256-verified against original VK post #8764
    require(len(photos)==3,"Ожидаются 3 оригинальных фото товара")
    DIR.mkdir(parents=True,exist_ok=True)
    prepared={}
    for role,(size,kind,name,photo_index) in ADDITIONAL_IMAGES.items():
        # render() uses the 3rd photo slot; rotate to use a different original photo
        arranged=list(photos)
        arranged[2]=photos[photo_index]
        if kind=="story":
            image,_=render(arranged,1080,1920,"story")
        else:
            image,_=render(arranged,*size,kind)
        if image.size!=size:
            image=image.resize(size,Image.Resampling.LANCZOS)
        require(image.size==size,f"Неожиданный размер картинки {role}")
        target=DIR/name
        image.save(target,format="JPEG",quality=95)
        prepared[role]={"path":target,"width":size[0],"height":size[1]}
    return prepared


def check_image_roles(content:dict, ids:dict)->bool:
    return (all(k in content and
                 isinstance(content[k],dict) and
                 content[k].get("id")==ids[k]["id"]
                for k in ADDITIONAL_IMAGES)
            and BASE_IMAGE_ROLES.issubset(content))


def main()->int:
    try:
        require(os.environ.get("VK_ADS_ALLOW_MAIN_IMAGES_FIX")=="1",
                "Исправление должно быть явно разрешено")
        api=ThrottledVKAds()
        group=api.ad_group(GROUP_ID)
        require(group.get("id")==GROUP_ID and
                group.get("ad_plan_id")==CAMPAIGN_ID and
                group.get("status")=="blocked",
                "Группа не соответствует ITALIAN SUNRISE или уже включена")
        path=f"/api/v2/banners/{BANNER_ID}.json"
        params={"fields":"id,status,ad_group_id,content"}
        ad=api.request("GET",path,params=params)
        require(ad.get("id")==BANNER_ID and
                ad.get("ad_group_id")==GROUP_ID and
                ad.get("status")=="blocked",
                "Объявление должно быть остановлено и находиться в нужной группе")
        original_content=minimal_ids(ad.get("content"),"content")
        require(BASE_IMAGE_ROLES.issubset(original_content),
                "Отсутствует основное фото 1:1 или иконка")
        slides=identify_carousel_roles(original_content)
        if not slides and FULL_IMAGE_ROLES.issubset(original_content):
            print(json.dumps({"already_complete":True,
                  "main_images": sorted(FULL_IMAGE_ROLES), "carousel_slides":0,
                  "group_id":GROUP_ID,"banner_id":BANNER_ID},ensure_ascii=False))
            return 0
        if FULL_IMAGE_ROLES.issubset(original_content):
            # Previous run may have saved formats before receiving a 429.
            # Reuse those IDs rather than uploading duplicate photos.
            image_ids={role:original_content[role] for role in ADDITIONAL_IMAGES}
        else:
            prepared=prepare_original_product_creatives()
            image_ids={role:{"id":api.upload(media)}
                       for role,media in prepared.items()}
            # Phase 1: preserve existing media including carousel until main images confirmed.
            before_update=dict(original_content)
            before_update.update(image_ids)
            require(api.ad_group(GROUP_ID).get("status")=="blocked",
                    "Группу включили; обновление остановлено")
            api.request("POST",path,json_body={"status":"blocked","content":before_update})
        confirmed=api.request("GET",path,params=params)
        content_after=minimal_ids(confirmed.get("content"),"content после загрузки")
        require(confirmed.get("status")=="blocked" and
                check_image_roles(content_after,image_ids),
                "Не подтверждено сохранение трёх форматов в блоке Изображения")
        # Phase 2: remove only slide media fields; preserve every other current media id.
        clean_content={key:value for key,value in content_after.items()
                       if not key.startswith(PREFIX)}
        require(FULL_IMAGE_ROLES.issubset(clean_content),
                "Неожиданное отсутствие основных изображений")
        require(api.ad_group(GROUP_ID).get("status")=="blocked",
                "Группа перестала быть остановленной; удаление карусели отменено")
        if identify_carousel_roles(content_after):
            api.request("POST",path,
                        json_body={"status":"blocked","content":clean_content})
        final_ad=api.request("GET",path,params=params)
        final_content=minimal_ids(final_ad.get("content"),"content итог")
        final_group=api.ad_group(GROUP_ID)
        result={
            "group_id":GROUP_ID,"banner_id":BANNER_ID,
            "group_status":final_group.get("status"),
            "banner_status":final_ad.get("status"),
            "main_image_roles":sorted(FULL_IMAGE_ROLES & set(final_content)),
            "main_image_count":len(FULL_IMAGE_ROLES & set(final_content)),
            "carousel_slide_roles":identify_carousel_roles(final_content),
            "main_variants_saved":check_image_roles(final_content,image_ids),
            "corrected":False
        }
        result["corrected"]=(
            result["group_status"]=="blocked" and
            result["banner_status"]=="blocked" and
            result["main_image_count"]==4 and
            not result["carousel_slide_roles"] and result["main_variants_saved"])
        DIR.mkdir(parents=True,exist_ok=True)
        (DIR/"result.json").write_text(
            json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(result,ensure_ascii=False,indent=2))
        require(result["corrected"],
                "VK Ads не подтвердил 4 изображения без карусели")
        return 0
    except (IntegrationError, ValueError, KeyError, OSError) as exc:
        print("Ошибка исправления блока Изображения (показы не включались): "
              + str(exc)[:1400],file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
