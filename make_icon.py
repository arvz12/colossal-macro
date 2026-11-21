"""Draws assets/icon.png and assets/icon.ico (run once before building)."""
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = 1024


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


ACCENT = (79, 140, 255)  # the default theme's accent (Midnight); the app recolours its icon to yours at run time


def mixc(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def draw():
    top, bottom = mixc(ACCENT, (255, 255, 255), 0.18), mixc(ACCENT, (0, 0, 0), 0.38)
    grad = Image.new("RGB", (SIZE, SIZE))
    px = grad.load()
    for y in range(SIZE):
        c = lerp(top, bottom, y / (SIZE - 1))
        for x in range(SIZE):
            px[x, y] = c
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=230, fill=255)
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    icon.paste(grad, (0, 0), mask)

    # Heat glow behind the ring
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((250, 250, 774, 774), fill=(255, 255, 255, 70))
    icon = Image.alpha_composite(icon, glow.filter(ImageFilter.GaussianBlur(60)))

    # A thick "C" ring, opening to the right
    ring = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(ring)
    d.arc((200, 200, 824, 824), start=40, end=320, fill=(255, 255, 255, 255), width=150)
    # Steam puffs leaving the opening
    for (cx, cy, r) in ((760, 420, 46), (840, 350, 34), (900, 300, 24)):
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 235))
    icon = Image.alpha_composite(icon, ring)
    return icon


def main():
    out = os.path.join(HERE, "assets")
    os.makedirs(out, exist_ok=True)
    icon = draw()
    icon.resize((256, 256), Image.LANCZOS).save(os.path.join(out, "icon.png"))
    icon.save(os.path.join(out, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon written to", out)


if __name__ == "__main__":
    main()
