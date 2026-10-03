"""Seekable media input that permits Windows Explorer rename/recycle operations."""
import os
from PySide6.QtCore import QFile, QIODevice, QUrl


def open_shared_media(path,parent=None):
    """Adopt a read-only Windows handle with READ/WRITE/DELETE sharing in Qt."""
    import ctypes
    import msvcrt
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    create=kernel.CreateFileW
    create.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,
                     wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    create.restype=wintypes.HANDLE
    handle=create(os.path.abspath(path),0x80000000,0x1|0x2|0x4,None,3,0x80,None)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:fd=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY)
    except Exception:
        close=kernel.CloseHandle; close.argtypes=[wintypes.HANDLE]; close(handle); raise
    device=QFile(parent)
    if not device.open(fd,QIODevice.ReadOnly,QFile.AutoCloseHandle):
        os.close(fd); device.deleteLater(); raise OSError(device.errorString())
    return device


def set_media_source(player,url):
    """Keep the device player-owned until Qt has retired its decoder threads."""
    previous=getattr(player,'_shared_media_device',None)
    if os.name=='nt' and url.isLocalFile():
        try:device=open_shared_media(url.toLocalFile(),player)
        except OSError:
            # Let Qt publish its usual missing/unreadable-media status.
            player.setSource(url); device=None
        else:player.setSourceDevice(device,url)
        player._shared_media_device=device
    else:
        player.setSource(url); player._shared_media_device=None
    if previous:previous.deleteLater()
