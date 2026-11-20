"""Rebuild authentic ITALIAN SUNRISE post 8764 creatives from three unmodified VK photos.

No image synthesis, no changes to the clothing. Original images are hash-checked
against their first VK ASSETS download. Only layout/resizing + Cyrillic overlays.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent / "test_8764"
ASSETS = ROOT / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

SOURCES = [
    ("photo_01.jpg", "d9d733c5ec60861247fc2fc05e2e96f1a1d2a5472a3ef6ad60e5bd4adb10955d",
     "https://sun9-6.userapi.com/s/v1/ig2/zg24iiBlru-AtQaIlS_rjB-qPBWaotaeuLe0XdNWyQ6dpPVfhBmcLU1rDIx-Z43c3NsCXjJxPIaL0elZ1ETiTP-c.jpg?quality=95&as=32x43,48x64,72x96,108x144,160x213,240x320,360x480,480x640,540x720,640x853,720x960,960x1280&from=bu&cs=960x0"),
    ("photo_02.jpg", "82fccbc881e9ebf5aca74e871f347bc1582a9d71e0113a7c61e22fdec883dcc8",
     "https://sun9-81.userapi.com/s/v1/ig2/pjX8NXInZPjV-vhkLzY_FzjGEVsYg7ObnaWHK4uCZigQ4oDhoKVXmwQjXURkqbX94vKltNWY82QtF8_PkDbjkm0E.jpg?quality=95&as=32x43,48x64,72x96,108x144,160x213,240x320,360x480,480x640,540x720,640x853,720x960,960x1280&from=bu&cs=960x0"),
    ("photo_03.jpg", "10d9e5d0b0e1441ff9536d1367934e0cad4c05f17378c979a65f4e9e48f4cc52",
     "https://sun9-49.userapi.com/s/v1/ig2/VEfywzrxuW0lL-r9zkWBXQsVhudG_VRTfY1GlMa0sa316NgpW-nIRWlpxZODAuMrqiwoesJtJVMjQfOgiBjHPijl.jpg?quality=95&as=32x43,48x64,72x96,108x144,160x213,240x320,360x480,480x640,540x720,640x853,720x960,960x1280&from=bu&cs=960x0")
]

CREAM=(239,237,222)
ROSE=(234,174,173)
DEEP=(29,45,37)
FONT_REG="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def download():
    for name, expected, url in SOURCES:
        host = urlparse(url).hostname or ""
        if not (host == "userapi.com" or host.endswith(".userapi.com")):
            raise ValueError("Only VK public userapi photo sources allowed")
        path=ASSETS / name
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==expected:
            continue
        req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req,timeout=30) as resp:
            blob=resp.read(3_000_001)
        if len(blob)>3_000_000 or hashlib.sha256(blob).hexdigest()!=expected:
            raise ValueError("Source photo checksum mismatch; refuse visual substitutions")
        path.write_bytes(blob)
    return [Image.open(ASSETS / name).convert("RGB") for name,_,_ in SOURCES]


def font(sz, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG,sz)


def gradient(w,h):
    # brand green tonal background, no generative alterations of clothing
    im=Image.new("RGB",(w,h))
    d=ImageDraw.Draw(im)
    for y in range(h):
        v=.65*y/max(1,h)
        r=int(36+v*8);g=int(55+v*8);b=int(44+v*6)
        d.line((0,y,w,y),fill=(r,g,b))
    return im


def panel(canvas,img,x,y,w,h):
    d=ImageDraw.Draw(canvas)
    d.rounded_rectangle((x-5,y-5,x+w+5,y+h+5),radius=20,fill=(230,230,227))
    p=ImageOps.contain(img,(w,h),method=Image.Resampling.LANCZOS)
    bg=Image.new("RGB",(w,h),(230,230,228))
    bg.paste(p,((w-p.width)//2,(h-p.height)//2))
    canvas.paste(bg,(x,y))


def add_text(canvas, text_boxes, x,y,text, size,bold=False, color=CREAM):
    draw=ImageDraw.Draw(canvas)
    f=font(size,bold)
    draw.text((x,y),text,font=f,fill=color)
    b=draw.textbbox((x,y),text,font=f)
    text_boxes.append((b[2]-b[0])*(b[3]-b[1]))
    return b


def labels(canvas,boxes,x,y,scale=1):
    old=add_text(canvas,boxes,x,y,"19 500 ₽",round(28*scale),False)
    sy=(old[1]+old[3])//2
    ImageDraw.Draw(canvas).line((x,sy,old[2],sy),fill=ROSE,width=max(2,round(3*scale)))
    add_text(canvas,boxes,x,y+round(42*scale),"9 750 ₽",round(56*scale),True)


def headline(canvas,boxes,lines,x,y,scale=1):
    for i,line in enumerate(lines):
        add_text(canvas,boxes,x,y+i*round(51*scale),line,round(37*scale),True)


def render(photos,w,h,kind):
    if kind=="wide" and (w,h)!=(1080,607):
        base, area=render(photos,1080,607,"wide")
        return base.resize((w,h),Image.Resampling.LANCZOS),area
    c=gradient(w,h)
    d=ImageDraw.Draw(c);boxes=[]
    if kind=="wide":
        panel(c,photos[2],554,30,440,547)
        d.rounded_rectangle((1008,30,1046,577),radius=6,fill=ROSE)
        d.rounded_rectangle((32,43,513,563),radius=10,outline=(93,111,94),width=2)
        headline(c,boxes,["НЕ ТОЛЬКО","ДЛЯ ОФИСА"],61,117,1)
        d.line((63,255,311,255),fill=ROSE,width=4)
        labels(c,boxes,64,306,1.05)
    elif kind=="square":
        panel(c,photos[2],452,45,580,985)
        d.line((60,74,396,74),fill=ROSE,width=6)
        headline(c,boxes,["НЕ ТОЛЬКО","ДЛЯ ОФИСА"],52,210,.97)
        labels(c,boxes,54,380,1.02)
        d.rounded_rectangle((59,710,378,716),radius=3,fill=ROSE)
    elif kind=="portrait":
        panel(c,photos[2],130,22,820,1055)
        d.line((57,1117,400,1117),fill=ROSE,width=5)
        headline(c,boxes,["НЕ ТОЛЬКО ДЛЯ ОФИСА"],55,1138,.79)
        labels(c,boxes,56,1201,.66)
    elif kind=="story":
        panel(c,photos[2],60,60,960,1350)
        d.rounded_rectangle((36,1450,1045,1879),radius=25,fill=DEEP,outline=(108,123,106),width=2)
        headline(c,boxes,["НЕ ТОЛЬКО ДЛЯ ОФИСА"],75,1504,.9)
        d.line((76,1596,370,1596),fill=ROSE,width=5)
        labels(c,boxes,75,1644,1.12)
    elif kind=="icon":
        # real detail crop from original photo: face, lapel, shoulders, belt
        c=ImageOps.fit(photos[0].crop((145,235,840,930)),(256,256),method=Image.Resampling.LANCZOS)
    else:
        raise ValueError("Unsupported format")
    ratio=sum(boxes)/(w*h)
    if ratio>.15:
        raise ValueError(f"Text area {ratio:.1%} exceeds required 15%")
    return c,ratio


def main():
    photos=download()
    manifest={"source":"https://vk.ru/wall-235449344_8764","post_date":"2026-11-20",
              "product":"Чёрный брючный костюм","source_photos":3,"price":9750,
              "old_price":19500,"image_type":"unaltered_original_photos",
              "renders":[]}
    layouts=[
      ("banner_1x1.jpg",1080,1080,"square"),
      ("banner_4x5.jpg",1080,1350,"portrait"),
      ("banner_16x9.jpg",1600,900,"wide"),
      ("banner_9x16.jpg",1080,1920,"story"),
      ("ad_icon_256.jpg",256,256,"icon"),
      ("ad_image_600x600.jpg",600,600,"ad_square")
    ]
    for name,w,h,kind in layouts:
        if kind=="ad_square":
            image,share=render(photos,1080,1080,"square")
            image=image.resize((600,600),Image.Resampling.LANCZOS)
        else:
            image,share=render(photos,w,h,kind)
        image.save(ASSETS/name,quality=94,optimize=True)
        manifest["renders"].append({"file":name,"width":w,"height":h,
                                    "text_area_ratio":round(share,4)})
    # Three true separate photo slides; no synthesizing or cropping the clothing.
    for i, photo in enumerate(photos[:3], 1):
        fitted = ImageOps.contain(photo, (600,600), method=Image.Resampling.LANCZOS)
        out = Image.new("RGB", (600,600), (243,243,242))
        out.paste(fitted, ((600-fitted.width)//2, (600-fitted.height)//2))
        filename = f"carousel_photo_{i}.jpg"
        out.save(ASSETS/filename, quality=95)
        manifest["renders"].append({"file":filename,"width":600,"height":600,
                                    "type":"separate_original_product_photo"})
    text=("Нужен костюм для встреч и выходов, но не хочется выглядеть как в строгой офисной форме? "
          "У этой модели жакет с акцентными плечами и поясом, а брюки — прямого кроя. "
          "Получается выразительный образ без сложного подбора комплекта.\n\n"
          "Цена по публикации: 9 750 ₽ вместо 19 500 ₽.\n\n"
          "Напишите «+» в сообщения: уточним наличие, поможем с мерками и расскажем об условиях сертификата 5 000 ₽.")
    job={
       "campaign_id":42378407,
       "template_group_id":169040836,
       "group_name":"ITALIAN SUNRISE | Сообщения | Костюм 8764 | 20.11.2026",
       "landing_url":"https://vk.ru/italiansunrise_sochi",
       "ad":{"name":"Костюм чёрный | 9 750 ₽ | Пост 8764",
             "content":{"icon_256x256":"assets/ad_icon_256.jpg",
                        "image_600x600":"assets/ad_image_600x600.jpg",
                        "image_600x600_slide_1":"assets/carousel_photo_1.jpg",
                        "image_600x600_slide_2":"assets/carousel_photo_2.jpg",
                        "image_600x600_slide_3":"assets/carousel_photo_3.jpg"},
             "textblocks":{"text_2000":{"text":text},
                           "title_40_vkads":{"text":"Не только для офиса"},
                           "cta_community_vk":{"text":"contactUs"},
                           "about_company_115":{"text":"Проверяется по действующему объявлению"}}}
    }
    (ROOT/"job.json").write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding="utf-8")
    (ROOT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"prepared":True,"photo_count":3,"renders":manifest["renders"],
                      "campaign_id":42378407,"writing_to_vk":False},ensure_ascii=False))


if __name__=="__main__":
    main()
