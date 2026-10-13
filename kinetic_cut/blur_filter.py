"""Bounded full-resolution Gaussian filtering; no Qt frames or decoder state."""
import math
import os
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageFilter

# Native Pillow filtering releases the GIL. A fixed shared pool avoids creating
# threads per frame; callers wait for their own image only. Each task owns a crop.
_POOL = ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1),
                           thread_name_prefix="kinetic-blur")


def gaussian(image, radius, region=None):
    halo = math.ceil(max(0., radius) * 6) + 6
    if region is not None:
        left, top, right, bottom = region
        left, top = max(0, left), max(0, top)
        right, bottom = min(image.width, right), min(image.height, bottom)
        if right > left and bottom > top:
            start_x, start_y = max(0, left-halo), max(0, top-halo)
            end_x, end_y = min(image.width, right+halo), min(image.height, bottom+halo)
            piece = image.crop((start_x, start_y, end_x, end_y))
            filtered = piece.filter(ImageFilter.GaussianBlur(radius))
            result = image.copy()
            result.paste(filtered.crop((left-start_x, top-start_y, right-start_x, bottom-start_y)), (left, top))
            return result
    count = min(4, os.cpu_count() or 1, image.height // 256)
    if count < 2 or image.width * image.height < 900_000 or halo > image.height // 8:
        return image.filter(ImageFilter.GaussianBlur(radius))

    def stripe(bounds):
        top, bottom = bounds
        start, end = max(0, top - halo), min(image.height, bottom + halo)
        piece = image.crop((0, start, image.width, end))
        filtered = piece.filter(ImageFilter.GaussianBlur(radius))
        return top, filtered.crop((0, top - start, image.width, bottom - start))

    # Six sigma of overlap exceeds the support of Pillow's three box passes.
    # Internal strip edges never participate in the visible result. Exterior
    # border padding is supplied by the caller exactly as before.
    bounds = [(n * image.height // count, (n + 1) * image.height // count)
              for n in range(count)]
    futures = [_POOL.submit(stripe, pair) for pair in bounds]
    parts, error = [], None
    for future in futures:
        try:
            parts.append(future.result())
        except Exception as exc:
            if error is None: error = exc
    if error is not None: raise error
    result = Image.new(image.mode, image.size)
    for top, piece in parts:
        result.paste(piece, (0, top))
    return result
