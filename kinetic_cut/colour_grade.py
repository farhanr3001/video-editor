"""Clip primaries shared by the preview shader, native export and compatibility render."""
import math
from functools import lru_cache


WHEELS = (
    ("lift", "Lift", "Shadows and black level"),
    ("gamma", "Gamma", "Midtones and skin"),
    ("gain", "Gain", "Highlights and white level"),
    ("offset", "Offset", "Overall colour and level"),
)

# The four wheels store two positions on the unit disk and a signed level.
# Tone controls store their displayed values, except for percentages.
TONE = (
    ("exposure", "Exposure", -3., 3., 0., .01, " EV"),
    ("temperature", "Temperature", -100., 100., 0., 1., ""),
    ("tint", "Tint", -100., 100., 0., 1., ""),
    ("contrast", "Contrast", .5, 1.75, 1., .01, "×"),
    ("pivot", "Contrast pivot", .15, .85, .5, .01, ""),
    ("saturation", "Saturation", 0., 200., 100., 1., "%"),
)
LUMA = (.2126, .7152, .0722)
PRESETS_KEY = "colour_grade_presets"
PRESET_LIMIT = 200
PRESETS = (
    ("Clean Contrast", {"contrast": 1.12, "pivot": .44, "saturation": 105}),
    ("Warm Film", {"lift": (.14, -.08, .06), "gain": (.23, .18, -.04),
                   "temperature": 14, "contrast": 1.12, "saturation": 87}),
    ("Teal & Amber", {"lift": (-.32, -.23, .01), "gamma": (.16, .05, .02),
                     "gain": (.19, .16, .02), "contrast": 1.15, "saturation": 95}),
    ("Soft Matte", {"lift": (-.05, -.09, .24), "gain": (.09, .1, -.16),
                    "contrast": .89, "saturation": 79}),
    ("Cool Night", {"lift": (-.12, -.25, -.06), "gamma": (-.13, -.2, -.15),
                    "gain": (-.09, -.1, -.08), "contrast": 1.12, "saturation": 76}),
    ("Warm Vintage", {"lift": (.07, -.06, .19), "gamma": (.19, .14, .05),
                      "temperature": 18, "contrast": .95, "saturation": 73}),
    ("Silver Mono", {"saturation": 0, "contrast": 1.24, "pivot": .43, "lift": (0, 0, .06)}),
)


def _number(value, low, high, default):
    try:
        value = float(value)
    except (ValueError, TypeError, OverflowError):
        return default
    return round(min(high, max(low, value)), 5) if math.isfinite(value) else default


def clean(raw):
    """Sparse, bounded and backwards-compatible saved representation."""
    if not isinstance(raw, dict):
        return {}
    grade = {}
    for name, _, _ in WHEELS:
        value = raw.get(name)
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            continue
        x, y, level = (_number(part, -1., 1., 0.) for part in value)
        radius = math.hypot(x, y)
        if radius > 1.00001:
            x, y = round(x / radius, 5), round(y / radius, 5)
        if x or y or level:
            grade[name] = [x, y, level]
    for name, _, low, high, default, _, _ in TONE:
        value = _number(raw.get(name), low, high, default)
        if value != default:
            grade[name] = value
    return grade


def saved_presets(settings):
    records = settings.get(PRESETS_KEY, [])
    if not isinstance(records, list):
        return []
    names = {name.casefold() for name, _ in PRESETS}
    ids = set()
    result = []
    for record in records[:PRESET_LIMIT]:
        if not isinstance(record, dict):
            continue
        name, key, values = (record.get(field) for field in ("name", "id", "values"))
        if not isinstance(name, str) or not isinstance(key, str) or not isinstance(values, dict):
            continue
        name = name.strip()
        if not name or len(name) > 80 or name.casefold() in names or not key or len(key) > 80 or key in ids:
            continue
        names.add(name.casefold())
        ids.add(key)
        result.append(dict(name=name, id=key, values=clean(values)))
    return result


def _wheel(raw, name):
    x, y, level = raw.get(name, (0., 0., 0.))
    vectors = (x, -.5*x + .8660254*y, -.5*x - .8660254*y)
    neutral = sum(weight*value for weight, value in zip(LUMA, vectors))
    return [value - neutral for value in vectors], level


