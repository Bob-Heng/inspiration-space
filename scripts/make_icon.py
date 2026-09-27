"""应用图标变体生成器：逆飞的流星雨 + 焰火 + 星空，共 5 幅候选。

运行：backend/venv/Scripts/python scripts/make_icon.py
输出：scripts/icon/variants/v1.png ~ v5.png
"""

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SIZE = 512
SS = 4
W = SIZE * SS
OUT = Path(__file__).resolve().parent / "icon" / "variants"
OUT.mkdir(parents=True, exist_ok=True)


def lerp(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def sky(palette):
    """palette: (top, mid, bottom) 夜空渐变。"""
    img = Image.new("RGB", (W, W))
    px = img.load()
    top, mid, bot = palette
    for y in range(W):
        t = y / W
        c = lerp(top, mid, t / 0.55) if t < 0.55 else lerp(mid, bot, (t - 0.55) / 0.45)
        for x in range(W):
            px[x, y] = c
    return img.convert("RGBA")


def add_stars(img, seed, density=200, bright=10):
    rng = random.Random(seed)
    layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(density):
        x, y = rng.uniform(0, W), rng.uniform(0, W * 0.9)
        r = rng.uniform(0.6, 2.0) * SS
        a = int(rng.uniform(70, 210))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, a))
    for _ in range(bright):
        x, y = rng.uniform(0, W), rng.uniform(0, W * 0.75)
        r = rng.uniform(2.0, 3.0) * SS
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 240, 230))
        arm = r * 4
        d.line([x - arm, y, x + arm, y], fill=(255, 255, 240, 90), width=SS)
        d.line([x, y - arm, x, y + arm], fill=(255, 255, 240, 90), width=SS)
    layer = layer.filter(ImageFilter.GaussianBlur(SS * 0.4))
    return Image.alpha_composite(img, layer)


def firework(img, cx, cy, radius, color, seed, arms=16):
    r2 = random.Random(seed)
    layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse(
        [cx - radius * 0.3, cy - radius * 0.3, cx + radius * 0.3, cy + radius * 0.3],
        fill=color + (210,),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius * 0.2))
    layer = Image.alpha_composite(layer, glow)
    d = ImageDraw.Draw(layer)
    for i in range(arms):
        ang = 2 * math.pi * i / arms + r2.uniform(-0.08, 0.08)
        ln = radius * r2.uniform(0.6, 1.0)
        x2, y2 = cx + math.cos(ang) * ln, cy + math.sin(ang) * ln
        d.line([cx, cy, x2, y2], fill=color + (190,), width=int(2 * SS))
        pr = 2.4 * SS
        d.ellipse([x2 - pr, y2 - pr, x2 + pr, y2 + pr], fill=color + (235,))
    layer = layer.filter(ImageFilter.GaussianBlur(SS * 0.3))
    return Image.alpha_composite(img, layer)


def meteor(base, hx, hy, length, width, angle_deg, seed, sparks=8):
    """亮核在 (hx,hy)，向 angle 反方向拖尾；angle 为飞行方向（度，逆时针）。"""
    r2 = random.Random(seed)
    layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ang = math.radians(angle_deg)
    dx, dy = math.cos(ang), math.sin(ang)
    steps = 70
    for i in range(steps):
        t = i / steps
        dist = length * t
        cx, cy = hx - dx * dist, hy + dy * dist
        wdt = width * (1 - t) ** 0.8 + 1
        if t < 0.22:
            col = (255, 248, 215)
        elif t < 0.55:
            col = (255, 208, 105)
        else:
            col = (255, 138, 72)
        alpha = int(245 * (1 - t) ** 1.25)
        d.ellipse([cx - wdt, cy - wdt, cx + wdt, cy + wdt], fill=col + (alpha,))
    halo = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    hr = width * 3.2
    hd.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=(255, 232, 170, 230))
    halo = halo.filter(ImageFilter.GaussianBlur(width * 2.2))
    layer = Image.alpha_composite(layer, halo)
    d = ImageDraw.Draw(layer)
    hr2 = width * 1.5
    d.ellipse([hx - hr2, hy - hr2, hx + hr2, hy + hr2], fill=(255, 253, 238, 255))
    for _ in range(sparks):
        t = r2.uniform(0.1, 0.95)
        dist = length * t
        cx = hx - dx * dist + r2.uniform(-7, 7) * SS
        cy = hy + dy * dist + r2.uniform(-7, 7) * SS
        pr = r2.uniform(1.0, 2.2) * SS
        d.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=(255, 222, 152, 175))
    layer = layer.filter(ImageFilter.GaussianBlur(SS * 0.35))
    return Image.alpha_composite(base, layer)


def finish(img, path):
    mask = Image.new("L", (W, W), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, W, W], radius=W * 0.18, fill=255)
    img.putalpha(mask)
    img.resize((SIZE, SIZE), Image.LANCZOS).save(path)


NIGHT = ((8, 16, 46), (16, 38, 88), (24, 62, 120))          # 经典夜空蓝
TEAL = ((6, 24, 52), (14, 58, 96), (20, 92, 128))           # 参考图偏青的湖蓝
DUSK = ((14, 14, 44), (40, 32, 92), (96, 56, 110))          # 带紫的暮色

# 角度约定：0=向右，逆时针为正。飞向左上约 200°，飞向正上偏右约 255°（屏幕坐标 y 向下）
variants = {}


