"""Current ITALIAN SUNRISE VK Ads target: 42876719, daily ad-group budgets.

Keeps the generic legacy one_ad_group module untouched while making the
active target explicit for future manual one-ad uploads.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
from . import one_ad_group

ACTIVE=Path(__file__).resolve().parent/"italian_sunrise_active_target.json"

def main():
    config=json.loads(ACTIVE.read_text(encoding="utf-8"))
    target=int(config["active_vk_ads_campaign_id"])
    template=int(config["target_group_template_id"])
    assert target==42876719 and template==169616554, "Unexpected active VK Ads target configuration"
    if len(sys.argv)<2:
        print("Required: JSON spec path",file=sys.stderr)
        return 2
    path=Path(sys.argv[1])
    if not path.is_file():
        print("Cannot find JSON spec",file=sys.stderr)
        return 2
    spec=json.loads(path.read_text(encoding="utf-8"))
    if spec.get("campaign_id")!=target or spec.get("template_group_id")!=template:
        print("Spec campaign/template must match the current target 42876719 / 169616554",file=sys.stderr)
        return 2
    # No modifications to legacy constants on disk.
    one_ad_group.CAMPAIGN_ID=target
    return one_ad_group.main()

if __name__=="__main__":
    raise SystemExit(main())
