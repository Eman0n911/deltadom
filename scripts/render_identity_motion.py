"""Render original code-native motion artwork, not a product execution recording.

Requires Pillow. Does not modify the separately generated editorial illustration.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/assets/brand'
W, H, SCALE = 960, 480, 2
BG, INK, BLUE, CORAL = '#f7f3eb', '#14263e', '#2459df', '#ed8c6b'
MUTED, PAPER, AMBER = '#747c85', '#e6dfd3', '#ac7121'
FONT_PATHS = ['/System/Library/Fonts/SFNS.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
FONT = next((p for p in FONT_PATHS if Path(p).exists()), None)
if FONT is None:
    raise RuntimeError('Install a sans-serif TrueType font and add its path to FONT_PATHS.')


def ease(value):
    value = max(0, min(1, value))
    return value * value * (3 - 2 * value)


def frame(t):
    im = Image.new('RGB', (W*SCALE, H*SCALE), BG)
    d = ImageDraw.Draw(im)

    def box(xy, fill, radius=0, outline=None, width=1):
        d.rounded_rectangle(tuple(round(v*SCALE) for v in xy), radius=radius*SCALE,
                            fill=fill, outline=outline, width=width*SCALE)

    def line(points, fill, width=2):
        d.line([(round(x*SCALE), round(y*SCALE)) for x, y in points], fill=fill,
               width=width*SCALE, joint='curve')

    def ellipse(xy, fill):
        d.ellipse(tuple(round(v*SCALE) for v in xy), fill=fill)

    def polygon(points, fill):
        d.polygon([(round(x*SCALE), round(y*SCALE)) for x, y in points], fill=fill)

    def text(xy, value, size, fill=INK, anchor=None):
        d.text(tuple(round(v*SCALE) for v in xy), value, font=ImageFont.truetype(FONT, size*SCALE),
               fill=fill, anchor=anchor)

    # A paper theatre, rather than a screenshot or a dashboard.
    text((40, 24), 'DeltaDOM', 21)
    text((920, 29), 'IDENTITY-BOUND CLICKS', 12, MUTED, 'ra')
    box((145, 100, 815, 378), '#e9e3d9', 18)
    box((138, 92, 808, 368), '#fffdf8', 18, '#d9d3c8')
    for x in (161, 176, 191):
        ellipse((x, 107, x+6, 113), '#a9adb0')
    line([(138, 128), (808, 128)], '#e5dfd5', 1)
    box((175, 303, 775, 320), '#d5cdbc', 5)
    for x in (210, 367, 524, 681):
        ellipse((x, 324, x+18, 342), '#d9d1c4')

    # All movement is authored illustration. No timing or safety guarantee is implied.
    move = ease((t-1.2)/2.0)
    reset = ease((t-7.5)/1.0)
    move *= 1-reset
    target_x = 270 + 360*move
    swap = ease((t-4.5)/.65) * (1-reset)
    paused = 5.15 <= t < 7.5

    def ticket(cx, cy, fill, mark):
        box((cx-55, cy-66, cx+59, cy+69), '#d3cbbd', 6)
        box((cx-60, cy-72, cx+54, cy+63), fill, 6)
        ellipse((cx-67, cy-9, cx-53, cy+5), '#fffdf8')
        ellipse((cx+47, cy-9, cx+61, cy+5), '#fffdf8')
        fg = '#fffdf8' if fill == BLUE else '#8c8172' if fill == PAPER else '#763a2e'
        if mark == 'triangle':
            polygon([(cx-23, cy-16), (cx-3, cy-48), (cx+17, cy-16)], fg)
        elif mark == 'circle':
            ellipse((cx-20, cy-45, cx+14, cy-11), fg)
        else:
            box((cx-20, cy-43, cx+13, cy-12), fg, 3)
        box((cx-32, cy+11, cx+27, cy+18), fg, 3)
        box((cx-32, cy+27, cx+10, cy+34), fg, 3)

    ticket(450-180*move, 235, PAPER, 'circle')
    ticket(630-180*move, 235, PAPER, 'square')
    lift = 22 * math.sin(math.pi*move)
    if swap < .5:
        ticket(target_x, 235-lift, BLUE, 'triangle')
    else:
        ticket(target_x, 235-lift, CORAL, 'circle')

    cursor_x, cursor_y = target_x+99, 171-lift-12*swap
    start, end = (target_x+54, 233-lift), (cursor_x, cursor_y+12)
    points = []
    for i in range(41):
        u = i/40
        points.append((start[0]+(end[0]-start[0])*u,
                       start[1]+(end[1]-start[1])*u+19*math.sin(math.pi*u)))
    if swap < .5:
        line(points, BLUE, 3)
    else:
        for i in range(0, 36, 8):
            line(points[i:i+4], '#b5a794', 2)
        # A visible pause, not a success checkmark or a guarantee of no prior effects.
        box((target_x+69, 230-lift, target_x+75, 252-lift), AMBER, 1)
        box((target_x+81, 230-lift, target_x+87, 252-lift), AMBER, 1)

    cursor = [(0, 0), (0, 64), (17, 49), (31, 75), (44, 67), (29, 42), (51, 40)]
    coords = [(cursor_x+x*.72, cursor_y+y*.72) for x, y in cursor]
    polygon([(x+3, y+3) for x, y in coords], '#d3cbbd')
    polygon(coords, '#fffdf8')
    line(coords+[coords[0]], INK, 3)

    if paused or swap >= .5:
        title, detail = 'Different record. Click paused.', 'Recheck before continuing.'
    elif move > .04:
        title, detail = 'New position. Same record.', 'Follow the identity, not the slot.'
    else:
        title, detail = 'Keep hold of the intended record.', 'Bind a click to its visible identity.'
    text((480, 386), title, 25, INK, 'ma')
    text((480, 422), detail, 15, MUTED, 'ma')
    text((920, 458), 'Concept animation / not an execution recording', 11, MUTED, 'ra')
    return im.resize((W, H), Image.Resampling.LANCZOS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    frames = [frame(i/12) for i in range(108)]
    # One shared palette prevents frame-to-frame colour flicker.
    palette = Image.new('RGB', (W, H*4))
    for i, index in enumerate([0, 30, 48, 72]):
        palette.paste(frames[index], (0, i*H))
    palette = palette.quantize(colors=96)
    indexed = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    path = OUT/'identity-motion.gif'
    indexed[0].save(path, save_all=True, append_images=indexed[1:], loop=0,
                    duration=[80, 80, 90]*36, optimize=True, disposal=2)
    for name, t in [('identity-motion-still', 3.6), ('identity-motion-paused', 6.0)]:
        frame(t).save(OUT/f'{name}.png')
    with Image.open(path) as result:
        duration = 0
        for i in range(result.n_frames):
            result.seek(i)
            duration += result.info['duration']
        assert duration == 9000, duration
        print(f'{path}: {result.n_frames} frames, {duration} ms, {path.stat().st_size} bytes')


if __name__ == '__main__':
    main()
