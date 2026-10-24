#!/usr/bin/env python3
"""Pictures of the LCD 1602 screens, without hardware.

The screen logic is a line-by-line port of compose() / bigClock() / weather() / startup()
from firmware/src/display.cpp, and the custom glyphs are the same CGRAM bytes, so the
pictures show what the firmware actually writes. Characters come from the HD44780 A00 ROM
(the usual PCF8574 backpack LCD). Needs Pillow.

  python tools/lcd_preview.py              # PNGs + GIF into docs/lcd/
  python tools/lcd_preview.py --out DIR
"""
import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------- character generator ----------

# CGRAM slots 0..5 from lcdInit(); printed as codes 8..13.
GLYPHS = [
    [0x00, 0x00, 0x00, 0x0E, 0x0E, 0x0E, 0x00, 0x00],  # 0: Wi-Fi dot
    [0x1F, 0x1F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],  # 1: bar at the top
    [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F, 0x1F],  # 2: bar at the bottom
    [0x1F, 0x1F, 0x00, 0x00, 0x00, 0x00, 0x1F, 0x1F],  # 3: bars top and bottom
    [0x00, 0x00, 0x00, 0x00, 0x0E, 0x0E, 0x0E, 0x00],  # 4: upper colon dot
    [0x00, 0x0E, 0x0E, 0x0E, 0x00, 0x00, 0x00, 0x00],  # 5: lower colon dot
]

