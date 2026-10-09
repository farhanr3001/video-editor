"""Bounded source sampling for large, axis-aligned export layers."""
import math


def visible_source(source_width, source_height, layer_width, layer_height,
                   centre_x, centre_y, frame_width, frame_height):
    """Return crop/scale/centre preserving the layer's original placement.

    Crop invisible source pixels before enlarging them. Two source pixels of
    overscan keep the scaling kernel away from the visible boundary. YUV crops
    and output dimensions are even; centre offsets compensate their rounding.
    None means there is no visible intersection (or an unsuitable tiny source).
    """
    left = centre_x - layer_width / 2
    top = centre_y - layer_height / 2
    if left >= frame_width or top >= frame_height or left + layer_width <= 0 or top + layer_height <= 0:
        return None
    if source_width < 4 or source_height < 4:
        return None
    def axis(source, size, offset, frame):
        start = max(0, 2 * math.floor((max(0, -offset) * source / size - 2) / 2))
        end = min(source - source % 2, 2 * math.ceil((min(size, frame - offset) * source / size + 2) / 2))
        length = end - start
        if length <= 0:
            return None
        scaled = max(2, 2 * round(length * size / source / 2))
        centre = offset + start * size / source + scaled / 2
        return start, length, scaled, centre
    horizontal = axis(source_width, layer_width, left, frame_width)
    vertical = axis(source_height, layer_height, top, frame_height)
    if not horizontal or not vertical:
        return None
    x, w, scaled_w, cx = horizontal
    y, h, scaled_h, cy = vertical
    return x, y, w, h, scaled_w, scaled_h, cx, cy
