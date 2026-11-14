import math
import os
import random
import struct
import time
import zlib


WIDTH = 1024
HEIGHT = 1024
PIXELS = bytearray(WIDTH * HEIGHT * 3)
BOWL_CX = 512.0
BOWL_CY = 560.0
FOOD_SCALE_X = 400 / 340
FOOD_SCALE_Y = 350 / 300
FOOD_SCALE = (FOOD_SCALE_X + FOOD_SCALE_Y) * 0.5


def set_px(x, y, color, alpha=1.0):
    if not (0 <= x < WIDTH and 0 <= y < HEIGHT) or alpha <= 0.0:
        return
    i = (y * WIDTH + x) * 3
    if alpha >= 1.0:
        PIXELS[i] = color[0]
        PIXELS[i + 1] = color[1]
        PIXELS[i + 2] = color[2]
        return
    inv = 1.0 - alpha
    PIXELS[i] = int(PIXELS[i] * inv + color[0] * alpha + 0.5)
    PIXELS[i + 1] = int(PIXELS[i + 1] * inv + color[1] * alpha + 0.5)
    PIXELS[i + 2] = int(PIXELS[i + 2] * inv + color[2] * alpha + 0.5)


def draw(shape_test, bbox, color, alpha=1.0):
    x0 = max(0, int(math.floor(bbox[0])))
    y0 = max(0, int(math.floor(bbox[1])))
    x1 = min(WIDTH, int(math.ceil(bbox[2])))
    y1 = min(HEIGHT, int(math.ceil(bbox[3])))
    color_at = color if callable(color) else lambda _x, _y: color
    for y in range(y0, y1):
        sy0 = y + 0.25
        sy1 = y + 0.75
        for x in range(x0, x1):
            sx0 = x + 0.25
            sx1 = x + 0.75
            coverage = (
                shape_test(sx0, sy0)
                + shape_test(sx1, sy0)
                + shape_test(sx0, sy1)
                + shape_test(sx1, sy1)
            ) * 0.25
            if coverage:
                set_px(x, y, color_at(x + 0.5, y + 0.5), alpha * coverage)


def ellipse(cx, cy, rx, ry, rot_deg=0):
    angle = math.radians(rot_deg)
    cs, sn = math.cos(angle), math.sin(angle)
    inv_rx2, inv_ry2 = 1.0 / (rx * rx), 1.0 / (ry * ry)

    def test(x, y):
        dx, dy = x - cx, y - cy
        u = dx * cs + dy * sn
        v = -dx * sn + dy * cs
        return u * u * inv_rx2 + v * v * inv_ry2 <= 1.0

    extent_x = math.sqrt((rx * cs) ** 2 + (ry * sn) ** 2)
    extent_y = math.sqrt((rx * sn) ** 2 + (ry * cs) ** 2)
    return test, (cx - extent_x, cy - extent_y, cx + extent_x, cy + extent_y)


def polygon(points):
    def test(x, y):
        inside = False
        j = len(points) - 1
        for i, (xi, yi) in enumerate(points):
            xj, yj = points[j]
            if (yi > y) != (yj > y):
                crossing = (xj - xi) * (y - yi) / (yj - yi) + xi
                if x < crossing:
                    inside = not inside
            j = i
        return inside

    return test, (
        min(p[0] for p in points),
        min(p[1] for p in points),
        max(p[0] for p in points),
        max(p[1] for p in points),
    )


def capsule(x1, y1, x2, y2, radius):
    dx, dy = x2 - x1, y2 - y1
    length2 = dx * dx + dy * dy
    radius2 = radius * radius

    def test(x, y):
        if length2 == 0:
            return (x - x1) ** 2 + (y - y1) ** 2 <= radius2
        t = ((x - x1) * dx + (y - y1) * dy) / length2
        t = max(0.0, min(1.0, t))
        px, py = x1 + t * dx, y1 + t * dy
        return (x - px) ** 2 + (y - py) ** 2 <= radius2

    return test, (
        min(x1, x2) - radius,
        min(y1, y2) - radius,
        max(x1, x2) + radius,
        max(y1, y2) + radius,
    )


