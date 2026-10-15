"""Generate the social sharing image (Open Graph / Twitter card).

Run from the project root:

    python tools/make_og_image.py

It writes app/static/og-image.png at 1200x630, the size Facebook, LinkedIn,
WhatsApp and X all expect. Kept as a script rather than a hand-made asset so
the wording can follow the product without a designer.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
OUT = Path(__file__).resolve().parents[1] / "app" / "static" / "og-image.png"

BG_TOP = (15, 35, 95)
BG_BOTTOM = (37, 99, 235)
WHITE = (255, 255, 255)
LIGHT = (219, 234, 254)
MUTED = (147, 197, 253)
GREEN = (134, 239, 172)

BOLD_FONTS = [
    r"C:\Windows\Fonts\segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]
REGULAR_FONTS = [
    r"C:\Windows\Fonts\segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def load_font(candidates, size):
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def bold(size):
    return load_font(BOLD_FONTS, size)


def regular(size):
    return load_font(REGULAR_FONTS, size)


def vertical_gradient(width, height, top, bottom):
    strip = Image.new("RGB", (1, height))
    for y in range(height):
        t = y / (height - 1)
        strip.putpixel(
            (0, y), tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        )
    return strip.resize((width, height))


def draw_glow(image):
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    pen = ImageDraw.Draw(glow)
    pen.ellipse((W - 430, -270, W + 50, 210), fill=(255, 255, 255, 26))
    pen.ellipse((W - 300, -190, W - 10, 100), fill=(255, 255, 255, 22))
    pen.ellipse((-260, H - 320, 260, H + 200), fill=(255, 255, 255, 14))
    return Image.alpha_composite(image, glow)


def draw_panel(pen):
    """A small mock of the app window, to the right of the copy."""
    pen.rounded_rectangle((660, 118, 1140, 542), radius=26, fill=WHITE)

    # Window chrome, with the three dots and a URL bar.
    pen.rounded_rectangle((660, 118, 1140, 174), radius=26, fill=(243, 244, 246))
    pen.rectangle((660, 146, 1140, 174), fill=(243, 244, 246))
    for index, colour in enumerate([(248, 113, 113), (250, 204, 21), (74, 222, 128)]):
        cx = 690 + index * 26
        pen.ellipse((cx - 7, 139, cx + 7, 153), fill=colour)
    pen.rounded_rectangle((784, 132, 1088, 160), radius=8, fill=WHITE)

    # Sidebar.
    pen.rectangle((660, 174, 716, 516), fill=(17, 24, 39))
    pen.rounded_rectangle((676, 198, 700, 222), radius=6, fill=(37, 99, 235))
    for y in (242, 286, 330, 374):
        pen.rounded_rectangle((676, y, 700, y + 24), radius=6, fill=(55, 65, 81))

    # Main column: heading, a new-job button, two totals, three job rows.
    pen.rounded_rectangle((742, 202, 902, 222), radius=8, fill=(156, 163, 175))
    pen.rounded_rectangle((1036, 196, 1116, 228), radius=10, fill=(37, 99, 235))

    for x0, x1, accent in ((742, 918, (22, 163, 74)), (936, 1116, (37, 99, 235))):
        pen.rounded_rectangle((x0, 246, x1, 320), radius=12, fill=(239, 246, 255))
        pen.rounded_rectangle((x0 + 16, 264, x0 + 84, 274), radius=5, fill=(156, 163, 175))
        pen.rounded_rectangle((x0 + 16, 288, x0 + 132, 306), radius=6, fill=accent)

    for index, accent in enumerate([(250, 204, 21), (22, 163, 74), (37, 99, 235)]):
        y = 336 + index * 58
        pen.rounded_rectangle((742, y, 1116, y + 46), radius=12, fill=(249, 250, 251))
        pen.rounded_rectangle((758, y + 10, 930, y + 22), radius=6, fill=(156, 163, 175))
        pen.rounded_rectangle((758, y + 28, 860, y + 38), radius=5, fill=(209, 213, 219))
        pen.rounded_rectangle((1060, y + 12, 1100, y + 36), radius=8, fill=accent)


def main():
    image = vertical_gradient(W, H, BG_TOP, BG_BOTTOM).convert("RGBA")
    image = draw_glow(image)
    pen = ImageDraw.Draw(image)

    pill = "BUILT FOR UK TRADESPEOPLE"
    pill_font = bold(20)
    pill_width = pen.textlength(pill, font=pill_font)
    pen.rounded_rectangle((80, 84, 80 + pill_width + 46, 132), radius=24,
                          fill=(255, 255, 255, 32))
    pen.text((102, 97), pill, font=pill_font, fill=LIGHT)

    pen.text((80, 168), "TradeScheduler", font=bold(78), fill=WHITE)
    pen.text((80, 290), "Jobs, quotes, invoices and payments", font=regular(31), fill=LIGHT)
    pen.text((80, 332), "for UK tradespeople.", font=regular(31), fill=LIGHT)
    pen.text((80, 406), "14-day free trial  ·  No card needed", font=bold(27), fill=GREEN)
    pen.text((80, 448), "Cancel anytime  ·  Works on your phone", font=regular(27), fill=MUTED)
    pen.text((80, 522), "thetradescheduler.com", font=bold(30), fill=WHITE)

    draw_panel(pen)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(OUT, "PNG", optimize=True)
    print("wrote", OUT, image.size)


if __name__ == "__main__":
    main()
