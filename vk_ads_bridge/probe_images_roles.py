"""Inspect only media role names of VK Ads community-message patterns (GET-only)."""
import json
from .cli import VKAds

def main():
    api=VKAds()
    matches=[]
    for offset in range(0,700,50):
        result=api.request("GET","/api/v2/banner_patterns.json",
                           params={"limit":50,"offset":offset})
        items=result.get("items",[])
        for item in items:
            fields=item.get("format") or []
            txt=[x.get("role") for x in fields if x.get("field")=="textblock"]
            img=[x.get("role") for x in fields if x.get("field")=="content"]
            if ("cta_community_vk" in txt or "image_1080x1350" in img or
                "image_607x1080" in img):
                matches.append({
                    "id":item.get("id"),"name":item.get("name"),
                    "image_roles":img,"text_roles":txt
                })
        if len(items)<50:break
    print(json.dumps({"read_only":True,"matching_patterns":matches[:75]},ensure_ascii=False))
if __name__=="__main__":main()
