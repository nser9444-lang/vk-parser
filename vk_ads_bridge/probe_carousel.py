"""Read-only metadata probe: determine whether VK Ads 3127 can carry 3 photo slides."""
import json
import os
import sys
from .cli import VKAds

def tryget(api,path,params=None):
    try:
        return api.request("GET",path,params=params)
    except Exception as exc:
        return {"request_error_class":type(exc).__name__, "error": str(exc)[:220]}

def main():
    api=VKAds(os.getenv("VK_ADS_CLIENT_ID",""),os.getenv("VK_ADS_CLIENT_SECRET",""))
    result={"read_only":True}
    package=tryget(api,"/api/v2/packages/3127.json",
                    {"fields":"id,name,description,banner_format_id,related_package_ids,objective"})
    result["package_3127"]={k:package.get(k) for k in
        ("id","name","description","banner_format_id","related_package_ids","objective","request_error_class","error")
        if k in package}
    fmt_id=package.get("banner_format_id")
    if isinstance(fmt_id,int):
        banner_fmt=tryget(api,f"/api/v2/banner_formats/{fmt_id}.json")
        result["banner_format"]={k:v for k,v in banner_fmt.items() if k in
                                ("id","name","description","status","patterns","pattern_ids","request_error_class","error")}
    pats=[]
    for offset in range(0,5000,100):
        response=tryget(api,"/api/v2/banner_patterns.json",
            {"fields":"id,name,description,format,status","limit":100,"offset":offset})
        if "request_error_class" in response:
            result["patterns_error"]=response["error"]
            break
        rows=response.get("items",[])
        if not isinstance(rows,list):
            break
        for p in rows:
            roles=[str(x.get("role","")) for x in p.get("format",[]) if isinstance(x,dict)]
            # Keep carousel patterns only (no personally identifying values).
            if "slide" in str(p.get("name","")).lower() or any("slide" in k.lower() for k in roles):
                pats.append({"id":p.get("id"),"name":p.get("name"),"status":p.get("status"),
                             "roles":roles[:45]})
        if len(rows)<100:
            break
    result["carousel_patterns"]=pats[:30]
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
