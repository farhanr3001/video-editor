"""Cheap peak analysis for Qt's decoded audio buffers (not a mixdown)."""
import math

import numpy as np
from PySide6.QtMultimedia import QAudioFormat


def channel_peaks(buffer):
    if not buffer.isValid():
        return (0.0, 0.0)
    fmt = buffer.format()
    sample_type = fmt.sampleFormat()
    types = {
        QAudioFormat.Float: (np.float32, 1.0, 0.0),
        QAudioFormat.Int16: (np.int16, 32768.0, 0.0),
        QAudioFormat.Int32: (np.int32, 2147483648.0, 0.0),
        QAudioFormat.UInt8: (np.uint8, 128.0, 128.0),
    }
    if sample_type not in types:
        return (0.0, 0.0)
    dtype, divisor, center = types[sample_type]
    channels = fmt.channelCount()
    if channels < 1:
        return (0.0, 0.0)
    values = np.frombuffer(buffer.constData(), dtype=dtype)
    frames = len(values) // channels
    if not frames:
        return (0.0, 0.0)
    samples = values[:frames * channels].reshape(frames, channels)
    # The small stride reduces work for long decoder buffers, but a full peak
    # scan is required to avoid missing short clipping transients.
    peaks = np.max(np.nan_to_num(np.abs(samples.astype(np.float32) - center), nan=0., posinf=0., neginf=0.), axis=0) / divisor
    left = float(peaks[0])
    right = float(peaks[1]) if channels > 1 else left
    return (left, right)


def peak_db(value):
    return 20.0 * math.log10(max(1e-7, float(value)))
