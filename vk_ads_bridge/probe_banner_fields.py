"""Inspect available text blocks of existing message ads, without printing their values."""
import json
import os
import sys
from .cli import VKAds
from .one_ad_group import CAMPAIGN_ID

def main():
    api=VKAds()
    checks={}
    for params in (
        {"_campaign_id":"169040836","fields":"id,status,textblocks,content,urls","limit":5},
        {"_ad_group_id":"169040836","fields":"id,status,textblocks,content,urls","limit":5},
    ):
        try:
            data=api.request("GET","/api/v2/banners.json",params=params)
            rows=data.get("items",[])
            checks[next(iter(params))]={
                "count":len(rows),
                "sample":[{"id":item.get("id"),
                           "textblock_keys":list((item.get("textblocks") or {}).keys()),
                           "has_legal":bool(((item.get("textblocks") or {}).get("about_company_115") or {}).get("text")),
                           "content_keys":list((item.get("content") or {}).keys())}
                          for item in rows[:2]]
            }
        except Exception as exc:
            checks[next(iter(params))]={"error_type":type(exc).__name__}
    print(json.dumps({"campaign":CAMPAIGN_ID,"read_only":True,"checks":checks},ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
