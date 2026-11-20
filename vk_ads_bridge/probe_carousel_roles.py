"""Read-only summary of carousel banner patterns for VK community messages."""
import json
from .cli import VKAds

def main():
    api=VKAds()
    found=[]
    total=0
    for offset in range(0,1200,50):
        response=api.request("GET","/api/v2/banner_patterns.json",
                            params={"limit":50,"offset":offset})
        items=response.get("items",[])
        if not isinstance(items,list):
            break
        total += len(items)
        for item in items:
            name=str(item.get("name",""))
            fmt=item.get("format",[])
            entries=[(e.get("field",""),e.get("role","")) for e in fmt if isinstance(e,dict)]
            roles=[role for field,role in entries]
            content_roles=[role for field,role in entries if field=="content"]
            carousel=bool("carousel" in name.lower() or
                          sum(("slide_" in r and "image" in r) for r in content_roles)>=3 or
                          sum(r.startswith("image_600x600_slide") for r in content_roles)>=3)
            if carousel:
                found.append({"id":item.get("id"),"name":name,
                              "status":item.get("status"),
                              "image_roles":content_roles,
                              "text_roles":[r for f,r in entries if f=="textblock"],
                              "url_roles":[r for f,r in entries if f=="url"]})
        if len(items)<50:
            break
    print(json.dumps({"read_only":True,"scanned":total,"carousels":found[:90]},ensure_ascii=False))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