# HD44780 A00 ROM, only the characters the firmware prints. 7 rows; the 8th (cursor row) is empty.
ROM = {
    " ": ["00000"] * 7,
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11111", "00010", "00100", "00010", "00001", "10001", "01110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    "%": ["11000", "11001", "00010", "00100", "01000", "10011", "00011"],
    "\xdf": ["11100", "10100", "11100", "00000", "00000", "00000", "00000"],  # degree sign
    "A": ["01110", "10001", "10001", "10001", "11111", "10001", "10001"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "a": ["00000", "00000", "01110", "00001", "01111", "10001", "01111"],
    "c": ["00000", "00000", "01110", "10000", "10000", "10001", "01110"],
    "e": ["00000", "00000", "01110", "10001", "11111", "10000", "01110"],
    "f": ["00110", "01001", "01000", "11100", "01000", "01000", "01000"],
    "h": ["10000", "10000", "10110", "11001", "10001", "10001", "10001"],
    "i": ["00100", "00000", "01100", "00100", "00100", "00100", "01110"],
    "k": ["10000", "10000", "10010", "10100", "11000", "10100", "10010"],
    "l": ["01100", "00100", "00100", "00100", "00100", "00100", "01110"],
    "n": ["00000", "00000", "10110", "11001", "10001", "10001", "10001"],
    "o": ["00000", "00000", "01110", "10001", "10001", "10001", "01110"],
    "r": ["00000", "00000", "10110", "11001", "10000", "10000", "10000"],
    "t": ["01000", "01000", "11100", "01000", "01000", "01001", "00110"],
    "v": ["00000", "00000", "10001", "10001", "10001", "01010", "00100"],
    "w": ["00000", "00000", "10001", "10001", "10101", "10101", "01010"],
}


def bitmap(ch: str) -> list[int]:
    """8 rows of 5 bits for one character code."""
    code = ord(ch)
    if 8 <= code <= 15:
        return GLYPHS[(code - 8) % 8] if (code - 8) < len(GLYPHS) else [0] * 8
    if code == 0xFF:
        return [0x1F] * 8  # full block
    rows = ROM.get(ch)
    if rows is None:
        raise KeyError(f"no ROM bitmap for {ch!r}; add it to ROM")
    return [int(r, 2) for r in rows] + [0]


# ---------- screens: port of display.cpp ----------

WIFI_DOT, TOP, BOT, BOTH, COLON_UP, COLON_DN = (chr(c) for c in range(8, 14))
FULL, DEG = "\xff", "\xdf"
BIG = [
    [FULL + TOP + FULL, FULL + BOT + FULL],  # 0
    [TOP + FULL + " ", BOT + FULL + BOT],    # 1
    [BOTH + BOTH + FULL, FULL + BOT + BOT],  # 2
    [BOTH + BOTH + FULL, BOT + BOT + FULL],  # 3
    [FULL + BOT + FULL, "  " + FULL],        # 4
    [FULL + BOTH + BOTH, BOT + BOT + FULL],  # 5
    [FULL + BOTH + BOTH, FULL + BOT + FULL], # 6
    [TOP + TOP + FULL, "  " + FULL],         # 7
    [FULL + BOTH + FULL, FULL + BOT + FULL], # 8
    [FULL + BOTH + FULL, BOT + BOT + FULL],  # 9
    [BOT + BOT + BOT, "   "],                # 10: dash, time unknown
]


def big_clock(hh=None, mm=None, ss=0, wifi=True):
    d = [10] * 4 if hh is None else [hh // 10, hh % 10, mm // 10, mm % 10]
    colon = True if hh is None else ss % 2 == 0
    lines = []
    for row in range(2):
        s = ""
        for i in range(4):
            s += "   " if i == 0 and d[0] == 0 else BIG[d[i]][row]
            if i == 1:
                s += (COLON_DN if row else COLON_UP) if colon else " "
            elif i != 3:
                s += " "
        s += (WIFI_DOT if wifi else " ") if row else " "
        lines.append(s)
    return lines


def weather(t, h=None, p=None, wifi=True):
    l1 = f"{t:.1f}" + DEG + "C"
    if h is not None:
        l1 = l1.ljust(12) + f"{h:3.0f}%"
    l2 = f"{p:.0f} hPa" if p is not None else ""
    l2 = l2.ljust(15) + (WIFI_DOT if wifi else " ")
    return [l1, l2]


def startup(msg, hms=None):
    return ["%02d:%02d:%02d" % hms if hms else "--:--:--", msg]


def fit(line):
    return (line + " " * 16)[:16]  # writeLine(): pad to 16 and cut


# ---------- drawing ----------

THEMES = {
    # backlight, lit dot, unlit dot (unlit dots are faintly visible on a real LCD)
    "blue": ((24, 64, 214), (232, 240, 255), (40, 82, 222)),
    "green": ((150, 196, 40), (22, 38, 12), (140, 184, 40)),
}
DOT, GAP, CHAR_GAP, ROW_GAP, PAD = 6, 1, 6, 8, 26


def caption_font():
    """Any system font with Cyrillic (Linux: DejaVu, Windows: Segoe UI / Arial)."""
    for name in ("DejaVuSans.ttf", "segoeui.ttf", "arial.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, 17)
        except OSError:
            pass
    return ImageFont.load_default()


def render(lines, theme="blue", caption=None):
    bg, on, off = THEMES[theme]
    pitch = DOT + GAP
    cw, ch = 5 * pitch - GAP, 8 * pitch - GAP
    w = PAD * 2 + 16 * cw + 15 * CHAR_GAP
    h = PAD * 2 + 2 * ch + ROW_GAP
    cap_h = 34 if caption else 0
    img = Image.new("RGB", (w + 24, h + 24 + cap_h), (18, 18, 20))
    dr = ImageDraw.Draw(img)
    # bezel + glass
    dr.rounded_rectangle((4, 4, w + 19, h + 19), 10, fill=(10, 10, 12))
    dr.rounded_rectangle((12, 12, w + 11, h + 11), 4, fill=bg)
    for r, line in enumerate(lines):
        for c, chv in enumerate(fit(line)):
            x0 = 12 + PAD + c * (cw + CHAR_GAP)
            y0 = 12 + PAD + r * (ch + ROW_GAP)
            for y, bits in enumerate(bitmap(chv)):
                for x in range(5):
                    lit = bits >> (4 - x) & 1
                    px, py = x0 + x * pitch, y0 + y * pitch
                    dr.rectangle((px, py, px + DOT - 1, py + DOT - 1), fill=on if lit else off)
    if caption:
        dr.text((14, h + 30), caption, fill=(200, 200, 208), font=caption_font())
    return img


# Every screen the firmware can show, in the order a user meets them.
SCREENS = [
    ("01-power-on", ["Svitlo-Local", "fw 0.3.0"], "Увімкнення: displayBegin()"),
    ("02-wifi-connecting", startup("WiFi..."), "Перші 30 с: шукає Wi-Fi, часу ще нема"),
    ("03-wifi-ok-no-ntp", startup("WiFi OK"), "Wi-Fi є, NTP ще не відповів (5 с)"),
    ("04-wifi-ok-ntp", startup("WiFi OK", (14, 7, 32)), "Wi-Fi є, NTP відповів"),
    ("05-wifi-no-network", startup("WiFi: no network"), "30 с без мережі (5 с)"),
    ("06-setup-ap", startup("AP SVITLO-LOCAL"), "Перше налаштування: точка SVITLO-LOCAL"),
    ("07-clock", big_clock(14, 7, 0), "Годинник, двокрапка горить, крапка Wi-Fi"),
    ("08-clock-colon-off", big_clock(14, 7, 1), "Годинник, наступна секунда: двокрапка згасла"),
    ("09-clock-morning", big_clock(8, 5, 0), "Ранок: « 8:05», без нуля попереду"),
    ("10-clock-no-wifi", big_clock(14, 7, 0, wifi=False), "Wi-Fi зник: крапки справа внизу нема"),
    ("11-clock-unknown", big_clock(None, None, wifi=False), "Часу нема (нема DS3231 і NTP): «--:--»"),
    ("12-weather", weather(23.5, 53, 1008), "Погода: 3 с з кожних 12 (BME280)"),
    ("13-weather-frost", weather(-12.3, 87, 1021), "Погода взимку"),
    ("14-weather-bmp280", weather(23.5, None, 1008), "BMP280: без вологості"),
]


def cycle_gif(out: Path, theme: str):
    """One 12 s cycle of compose(): 9 s big clock (colon blinks), 3 s weather."""
    frames, durations = [], []
    for sec in range(12):
        lines = weather(23.5, 53, 1008) if sec >= 9 else big_clock(14, 7, sec)
        frames.append(render(lines, theme, f"цикл 12 с, секунда {sec}"))
        durations.append(1000)
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "docs" / "lcd"))
    ap.add_argument("--theme", choices=THEMES, default="blue")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tiles = []
    for name, lines, caption in SCREENS:
        img = render(lines, a.theme, caption)
        img.save(out / f"{name}.png", optimize=True)
        tiles.append(img)
    # contact sheet: all screens on one picture, two columns
    tw, th = tiles[0].size
    cols = 2
    rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (cols * tw, rows * th), (18, 18, 20))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % cols) * tw, (i // cols) * th))
    sheet.save(out / "all-screens.png", optimize=True)
    cycle_gif(out / "cycle.gif", a.theme)
    print(f"{len(tiles)} screens, all-screens.png and cycle.gif in {out}")


if __name__ == "__main__":
    main()
