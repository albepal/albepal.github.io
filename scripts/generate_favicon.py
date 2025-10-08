#!/usr/bin/env python3
"""Generate custom favicon assets with 'AP' monogram."""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

BG = (0x2E, 0x4E, 0x8A, 255)
FG = (255, 255, 255, 255)


def arc_points(cx, cy, rx, ry, start_deg, end_deg, steps=48):
    start = math.radians(start_deg)
    end = math.radians(end_deg)
    if steps < 2:
        steps = 2
    for i in range(steps + 1):
        t = start + (end - start) * i / steps
        yield (cx + math.cos(t) * rx, cy + math.sin(t) * ry)


A_OUTER = [
    (130, 404),
    (210, 100),
    (226, 100),
    (306, 404),
    (258, 404),
    (232, 302),
    (182, 302),
    (156, 404),
]
A_HOLE = [
    (214, 180),
    (242, 288),
    (190, 288),
]
A_BAR = (180, 250, 252, 292)

# Construct a more traditional bowl for the "P" using arcs
P_OUTER = [
    (316, 404),
    (316, 116),
    (372, 116),
]
P_OUTER += list(arc_points(390, 196, 96, 88, -90, 90, steps=48))
P_OUTER += [
    (362, 284),
    (362, 404),
    (316, 404),
]

P_HOLE = [(336, 164), (372, 164)]
P_HOLE += list(arc_points(384, 194, 70, 62, -90, 90, steps=40))
P_HOLE.append((372, 226))
P_HOLE.append((336, 226))


def clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def scale_points(points, scale):
    return [(x * scale, y * scale) for x, y in points]


def scale_rect(rect, scale):
    x1, y1, x2, y2 = rect
    return (x1 * scale, y1 * scale, x2 * scale, y2 * scale)


def point_in_polygon(x: float, y: float, polygon) -> bool:
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_intersect = (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1
            if x < x_intersect:
                inside = not inside
    return inside


def set_pixel(buf: bytearray, size: int, x: int, y: int, color):
    if not (0 <= x < size and 0 <= y < size):
        return
    idx = (y * size + x) * 4
    buf[idx : idx + 4] = bytes(color)


def fill_rect(buf, size, rect, color):
    x1, y1, x2, y2 = rect
    x_start = clamp(int(math.floor(x1)), 0, size)
    x_end = clamp(int(math.ceil(x2)), 0, size)
    y_start = clamp(int(math.floor(y1)), 0, size)
    y_end = clamp(int(math.ceil(y2)), 0, size)
    if x_end <= x_start:
        x_end = clamp(x_start + 1, 0, size)
    if y_end <= y_start:
        y_end = clamp(y_start + 1, 0, size)
    row = bytes(color)
    for y in range(y_start, y_end):
        offset = (y * size + x_start) * 4
        for x in range(x_start, x_end):
            buf[offset : offset + 4] = row
            offset += 4


def fill_polygon(buf, size, polygon, color):
    xs = [pt[0] for pt in polygon]
    ys = [pt[1] for pt in polygon]
    x_start = clamp(int(math.floor(min(xs))), 0, size)
    x_end = clamp(int(math.ceil(max(xs))), 0, size)
    y_start = clamp(int(math.floor(min(ys))), 0, size)
    y_end = clamp(int(math.ceil(max(ys))), 0, size)
    if x_end <= x_start or y_end <= y_start:
        return
    for y in range(y_start, y_end):
        yy = y + 0.5
        for x in range(x_start, x_end):
            xx = x + 0.5
            if point_in_polygon(xx, yy, polygon):
                set_pixel(buf, size, x, y, color)


def make_png(size: int) -> bytes:
    buf = bytearray(BG * size * size)
    scale = size / 512.0

    # Letter A
    fill_polygon(buf, size, scale_points(A_OUTER, scale), FG)
    fill_polygon(buf, size, scale_points(A_HOLE, scale), BG)
    fill_rect(buf, size, scale_rect(A_BAR, scale), FG)

    # Letter P
    fill_polygon(buf, size, scale_points(P_OUTER, scale), FG)
    fill_polygon(buf, size, scale_points(P_HOLE, scale), BG)

    # encode PNG
    stride = size * 4
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter type 0
        row_start = y * stride
        raw.extend(buf[row_start : row_start + stride])

    compressed = zlib.compress(bytes(raw), 9)

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return (
            struct.pack("!I", len(data))
            + chunk_type
            + data
            + struct.pack("!I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack("!IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(chunk(b"IHDR", ihdr))
    png.extend(chunk(b"IDAT", compressed))
    png.extend(chunk(b"IEND", b""))
    return bytes(png)


def write_png(path: Path, size: int):
    data = make_png(size)
    path.write_bytes(data)
    return data


def write_ico(path: Path, png_data: bytes, size: int):
    # ICO header for single PNG-based icon
    reserved = 0
    icon_type = 1
    count = 1
    header = struct.pack("<HHH", reserved, icon_type, count)
    width = size if size < 256 else 0
    height = size if size < 256 else 0
    color_count = 0
    reserved_byte = 0
    planes = 0
    bitcount = 0
    image_size = len(png_data)
    offset = 6 + 16
    entry = struct.pack(
        "<BBBBHHII",
        width,
        height,
        color_count,
        reserved_byte,
        planes,
        bitcount,
        image_size,
        offset,
    )
    path.write_bytes(header + entry + png_data)


def main():
    out_dir = Path(__file__).resolve().parents[1] / "images"
    out_dir.mkdir(parents=True, exist_ok=True)

    png32 = write_png(out_dir / "favicon-32x32.png", 32)
    png192 = write_png(out_dir / "favicon-192x192.png", 192)
    png512 = write_png(out_dir / "favicon-512x512.png", 512)

    write_ico(out_dir / "favicon.ico", png32, 32)

    print("Generated favicon assets:")
    for size, data in ((32, png32), (192, png192), (512, png512)):
        print(f"  {size}x{size} -> {len(data)} bytes")


if __name__ == "__main__":
    main()
