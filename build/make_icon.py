"""Draws the microphone icon and saves it as a multi-size .ico."""
import sys

from PIL import Image, ImageDraw


def draw(size: int) -> Image.Image:
    s = size / 64
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((2 * s, 2 * s, 62 * s, 62 * s), radius=14 * s, fill=(28, 33, 41, 255))
    col = (108, 211, 230, 255)
    w = max(1, round(4 * s))
    d.rounded_rectangle((24 * s, 9 * s, 40 * s, 37 * s), radius=8 * s, fill=col)
    d.arc((16 * s, 20 * s, 48 * s, 45 * s), 0, 180, fill=col, width=w)
    d.line((32 * s, 45 * s, 32 * s, 53 * s), fill=col, width=w)
    d.line((23 * s, 54 * s, 41 * s, 54 * s), fill=col, width=w)
    return im


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "icon.ico"
    draw(256).save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon:", out)
