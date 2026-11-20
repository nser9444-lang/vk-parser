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
    package_queries=[
        ("/api/v2/packages.json",{"_id":3127,"fields":"id,name,banner_format_id,description","limit":10}),
        ("/api/v2/packages.json",{"_id":3127,"limit":10}),
        ("/api/v2/packages/3127.json",None),
    ]
    result["packages"]=[]
    for path,params in package_queries:
        data=tryget(api,path,params)
        summary={"endpoint":path, "params":params,"response_type":type(data).__name__}
        if isinstance(data,dict):
            summary["keys"]=list(data.keys())[:15]
            if "items" in data:
                summary["rows"]=[{k:x.get(k) for k in ("id","name","description","banner_format_id")}
                                 for x in data.get("items",[])[:5] if isinstance(x,dict)]
            else:
                summary["object"]={k:data.get(k) for k in
                    ("id","name","description","banner_format_id","request_error_class","error") if k in data}
        result["packages"].append(summary)
    pattern_queries=[
        None,
        {"limit":10},
        {"limit":10,"fields":"id,name,status"},
        {"limit":10,"fields":"id,name,format,status"}
    ]
    result["patterns"]=[]
    for params in pattern_queries:
        data=tryget(api,"/api/v2/banner_patterns.json",params)
        summary={"params":params,"response_type":type(data).__name__}
        if isinstance(data,dict):
            summary["keys"]=list(data.keys())[:10]
            summary["count"]=data.get("count")
            if "items" in data:
                summary["sample"]=[{"id":x.get("id"),"name":x.get("name"),
                                    "roles":[str(y.get("role")) for y in x.get("format",[])
                                             if isinstance(y,dict)]}
                                   for x in data["items"][:3] if isinstance(x,dict)]
            else:
                summary["error"]=str(data.get("error",""))[:120]
        result["patterns"].append(summary)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
