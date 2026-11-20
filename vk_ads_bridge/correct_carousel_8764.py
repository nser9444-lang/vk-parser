"""Try to add 3 distinct VK original photos to the existing paused Italian Sunrise ad.

This is a one-off, opt-in correction of exactly ad 253388295 in group 169050043.
The ad/group must be blocked. Media fields in the existing banner are preserved.
Never enable delivery or change budget or targeting.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageOps

from .cli import VKAds, IntegrationError, require, positive_id
from .build_test_8764 import download as download_verified_photos, ROOT

GROUP_ID = 169050043
BANNER_ID = 253388295
CAMPAIGN_ID = 42378407
THREE_FIELDS = tuple(f"image_600x600_slide_{i}" for i in (1,2,3))
FILES = ROOT / "carousel_3_photos"


def create_carousel_images() -> list[Path]:
    originals = download_verified_photos()
    require(len(originals) == 3, "Ожидаются три разные оригинальные фотографии")
    FILES.mkdir(parents=True,exist_ok=True)
    outputs=[]
    for i,src in enumerate(originals,1):
        # No generative edits, no cropping: preserve original product from each photo.
        fitted=ImageOps.contain(src,(600,600),Image.Resampling.LANCZOS)
        square=Image.new("RGB",(600,600),(243,243,242))
        square.paste(fitted,((600-fitted.width)//2,(600-fitted.height)//2))
        target=FILES / f"original_photo_{i:02d}_600x600.jpg"
        square.save(target,quality=96,subsampling=0)
        outputs.append(target)
    require(len({hashlib.sha256(p.read_bytes()).hexdigest() for p in outputs})==3,
            "Слайды должны быть разными фотографиями")
    return outputs


def minimal_ids(blocks: dict, label: str) -> dict:
    require(isinstance(blocks,dict),f"Не получен объект {label}")
    out={}
    for k,v in blocks.items():
        if isinstance(v,dict) and type(v.get("id")) is int and v["id"]>0:
            out[k]={"id":v["id"]}
    return out


def minimal_text(blocks: dict) -> dict:
    require(isinstance(blocks,dict),"Не получены текстовые блоки")
    out={}
    for k,v in blocks.items():
        if isinstance(v,dict) and isinstance(v.get("text"),str):
            out[k]={"text":v["text"]}
    return out


def main() -> int:
    try:
        require(os.getenv("VK_ADS_ALLOW_CORRECT_CAROUSEL") == "1",
                "Запись в кабинет отключена")
        api=VKAds()
        group=api.ad_group(GROUP_ID)
        require(group.get("id")==GROUP_ID and group.get("ad_plan_id")==CAMPAIGN_ID
                and group.get("status")=="blocked",
                "Целевая группа должна быть остановлена и относиться к ITALIAN SUNRISE")
        banner=api.request("GET",f"/api/v2/banners/{BANNER_ID}.json",
            params={"fields":"id,status,ad_group_id,content,textblocks,urls"})
        require(banner.get("id")==BANNER_ID and banner.get("ad_group_id")==GROUP_ID
                and banner.get("status")=="blocked",
                "Целевое объявление должно быть остановлено и находиться в целевой группе")
        content=minimal_ids(banner.get("content"),"content")
        texts=minimal_text(banner.get("textblocks"))
        urls=minimal_ids(banner.get("urls"),"urls")
        require("icon_256x256" in content and "image_600x600" in content,
                "Отсутствуют изображения основного формата — обновление запрещено")
        require("primary" in urls and "title_40_vkads" in texts
                and "cta_community_vk" in texts and "about_company_115" in texts,
                "Не найдены обязательные поля существующего объявления")
        # VK carousel pattern 256: title_40_vkads, text_220, about_company_115,
        # cta_community_vk; slide patterns 243,245,246: image_600x600_slide_1..3
        imgpaths=create_carousel_images()
        uploads={}
        for key,path in zip(THREE_FIELDS,imgpaths):
            uploads[key]={"id":api.upload({"path":path,"width":600,"height":600})}
        content.update(uploads)
        require(all(k in content for k in THREE_FIELDS),"Не все три фото подготовлены")
        require(api.ad_group(GROUP_ID).get("status")=="blocked",
                "Группу включили до сохранения")
        payload={"status":"blocked","urls":urls,"content":content,"textblocks":texts}
        api.request("POST",f"/api/v2/banners/{BANNER_ID}.json",json_body=payload)
        check=api.request("GET",f"/api/v2/banners/{BANNER_ID}.json",
                          params={"fields":"id,status,ad_group_id,content"})
        found=minimal_ids(check.get("content"),"после обновления")
        result={
            "group_id":GROUP_ID,"banner_id":BANNER_ID,
            "group_status":api.ad_group(GROUP_ID).get("status"),
            "banner_status":check.get("status"),
            "source_photos":3,
            "carousel_fields_expected":list(THREE_FIELDS),
            "carousel_fields_saved":[k for k in THREE_FIELDS if found.get(k)==uploads[k]],
            "main_image_preserved":("image_600x600" in found),
            "corrected":False
        }
        result["corrected"]=(
            result["group_status"]=="blocked" and result["banner_status"]=="blocked"
            and len(result["carousel_fields_saved"])==3 and result["main_image_preserved"])
        (FILES/"result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
        print(json.dumps(result,ensure_ascii=False,indent=2))
        require(result["corrected"],"VK API не подтвердил сохранение всех трёх слайдов")
        return 0
    except (IntegrationError,ValueError,KeyError,OSError) as exc:
        print("Ошибка при исправлении изображения (группа и объявление не запускаются): "
              + str(exc)[:500],file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