def coefficients(raw):
    """Display-referred RGB primaries. Alpha stays independent of the grade."""
    lift, black = _wheel(raw, "lift")
    gamma, mid = _wheel(raw, "gamma")
    gain, white = _wheel(raw, "gain")
    offset, global_level = _wheel(raw, "offset")
    ev, pivot = raw.get("exposure", 0.), raw.get("pivot", .5)
    contrast = raw.get("contrast", 1.)
    temperature, tint = raw.get("temperature", 0.)/100, raw.get("tint", 0.)/100
    balance = (.36*temperature+.10*tint, -.24*tint, -.36*temperature+.10*tint)
    slopes, biases, powers = [], [], []
    for channel in range(3):
        toe = .20*black + .14*lift[channel]
        scale = 2**(ev + .75*white + .5*gain[channel] + balance[channel])
        slopes.append(contrast * (1-toe) * scale)
        biases.append(contrast*(toe + .22*global_level + .12*offset[channel]) + (1-contrast)*pivot)
        powers.append(2**(-.9*mid - .58*gamma[channel]))
    return tuple(slopes), tuple(biases), tuple(powers), raw.get("saturation", 100.)/100


def apply_rgb(rgb, raw):
    import numpy as np

    slope, bias, power, saturation = coefficients(raw)
    rgb = np.asarray(rgb, dtype=np.float32)
    adjusted = np.power(np.clip(rgb*np.float32(slope)+np.float32(bias), 0, 1), np.float32(power))
    gray = (adjusted*np.float32(LUMA)).sum(axis=-1, keepdims=True)
    return np.clip(gray+(adjusted-gray)*np.float32(saturation), 0, 1)


@lru_cache(maxsize=32)
def _channel_tables(slope, bias, power):
    import numpy as np

    ramp = np.arange(256, dtype=np.float32)[:, None]/255
    return np.power(np.clip(ramp*np.float32(slope)+np.float32(bias), 0, 1), np.float32(power))


def apply_image(image, raw):
    if not raw or image.isNull():
        return image
    import numpy as np
    from PySide6.QtGui import QImage

    source = image.convertToFormat(QImage.Format_RGBA8888)
    pixels = np.frombuffer(source.constBits(), dtype=np.uint8).reshape(source.height(), source.width(), 4)
    slope, bias, power, saturation = coefficients(raw)
    table = _channel_tables(slope, bias, power)
    rgb = table[pixels[..., :3], np.arange(3)]
    gray = (rgb*np.float32(LUMA)).sum(axis=-1, keepdims=True)
    output = pixels.copy()
    output[..., :3] = np.rint(np.clip(gray+(rgb-gray)*saturation, 0, 1)*255).astype(np.uint8)
    return QImage(output.data, source.width(), source.height(), source.bytesPerLine(), QImage.Format_RGBA8888).copy()


def ffmpeg_filter(raw, output_format):
    """16-bit per-channel LUT, then the same RGB saturation matrix as the GPU."""
    slope, bias, power, saturation = coefficients(raw)
    lut = ":".join(f"{c}='maxval*pow(clip(val/maxval*{s:.9f}+({b:.9f}),0,1),{p:.9f})'"
                   for c, s, b, p in zip("rgb", slope, bias, power))
    matrix = ":".join(f"{out}{src}={(saturation if i == j else 0)+(1-saturation)*LUMA[j]:.9f}"
                      for i, out in enumerate("rgb") for j, src in enumerate("rgb"))
    return f"format=gbrap16le,lutrgb={lut},colorchannelmixer={matrix},format={output_format}"


def publish(layer, raw):
    from PySide6.QtGui import QVector4D

    if getattr(layer, "_advanced_grade", None) == raw:
        return
    slope, bias, power, saturation = coefficients(raw)
    layer.setProperty("gradeSlope", QVector4D(*slope, float(bool(raw))))
    layer.setProperty("gradeBias", QVector4D(*bias, 0.))
    layer.setProperty("gradePower", QVector4D(*power, saturation))
    layer._advanced_grade = dict(raw)
