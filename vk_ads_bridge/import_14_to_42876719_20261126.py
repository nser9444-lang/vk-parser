#!/usr/bin/env python3
"""ITALIAN SUNRISE: import existing ad creative archives 002–015 to VK Ads as BLOCKED.

Use actual approved/archive PNG pixels (not regenerated clothing). Create exactly
one NEW BLOCKED message ad per new BLOCKED group. Four images belong in main
"Изображения", NOT carousel. Validate back via VK Ads API before success.
Archive URLs are short-lived and passed in an issue event, never committed.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile

from PIL import Image, ImageOps
import requests

from vk_ads_bridge.one_ad_group import execute, CAMPAIGN_ID, EXPECTED_ASSETS, GROUP_FIELDS
import vk_ads_bridge.one_ad_group as group_bridge
from vk_ads_bridge.cli import VKAds, IntegrationError

ROOT=Path("vkads-import-42876719-20261126")
IDS=list(range(2,16))
CAMPAIGN_ID_EXPECTED=42876719
FORMAT_NAMES=("1x1.png","4x5.png","16x9.png","9x16.png")
EXPECTED_DIMENSIONS={"1x1.png":(1080,1080),"4x5.png":(1080,1350),
                     "16x9.png":(1600,900),"9x16.png":(1080,1920)}
BUNDLE_KEYS=("002","003","004","005","006-015")
SOURCE_BUNDLE_MAP={"002":2,"003":3,"004":4,"005":5}
GROUP_TAG="ITALIAN SUNRISE 26.11.2026 | 42876719"
# Patch constants only in this one upload process, not in the older workflow.
group_bridge.CAMPAIGN_ID=42876719

class SlowReliableVKAds(VKAds):
    """Respect one request per ~2s; retry only transient GET/UPLOAD/429 safely."""
    def request(self,method,path,*,params=None,json_body=None,data=None,files=None):
        # A POST creating a group is not safe to retry without checking duplicate.
        uploading=path=="/api/v2/content/static.json"
        safe_to_retry=(method=="GET" or uploading)
        for attempt in range(5):
            time.sleep(2.1)
            try:
                return super().request(method,path,params=params,json_body=json_body,
                                       data=data,files=files)
            except IntegrationError as e:
                s=str(e)
                if not safe_to_retry or not any(x in s for x in ("HTTP 429","HTTP 500","HTTP 502","HTTP 503")) or attempt==4:
                    raise
                time.sleep(min(8*(attempt+1),40))
        raise IntegrationError("Too many retries")

def download_archive(name,item):
    url=item["url"].strip()
    parsed=urllib.parse.urlsplit(url)
    assert parsed.scheme=="https" and (parsed.hostname or "").endswith(".oaiusercontent.com"),"Unexpected artifact host"
    max_size=100_000_000
    out=ROOT/f"archive-{name}.zip"
    req=urllib.request.Request(url,headers={"User-Agent":"ItalianSunriseOriginalCreativeTransfer/1"})
    with urllib.request.urlopen(req,timeout=120) as resp, out.open("wb") as fh:
        total=0
        while True:
            chunk=resp.read(2**20)
            if not chunk:break
            total+=len(chunk)
            if total>max_size:raise RuntimeError("Unexpectedly large archive")
            fh.write(chunk)
    digest=hashlib.sha256(out.read_bytes()).hexdigest()
    if digest!=item["sha256"]:
        raise RuntimeError(f"Archive {name} digest mismatch; no upload")
    print(f"CHECK archive-{name} sha256 verified, {out.stat().st_size} bytes",flush=True)
    return out

def extract_verified(archives):
    folders={}
    for name,path in archives.items():
        base=ROOT/"creatives"
        if name in SOURCE_BUNDLE_MAP:
            target=base/f'{SOURCE_BUNDLE_MAP[name]:03d}'
        else:target=base
        target.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(path) as z:
            infos=z.infolist()
            # Known archive layout: one campaign per root for 2-5, folder per ad 6–15.
            if len(infos)>150:raise RuntimeError("Unexpected archive file count")
            total_uncompressed=sum(k.file_size for k in infos)
            if total_uncompressed>300_000_000:raise RuntimeError("Archive decompression too large")
            for info in infos:
                if info.is_dir():continue
                parts=Path(info.filename).parts
                if any(p in ("..","") for p in parts) or info.filename.startswith("/"):
                    raise RuntimeError("Unsafe archive filename")
                if info.filename.endswith((".png",".jpg",".json",".txt",".md")):
                    destination=target.joinpath(*parts)
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    destination.write_bytes(z.read(info))
    # check exact 56 variants; no synthetic fallback, no blank placeholders.
    mapping={}
    for i in IDS:
        top=ROOT/"creatives"
        candidates=[p for p in top.glob(f"{i:03d}*") if p.is_dir()]
        if len(candidates)!=1:raise RuntimeError(f"Missing or duplicate creative {i}: {len(candidates)}")
        folder=candidates[0]
        for file,size in EXPECTED_DIMENSIONS.items():
            p=folder/file
            if not p.exists():raise RuntimeError(f"{i}: missing {file}")
            with Image.open(p) as test:
                if test.size!=size or test.format!="PNG":
                    raise RuntimeError(f"{i}: invalid {file} dimensions or format")
                test.verify()
        if not (folder/"ad_text.txt").exists():
            raise RuntimeError(f"{i}: missing ad text")
        mapping[i]=folder
    return mapping

def make_ad_assets(idx,folder):
    target=ROOT/"ready"/f"{idx:03d}"
    target.mkdir(parents=True,exist_ok=True)
    # The four original campaign image files are retained unchanged as sources.
    named={"image_600x600":("1x1.png",(600,600)),
           "image_4_5":("4x5.png",(1080,1350)),
           "image_1080x607":("16x9.png",(1080,607)),
           "image_607x1080":("9x16.png",(607,1080))}
    content={}
    for role,(filename,size) in named.items():
        with Image.open(folder/filename) as im:
            photo=im.convert("RGB")
            output=ImageOps.fit(photo,size,Image.Resampling.LANCZOS,centering=(.5,.5))
            dest=target/f"{role}.png"
            output.save(dest,format="PNG",optimize=True)
            content[role]=dest.name
    icon_candidates=sorted(folder.glob("original_*.jpg"))+sorted(folder.glob("source_*.jpg"))
    if not icon_candidates:
        raise RuntimeError(f"{idx}: no original source photo for icon")
    with Image.open(icon_candidates[0]) as im:
        original=im.convert("RGB")
        icon=ImageOps.fit(original,(256,256),Image.Resampling.LANCZOS,centering=(.5,.37))
        icon.save(target/"icon_256x256.png",format="PNG",optimize=True)
        content["icon_256x256"]="icon_256x256.png"
    # Must match five precise VK Ads media roles; four main images + icon.
    if set(content)!=set(EXPECTED_ASSETS):raise RuntimeError("Incomplete VK Ads image roles")
    for role,name in content.items():
        with Image.open(target/name) as img:
            if img.size!=EXPECTED_ASSETS[role]:raise RuntimeError("Incorrect VK format")
    return target,content

def clean_title(s):
    s=re.sub(r"\s+"," ",s.strip()).replace("№","№")
    return s[:40].strip()

def create_specs(mapping,text_override):
    specs=[]
    for idx,folder in sorted(mapping.items()):
        target,roles=make_ad_assets(idx,folder)
        text=(folder/"ad_text.txt").read_text(encoding="utf-8").strip()
        if idx==5:
            text=text_override.strip()
        if not text or len(text)>2000:
            raise RuntimeError(f"{idx}: invalid ad copy")
        if "«+»" not in text and "« + »" not in text:
            raise RuntimeError(f"{idx}: missing plus CTA")
        manifest=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
        title=manifest.get("image_headline") or manifest.get("title") or manifest.get("concept_name") or \
              manifest.get("image_title") or f"Итальянская одежда {idx}"
        title=clean_title(title)
        if not title:title=f"Итальянская одежда {idx}"
        spec={
          "campaign_id":42876719,
          "template_group_id":169616554,
          "group_name":f"{GROUP_TAG} | Связка {idx:03d} | архив четырёх форматов",
          "landing_url":"https://vk.ru/italiansunrise_sochi",
          "ad":{
            "name":f"ITALIAN SUNRISE | {idx:03d} | {title}"[:150],
            "content":roles,
            "textblocks":{
                "title_40_vkads":{"text":title},
                "text_2000":{"text":text},
                "cta_community_vk":{"text":"contactUs"},
                "about_company_115":{"text":"Берём подтверждённые сведения рекламодателя из шаблона"}
            }
          }
        }
        output=target/"job.json"
        output.write_text(json.dumps(spec,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        specs.append((idx,output))
    return specs

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--apply",action="store_true")
    args=ap.parse_args()
    if not os.getenv("VK_ADS_ACCESS_TOKEN") and args.apply:
        raise RuntimeError("VK Ads token secret is absent")
    if args.apply and os.getenv("VK_ADS_BATCH_CONFIRM")!="COPY_14_BLOCKED_TO_42876719":
        raise RuntimeError("Explicit batch user confirmation not supplied")
    payload=json.loads(os.environ["CREATIVE_ARCHIVES_JSON"])
    if set(payload["archives"])!=set(BUNDLE_KEYS):
        raise RuntimeError("Expected five source archives")
    latest=payload.get("ad005_text","")
    if len(latest)<50 or "5 200" not in latest:
        raise RuntimeError("Latest approved copy for ad 005 not provided")
    ROOT.mkdir(parents=True,exist_ok=True)
    archives={}
    for name in BUNDLE_KEYS:
        archives[name]=download_archive(name,payload["archives"][name])
    mapping=extract_verified(archives)
    specs=create_specs(mapping,latest)
    print(f"PRE-FLIGHT: {len(specs)} complete creatives, 4 primary images each + one icon",flush=True)
    # Local validate with one_ad_group.load_spec, before any changes on VK.
    from vk_ads_bridge.one_ad_group import load_spec
    for n,path in specs:
        doc,content,digest=load_spec(path)
        if len(content)!=5:raise RuntimeError(f"{n}: all image formats not ready")
    print("ALL 14 SPECS PASSED dimensions and original-file checks",flush=True)
    results=[]
    try:
        if not args.apply:
            print(json.dumps({"dry_run":True,"groups_ready":len(specs),"formats_per_ad":4}))
            return 0
        api=SlowReliableVKAds()
        target=api.request("GET","/api/v2/ad_plans/42876719.json",params={"fields":"id,status"})
        if target.get("id")!=42876719 or target.get("status")!="blocked":
            raise RuntimeError("Target campaign inaccessible or not blocked")
        template=api.request("GET","/api/v2/ad_groups/169616554.json",params={"fields":GROUP_FIELDS})
        if template.get("ad_plan_id")!=42876719 or template.get("package_id")!=3127:
            raise RuntimeError("Target group mismatched campaign or package")
        if template.get("status")!="blocked":
            raise RuntimeError("Target group must be blocked")
        if template.get("budget_limit_day") is None or template.get("budget_limit") is not None:
            raise RuntimeError("Group-level daily budget not verified on target template")
        print("TARGET BUDGET CHECK PASSED: daily budget on ad-group level, values not printed",flush=True)
        # Only this method creates ads. Execute sequentially to avoid API rate limits.
        for i,(n,path) in enumerate(specs,1):
            print(f"UPLOAD START {n:03d} ({i}/{len(specs)})",flush=True)
            try:
                record=execute(path,apply=True,confirm_campaign_id=42876719,
                               receipt_dir=ROOT/"receipts",api=api)
                if record.get("main_image_formats_saved")!=4 or record.get("carousel_slides")!=0:
                    raise RuntimeError("VK did not confirm all 4 main image fields")
                created_group=api.request("GET",f"/api/v2/ad_groups/{record['group_id']}.json",
                    params={"fields":"id,status,ad_plan_id,package_id,budget_limit_day,budget_limit"})
                if created_group.get("ad_plan_id")!=42876719 or created_group.get("status")!="blocked":
                    raise RuntimeError("Wrong campaign/status after creation")
                if created_group.get("budget_limit_day")!=template.get("budget_limit_day"):
                    raise RuntimeError("Group daily budget differs from target template")
                if created_group.get("budget_limit") is not None:
                    raise RuntimeError("Unexpected group total budget")
                record["target_campaign_id"]=42876719
                record["daily_group_budget_verified_by_api"]=True
                record["number"]=n
                record["successful"]=True
                print(f"UPLOAD SUCCESS {n:03d}: group={record['group_id']}, banner={record['banner_ids'][0]}; 4 images",flush=True)
                results.append(record)
            except Exception as exc:
                results.append({"number":n,"successful":False,"error_type":type(exc).__name__,
                                "error_short":str(exc)[:300]})
                print(f"UPLOAD FAILURE {n:03d}: {type(exc).__name__}: {str(exc)[:250]}",flush=True)
                # Abort rather than creating more possibly incomplete banners.
                break
    finally:
        report={"campaign_id":42876719,"attempted":len(results),
                "successful_count":sum(bool(r["successful"]) for r in results),
                "total_expected":14,"group_status":"blocked","banner_status":"blocked",
                "four_images_verified_by_api_for_successes":True,
                "no_vk_ads_activation_attempted":True,
                "records":results}
        (ROOT/"upload-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print("UPLOAD_FINAL_STATUS "+json.dumps({k:report[k] for k in
              ("attempted","successful_count","total_expected","no_vk_ads_activation_attempted")},
             ensure_ascii=False),flush=True)
    return 0 if len(results)==14 and all(r["successful"] for r in results) else 1

if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"PRECHECK FAILURE: {type(exc).__name__}: {str(exc)[:300]}",file=sys.stderr)
        raise