def v1():
    """三颗主流星齐飞左上，右上金色焰火。"""
    img = add_stars(sky(NIGHT), seed=42)
    img = firework(img, W * 0.80, W * 0.24, W * 0.15, (255, 196, 90), seed=7)
    img = meteor(img, W * 0.58, W * 0.20, W * 0.46, 5.2 * SS, 200, seed=1)
    img = meteor(img, W * 0.84, W * 0.42, W * 0.34, 3.6 * SS, 205, seed=2)
    img = meteor(img, W * 0.34, W * 0.38, W * 0.28, 3.0 * SS, 195, seed=3)
    return img


def v2():
    """一颗超亮主流星斜贯画面，拖尾撒光点，左下暖橙焰火。"""
    img = add_stars(sky(TEAL), seed=9, density=230)
    img = meteor(img, W * 0.66, W * 0.30, W * 0.62, 6.5 * SS, 210, seed=5, sparks=14)
    img = meteor(img, W * 0.30, W * 0.16, W * 0.22, 2.6 * SS, 200, seed=6)
    img = firework(img, W * 0.22, W * 0.68, W * 0.13, (255, 150, 110), seed=11)
    return img


def v3():
    """密集流星阵（5 颗）从右下向左上逆飞，暮色紫底。"""
    img = add_stars(sky(DUSK), seed=77, density=170)
    img = meteor(img, W * 0.74, W * 0.14, W * 0.40, 4.6 * SS, 200, seed=21)
    img = meteor(img, W * 0.88, W * 0.36, W * 0.30, 3.2 * SS, 203, seed=22)
    img = meteor(img, W * 0.60, W * 0.34, W * 0.26, 2.8 * SS, 197, seed=23)
    img = meteor(img, W * 0.46, W * 0.12, W * 0.20, 2.2 * SS, 192, seed=24)
    img = meteor(img, W * 0.30, W * 0.44, W * 0.18, 2.0 * SS, 206, seed=25)
    img = firework(img, W * 0.16, W * 0.78, W * 0.12, (255, 180, 100), seed=26)
    return img


def v4():
    """流星近乎竖直向上逆飞（正面'逆飞'），底部地平线微亮。"""
    img = add_stars(sky(((10, 18, 50), (18, 44, 96), (40, 90, 140))), seed=5, density=210)
    img = meteor(img, W * 0.50, W * 0.18, W * 0.55, 6.0 * SS, 262, seed=31)
    img = meteor(img, W * 0.74, W * 0.30, W * 0.36, 3.4 * SS, 250, seed=32)
    img = meteor(img, W * 0.26, W * 0.36, W * 0.30, 3.0 * SS, 272, seed=33)
    img = firework(img, W * 0.80, W * 0.62, W * 0.12, (255, 190, 100), seed=34)
    return img


def v5():
    """双主流星交叉（X 构图），两处焰火呼应，星空偏青。"""
    img = add_stars(sky(TEAL), seed=64, density=190)
    img = firework(img, W * 0.20, W * 0.22, W * 0.12, (255, 200, 110), seed=41)
    img = firework(img, W * 0.82, W * 0.70, W * 0.10, (255, 150, 110), seed=42)
    img = meteor(img, W * 0.68, W * 0.16, W * 0.52, 5.6 * SS, 205, seed=43)
    img = meteor(img, W * 0.30, W * 0.44, W * 0.40, 4.4 * SS, 232, seed=44)
    return img


for name, fn in [("v1", v1), ("v2", v2), ("v3", v3), ("v4", v4), ("v5", v5)]:
    finish(fn(), OUT / f"{name}.png")
    print("已生成", f"{name}.png")


def final_icon():
    """定稿：初版构图（用户选定），流星拖尾加长约 1.5 倍，位置不变。"""
    img = add_stars(sky(NIGHT), seed=42, density=180)
    img = firework(img, W * 0.78, W * 0.30, W * 0.16, (255, 196, 90), seed=7)   # 右上金
    img = firework(img, W * 0.20, W * 0.62, W * 0.11, (255, 150, 110), seed=11)  # 左下橙
    img = meteor(img, W * 0.60, W * 0.16, W * 0.62, 3.4 * SS, 200, seed=1)
    img = meteor(img, W * 0.82, W * 0.34, W * 0.45, 2.4 * SS, 205, seed=2)
    img = meteor(img, W * 0.38, W * 0.30, W * 0.38, 2.2 * SS, 195, seed=3)
    img = meteor(img, W * 0.70, W * 0.52, W * 0.30, 1.8 * SS, 210, seed=4)
    img = meteor(img, W * 0.30, W * 0.48, W * 0.24, 1.5 * SS, 192, seed=5)
    return img


FINAL_DIR = Path(__file__).resolve().parent / "icon"
img = final_icon()
mask = Image.new("L", (W, W), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, W, W], radius=W * 0.18, fill=255)
img.putalpha(mask)
final = img.resize((SIZE, SIZE), Image.LANCZOS)
final.save(FINAL_DIR / "icon-512.png")
final.resize((256, 256), Image.LANCZOS).save(FINAL_DIR / "icon-256.png")
final.save(
    FINAL_DIR / "favicon.ico",
    sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
print("定稿已生成: icon-512.png / icon-256.png / favicon.ico")
