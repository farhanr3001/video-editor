"""Explicit native decoder preferences and source-compatible worker selection."""
import os,sys

MODES=('Auto (best preview performance)','Direct3D 11 (hardware)','CPU compatibility')

def configure(settings):
    if sys.platform!='win32':return
    mode=settings.get('playback_decoder',MODES[0])
    # Honor explicit environment overrides used by diagnostics/deployments.
    if mode==MODES[2]:os.environ.setdefault('QT_FFMPEG_DECODING_HW_DEVICE_TYPES',',')
    elif mode==MODES[1]:os.environ.setdefault('QT_FFMPEG_DECODING_HW_DEVICE_TYPES','d3d11va')
    # Native scene-graph composition consumes decoder textures directly. Explicit
    # compatibility mode retains readback; diagnostics may override the backend.
    gpu=os.environ.get('KINETIC_GPU_PREVIEW','1')!='0' and mode!=MODES[2]
    os.environ.setdefault('QT_DISABLE_HW_TEXTURES_CONVERSION','0' if gpu else '1')
    if gpu:
        os.environ.setdefault('QSG_RHI_BACKEND','d3d11')
        os.environ.setdefault('QSG_RENDER_LOOP','threaded')
