import re, base64, io, os, json
from PIL import Image, ImageDraw, ImageFilter

# 1) Take the logo out of the splash picture inside the app
html = open("index.html", encoding="utf-8").read()
m = re.search(r'id="splash"><img class="spi"[^>]*?src="data:image/[a-z]+;base64,([A-Za-z0-9+/=]+)"', html)
assert m, "splash picture not found"
poster = Image.open(io.BytesIO(base64.b64decode(m.group(1)))).convert("RGB")
W, H = poster.size
k = W / 887.0
cx, cy, half = int(438 * k), int(674 * k), int(170 * k)
mark = poster.crop((cx - half, cy - half, cx + half, cy + half))
mask = Image.new("L", mark.size, 0)
ImageDraw.Draw(mask).ellipse((0, 0, mark.size[0] - 1, mark.size[1] - 1), fill=255)
mask = mask.filter(ImageFilter.GaussianBlur(2))
mark = mark.convert("RGBA")
white = Image.new("RGBA", mark.size, (255, 255, 255, 255))
mark = Image.composite(mark, white, mask)

def sized(img, s):
    return img.resize((s, s), Image.LANCZOS)

res = "android/app/src/main/res"
dens = {"mdpi": (48, 108), "hdpi": (72, 162), "xhdpi": (96, 216), "xxhdpi": (144, 324), "xxxhdpi": (192, 432)}
for d, (legacy, adaptive) in dens.items():
    folder = os.path.join(res, "mipmap-" + d)
    os.makedirs(folder, exist_ok=True)
    # normal icon: white rounded square with the logo
    base = Image.new("RGBA", (legacy, legacy), (0, 0, 0, 0))
    ImageDraw.Draw(base).rounded_rectangle((0, 0, legacy - 1, legacy - 1), radius=int(legacy * 0.22), fill=(255, 255, 255, 255))
    inner = int(legacy * 0.84)
    base.alpha_composite(sized(mark, inner), ((legacy - inner) // 2, (legacy - inner) // 2))
    base.save(os.path.join(folder, "ic_launcher.png"))
    # round icon
    rnd = Image.new("RGBA", (legacy, legacy), (0, 0, 0, 0))
    ImageDraw.Draw(rnd).ellipse((0, 0, legacy - 1, legacy - 1), fill=(255, 255, 255, 255))
    inner = int(legacy * 0.86)
    rnd.alpha_composite(sized(mark, inner), ((legacy - inner) // 2, (legacy - inner) // 2))
    rnd.save(os.path.join(folder, "ic_launcher_round.png"))
    # adaptive icon foreground (logo kept inside the safe zone)
    fg = Image.new("RGBA", (adaptive, adaptive), (0, 0, 0, 0))
    inner = int(adaptive * 0.64)
    fg.alpha_composite(sized(mark, inner), ((adaptive - inner) // 2, (adaptive - inner) // 2))
    fg.save(os.path.join(folder, "ic_launcher_foreground.png"))

# adaptive icon background = white
os.makedirs(os.path.join(res, "values"), exist_ok=True)
open(os.path.join(res, "values", "ic_launcher_background.xml"), "w").write(
    '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#FFFFFF</color>\n</resources>\n')

# 2) Make the window and system bars match the splash picture (no dark frame)
sp = os.path.join(res, "values", "styles.xml")
st = open(sp, encoding="utf-8").read()
items = ('<item name="android:background">@null</item>\n'
         '        <item name="android:statusBarColor">#F6FAFE</item>\n'
         '        <item name="android:navigationBarColor">#F6FAFE</item>\n'
         '        <item name="android:windowLightStatusBar">true</item>\n'
         '        <item name="android:windowLightNavigationBar">true</item>')
new, n = re.subn(r'<item name="android:background">@null</item>', items, st)
print("styles edited:", n)
open(sp, "w", encoding="utf-8").write(new)

# 3) Web view background colour
cp = "capacitor.config.json"
cfg = json.load(open(cp))
cfg["backgroundColor"] = "#F6FAFE"
json.dump(cfg, open(cp, "w"), indent=2)

# 4) Make the page itself fill the whole screen
w = open("www/index.html", encoding="utf-8").read()
css = '<style>html,body{margin:0;padding:0}#splash{position:fixed;top:0;left:0;right:0;bottom:0;width:100%;height:100%;background:#f6fafe!important}#splash .spi{padding:0!important;margin:0!important;border:0!important;gap:0!important;background:transparent!important;box-sizing:border-box!important;display:block!important;width:100%!important;height:100%!important;object-fit:cover!important}#splash .spm{background:transparent!important;padding:0!important;flex:none!important;overflow:visible!important;display:block!important;gap:0!important}#splash .spf{padding:0!important}</style>'
assert "</head>" in w
w = w.replace("</head>", css + "</head>", 1)
open("www/index.html", "w", encoding="utf-8").write(w)
print("branding done")