def ring(cx, cy, radius, width):
    half = width * 0.5
    inner2 = max(0.0, radius - half) ** 2
    outer2 = (radius + half) ** 2

    def test(x, y):
        d2 = (x - cx) ** 2 + (y - cy) ** 2
        return inner2 <= d2 <= outer2

    extent = radius + half
    return test, (cx - extent, cy - extent, cx + extent, cy + extent)


def arc_ring(cx, cy, radius, width, start_deg, end_deg):
    base, bbox = ring(cx, cy, radius, width)

    def test(x, y):
        if not base(x, y):
            return False
        angle = math.degrees(math.atan2(y - cy, x - cx))
        if start_deg <= end_deg:
            return start_deg <= angle <= end_deg
        return angle >= start_deg or angle <= end_deg

    return test, bbox


def fill_ellipse(cx, cy, rx, ry, color, alpha=1.0, rot_deg=0):
    test, bbox = ellipse(cx, cy, rx, ry, rot_deg)
    draw(test, bbox, color, alpha)


def fill_capsule(x1, y1, x2, y2, radius, color, alpha=1.0):
    test, bbox = capsule(x1, y1, x2, y2, radius)
    draw(test, bbox, color, alpha)


def food_point(x, y):
    return (
        BOWL_CX + (x - BOWL_CX) * FOOD_SCALE_X,
        BOWL_CY + (y - BOWL_CY) * FOOD_SCALE_Y,
    )


def food_ellipse(cx, cy, rx, ry, color, alpha=1.0, rot_deg=0):
    x, y = food_point(cx, cy)
    test, bbox = ellipse(x, y, rx * FOOD_SCALE_X, ry * FOOD_SCALE_Y, rot_deg)
    draw(test, bbox, color, alpha)


def food_capsule(x1, y1, x2, y2, radius, color, alpha=1.0):
    x1, y1 = food_point(x1, y1)
    x2, y2 = food_point(x2, y2)
    test, bbox = capsule(x1, y1, x2, y2, radius * FOOD_SCALE)
    draw(test, bbox, color, alpha)


def food_ring(cx, cy, radius, width, color, alpha=1.0):
    x, y = food_point(cx, cy)
    test, bbox = ring(x, y, radius * FOOD_SCALE, width * FOOD_SCALE)
    draw(test, bbox, color, alpha)


def food_arc_ring(cx, cy, radius, width, start_deg, end_deg, color, alpha=1.0):
    x, y = food_point(cx, cy)
    test, bbox = arc_ring(x, y, radius * FOOD_SCALE, width * FOOD_SCALE, start_deg, end_deg)
    draw(test, bbox, color, alpha)


def food_polygon(points, color, alpha=1.0):
    test, bbox = polygon([food_point(x, y) for x, y in points])
    draw(test, bbox, color, alpha)


def radial_glow(cx, cy, radius, color, strength):
    x0, x1 = max(0, int(cx - radius)), min(WIDTH, int(cx + radius + 1))
    y0, y1 = max(0, int(cy - radius)), min(HEIGHT, int(cy + radius + 1))
    radius2 = radius * radius
    for y in range(y0, y1):
        dy2 = (y + 0.5 - cy) ** 2
        for x in range(x0, x1):
            d = math.sqrt((x + 0.5 - cx) ** 2 + dy2) / radius
            falloff = max(0.0, 1.0 - d) ** 2
            if falloff:
                set_px(x, y, color, strength * falloff)


def radial_glow_additive(cx, cy, radius, color, strength):
    x0, x1 = max(0, int(cx - radius)), min(WIDTH, int(cx + radius + 1))
    y0, y1 = max(0, int(cy - radius)), min(HEIGHT, int(cy + radius + 1))
    for y in range(y0, y1):
        dy2 = (y + 0.5 - cy) ** 2
        for x in range(x0, x1):
            d = math.sqrt((x + 0.5 - cx) ** 2 + dy2) / radius
            falloff = max(0.0, 1.0 - d) ** 2
            if falloff:
                i = (y * WIDTH + x) * 3
                amount = strength * falloff
                PIXELS[i] = min(255, int(PIXELS[i] + color[0] * amount + 0.5))
                PIXELS[i + 1] = min(255, int(PIXELS[i + 1] + color[1] * amount + 0.5))
                PIXELS[i + 2] = min(255, int(PIXELS[i + 2] + color[2] * amount + 0.5))


