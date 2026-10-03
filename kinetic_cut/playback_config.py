"""Explicit decoder preferences; composition remains the CPU QWidget renderer."""
import os,sys

MODES=('Auto (hardware preferred)','Direct3D 11 (hardware)','CPU compatibility')

def configure(settings):
    if sys.platform!='win32':return
    mode=settings.get('playback_decoder',MODES[0])
    # Honor explicit environment overrides used by diagnostics/deployments.
    if mode==MODES[2]:os.environ.setdefault('QT_FFMPEG_DECODING_HW_DEVICE_TYPES',',')
    elif mode==MODES[1]:os.environ.setdefault('QT_FFMPEG_DECODING_HW_DEVICE_TYPES','d3d11va')
    # CPU composition needs a readback. Keep the safer software colour conversion
    # while permitting hardware decoding; these are separate operations.
    os.environ.setdefault('QT_DISABLE_HW_TEXTURES_CONVERSION','1')