def soft_steam_blob(cx, cy, rx, ry, strength):
    x0, x1 = max(0, int(cx - rx - 1)), min(WIDTH, int(cx + rx + 2))
    y0, y1 = max(0, int(cy - ry - 1)), min(HEIGHT, int(cy + ry + 2))
    for y in range(y0, y1):
        ny = (y + 0.5 - cy) / ry
        for x in range(x0, x1):
            nx = (x + 0.5 - cx) / rx
            d2 = nx * nx + ny * ny
            if d2 < 1.0:
                alpha = strength * math.exp(-3.2 * d2)
                set_px(x, y, (255, 249, 238), alpha)


def make_table():
    top, bottom = (64, 40, 26), (30, 18, 12)
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        color = tuple(int(a * (1.0 - t) + b * t + 0.5) for a, b in zip(top, bottom))
        row = bytes(color) * WIDTH
        start = y * WIDTH * 3
        PIXELS[start:start + WIDTH * 3] = row

    radial_glow_additive(400, 300, 700, (255, 190, 110), 0.10)

    # Fine, low-contrast grain keeps the table tactile without competing with the bowl.
    rng = random.Random(19)
    for _ in range(34):
        y = rng.randrange(20, HEIGHT - 20)
        x = rng.randrange(0, WIDTH - 100)
        length = rng.randrange(35, 180)
        shade = rng.choice(((105, 66, 42), (16, 10, 7)))
        fill_capsule(x, y, min(WIDTH - 1, x + length), y + rng.uniform(-1.5, 1.5), 0.7, shade, 0.12)

    # The inverse radial falloff darkens the perimeter into a soft vignette.
    cx, cy, radius = 512.0, 512.0, 720.0
    for y in range(HEIGHT):
        dy2 = (y + 0.5 - cy) ** 2
        for x in range(WIDTH):
            d = math.sqrt((x + 0.5 - cx) ** 2 + dy2) / radius
            alpha = 0.35 * min(1.0, d) ** 2
            if alpha:
                set_px(x, y, (0, 0, 0), alpha)


def draw_broth():
    cx, cy = food_point(512.0, 552.0)
    rx, ry = 292.0 * FOOD_SCALE_X, 252.0 * FOOD_SCALE_Y
    test, bbox = ellipse(cx, cy, rx, ry)

    def amber_at(x, y):
        d = math.sqrt(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2)
        t = min(1.0, d)
        # A luminous center rolls into a deeper, roasted broth at its edge.
        t = t * t * (3.0 - 2.0 * t)
        inner, outer = (205, 132, 55), (105, 54, 27)
        return tuple(int(a * (1.0 - t) + b * t + 0.5) for a, b in zip(inner, outer))

    draw(test, bbox, amber_at)

    # Fine concentric light on the upper-left broth catches the window.
    for radius, start, end in ((201, 202, 249), (224, 207, 238)):
        test, bbox = arc_ring(cx, cy, radius * FOOD_SCALE, 5 * FOOD_SCALE, start, end)
        draw(test, bbox, (255, 231, 173), 0.35)
    soft_steam_blob(*food_point(460, 376), 96 * FOOD_SCALE_X, 27 * FOOD_SCALE_Y, 0.24)

    rng = random.Random(31)
    for _ in range(6):
        x = rng.uniform(340, 685)
        y = rng.uniform(390, 710)
        if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 < 0.78:
            r = rng.uniform(7, 14)
            food_ellipse(x, y, r, r * 0.78, (255, 211, 125), 0.33)
            food_ellipse(x - 2, y - 2, r * 0.35, r * 0.28, (255, 239, 191), 0.3)


def draw_noodle_swirl():
    cx, cy = 470.0, 560.0
    for index, base_radius in enumerate((40, 62, 84, 106, 128)):
        phase = index * 0.83
        points = []
        for step in range(31):
            angle = math.radians(step * 12)
            radius = base_radius + 5.5 * math.sin(angle * 3.0 + phase)
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        for a, b in zip(points, points[1:]):
            food_capsule(a[0] + 1, a[1] + 2, b[0] + 1, b[1] + 2, 4.7, (132, 78, 35), 0.52)
            food_capsule(a[0], a[1], b[0], b[1], 3.6, (247, 224, 168), 0.97)
            if int(a[0] + a[1]) % 3 == 0:
                food_capsule(a[0] - 0.7, a[1] - 1.0, b[0] - 0.7, b[1] - 1.0, 0.9, (255, 246, 213), 0.55)


def draw_pork(cx, cy):
    food_ellipse(cx + 2, cy + 5, 59, 57, (65, 36, 25), 0.35)
    scaled_cx, scaled_cy = food_point(cx, cy)
    scaled_rx, scaled_ry = 57 * FOOD_SCALE_X, 55 * FOOD_SCALE_Y
    test, bbox = ellipse(scaled_cx, scaled_cy, scaled_rx, scaled_ry, -8)

    def pork_tone(x, y):
        d = min(1.0, math.sqrt(((x - scaled_cx) / scaled_rx) ** 2 + ((y - scaled_cy) / scaled_ry) ** 2))
        light = max(0.0, 1.0 - d)
        return (
            int(179 + 34 * light),
            int(111 + 28 * light),
            int(79 + 25 * light),
        )

    draw(test, bbox, pork_tone)
    food_ring(cx, cy, 53, 5, (246, 213, 173), 0.85)
    food_ring(cx, cy, 30, 8, (143, 77, 53), 0.9)
    food_ring(cx - 2, cy - 2, 23, 3, (229, 163, 128), 0.65)
    food_ellipse(cx - 2, cy - 2, 5, 5, (238, 179, 137), 0.75)

    # Small irregular fat seams give the seared pork a layered, cooked surface.
    for offset in (-17, 15):
        food_arc_ring(cx + offset, cy + 2, 12, 3, 195, 335, (246, 196, 159), 0.45)


def draw_egg():
    food_ellipse(400, 472, 54, 45, (126, 67, 39), 0.25)
    food_ellipse(398, 468, 52, 44, (250, 245, 229))
    food_ellipse(401, 469, 26, 26, (255, 151, 42))
    food_ring(401, 469, 24, 4, (220, 107, 22), 0.9)
    food_ellipse(394, 461, 6, 6, (255, 247, 205), 0.96)
    food_ellipse(407, 480, 4, 3, (236, 121, 28), 0.5)


def draw_nori():
    points = [
        (516, 329), (536, 322), (555, 325), (575, 332), (594, 341),
        (607, 350), (603, 373), (600, 397), (603, 427), (585, 438),
        (563, 441), (542, 437), (522, 428), (518, 403), (520, 378),
    ]
    food_polygon(points, (13, 27, 20))
    for a, b in zip(points[:5], points[1:6]):
        food_capsule(a[0], a[1], b[0], b[1], 1.2, (57, 85, 55), 0.65)
    food_capsule(519, 337, 523, 420, 1.3, (65, 92, 59), 0.55)


def draw_onions_and_seeds():
    rng = random.Random(7)
    cx, cy, rx, ry = 512.0, 552.0, 292.0, 252.0
    onions = []
    while len(onions) < 24:
        x = rng.uniform(cx - rx * 0.88, cx + rx * 0.88)
        y = rng.uniform(cy - ry * 0.88, cy + ry * 0.88)
        if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 >= 0.78:
            continue
        if math.hypot(x - 400, y - 468) < 67:
            continue
        if math.hypot(x - 620, y - 480) < 67 or math.hypot(x - 660, y - 560) < 67:
            continue
        onions.append((x, y))

    for i, (x, y) in enumerate(onions):
        radius = rng.uniform(5.5, 8.0)
        if i % 4:
            food_ring(x, y, radius, 3.0, (84, 164, 71), 0.96)
            food_ellipse(x, y, 2, 2, (183, 226, 126), 0.95)
        else:
            food_ellipse(x, y, radius * 0.75, radius * 0.5, (76, 158, 70), 0.95, rng.uniform(-40, 40))
            food_ellipse(x - 1, y - 1, 2, 2, (175, 220, 116), 0.9)

    for _ in range(12):
        for _attempt in range(50):
            x = rng.uniform(cx - 240, cx + 240)
            y = rng.uniform(cy - 190, cy + 190)
            if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 < 0.78:
                break
        r = rng.uniform(2.0, 3.0)
        food_ellipse(x, y, r, r * 0.7, (255, 238, 199), 0.88, rng.uniform(-30, 30))


def draw_chili_oil():
    food_arc_ring(512, 552, 150, 5, 12, 78, (220, 57, 30), 0.76)
    food_ellipse(628, 688, 4, 3, (239, 83, 35), 0.65)


def draw_lifted_noodles():
    # Strands arc up from the broth and tuck between the chopstick tips.
    for strand in range(6):
        offset = (strand - 2.5) * 5.0
        points = []
        for j in range(6):
            t = j / 5
            x = 555 + 25 * t + offset + 3.6 * math.sin(t * math.pi * 2 + strand * 0.7)
            y = 475 - 43 * t
            points.append((x, y))
        for a, b in zip(points, points[1:]):
            fill_capsule(a[0] + 1.5, a[1] + 1.5, b[0] + 1.5, b[1] + 1.5, 5.7, (120, 74, 40), 0.7)
            fill_capsule(a[0], a[1], b[0], b[1], 4.5, (246, 222, 162), 0.97)
            fill_capsule(a[0] - 1, a[1] - 1, b[0] - 1, b[1] - 1, 1.0, (255, 249, 218), 0.55)


def draw_chopsticks():
    dx, dy = 210.0, -195.0
    length = math.hypot(dx, dy)
    px, py = -dy / length * 8.0, dx / length * 8.0
    for offset in (-1, 1):
        x1, y1 = 570 + px * offset, 451 + py * offset
        x2, y2 = 780 + px * offset, 256 + py * offset
        fill_capsule(x1, y1, x2, y2, 9, (190, 139, 78))
        fill_capsule(x1 + 2, y1 - 2, x2 + 2, y2 - 2, 1.4, (236, 193, 126), 0.68)
        t = 0.15
        tx, ty = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        fill_capsule(x1, y1, tx, ty, 8.2, (120, 77, 39))
        fill_capsule(x1 + 1.5, y1 - 1.5, tx + 1.5, ty - 1.5, 1.0, (173, 120, 66), 0.6)


def draw_steam():
    wisps = ((372, 410, -25), (470, 390, 18), (565, 404, -17), (665, 415, 22))
    for index, (base_x, start_y, drift) in enumerate(wisps):
        for step in range(7):
            t = step / 6
            x = base_x + drift * t + 10 * math.sin(t * math.pi * 2 + index)
            y = start_y - 330 * t
            radius = 23 + 4 * math.sin(t * math.pi)
            soft_steam_blob(x, y, radius, radius * 1.35, 0.24 + 0.025 * (step % 2))
    radial_glow_additive(512, 300, 260, (255, 244, 224), 0.06)


def png_chunk(kind, data):
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def write_png(path):
    raw = bytearray()
    stride = WIDTH * 3
    for y in range(HEIGHT):
        raw.append(0)
        start = y * stride
        raw.extend(PIXELS[start:start + stride])
    image = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">2I5B", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + png_chunk(b"IEND", b"")
    )
    with open(path, "wb") as output:
        output.write(image)


def render():
    make_table()

    # A soft grounding shadow separates the lacquer from the wood.
    for i in range(6, 0, -1):
        scale = 1.0 + i * 0.025
        fill_ellipse(518, 575 + i * 2, 400 * scale, 345 * scale, (8, 5, 4), 0.035)

    fill_ellipse(512, 560, 400, 350, (202, 123, 58))
    fill_ellipse(518, 568, 388, 340, (18, 16, 26))
    test, bbox = arc_ring(512, 560, 388, 3, 205, 273)
    draw(test, bbox, (238, 166, 91), 0.65)
    draw_broth()
    draw_steam()
    draw_nori()

    draw_noodle_swirl()
    draw_egg()
    draw_pork(620, 480)
    draw_pork(660, 560)
    draw_onions_and_seeds()
    draw_chili_oil()
    # Keep the lifted strands visible as they tuck under the chopstick tips.
    draw_lifted_noodles()
    draw_chopsticks()

    # A few final broth pinpricks and warm highlights sharpen the glossy surface.
    rng = random.Random(53)
    for _ in range(6):
        x = rng.uniform(350, 690)
        y = rng.uniform(390, 700)
        if ((x - 512) / 292) ** 2 + ((y - 552) / 252) ** 2 < 0.72:
            food_ellipse(x, y, 2.2, 1.5, (255, 235, 187), 0.44)


def main():
    render()
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(output_dir, exist_ok=True)
    write_png(os.path.join(output_dir, "entry.png"))


if __name__ == "__main__":
    main()
