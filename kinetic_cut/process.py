"""Subprocess helpers that keep command-line tools invisible in the desktop app."""
import os
import subprocess
import copy
import shutil
import sys
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=32)
def resolve_tool(command):
    """Bypass known Chocolatey shims: their native children escape Popen flags.

    Explicit custom tools are preserved. Only the installed sibling FFmpeg
    binary for a verified Chocolatey shim is substituted, without executing it.
    """
    if not isinstance(command,str) or os.name!='nt' or Path(command).name.lower() not in {'ffmpeg','ffmpeg.exe','ffprobe','ffprobe.exe'}:return command
    if getattr(sys,'frozen',False) and command.lower() in {'ffmpeg','ffmpeg.exe','ffprobe','ffprobe.exe'}:
        from .icons import resource_path
        bundled=resource_path('assets','tools',Path(command).stem.lower()+'.exe')
        if bundled.is_file():return str(bundled)
    found=shutil.which(command)
    if not found:return command
    path=Path(found)
    if path.parent.name.lower()=='bin' and path.parent.parent.name.lower()=='chocolatey':
        target=path.parent.parent/'lib'/'ffmpeg'/'tools'/'ffmpeg'/'bin'/path.name
        if target.is_file():return str(target)
    return command

def _tool_args(args):
    if isinstance(args,(list,tuple)) and args:
        values=list(args); values[0]=resolve_tool(os.fspath(values[0])); return values
    return args


def _desktop_flags(kwargs):
    if os.name == "nt":
        kwargs["creationflags"] = (kwargs.get("creationflags", 0) & ~getattr(subprocess,"CREATE_NEW_CONSOLE",0x10)) | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        startup = copy.copy(kwargs.get("startupinfo")) if kwargs.get("startupinfo") else subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startup
    return kwargs


def install_desktop_process_policy():
    """Also cover helpers launched by Python dependencies in this desktop process.

    Install before importing media libraries. This does not silence captured error
    output or alter executable arguments, pipes, or unrelated processes.
    """
    if os.name != "nt" or getattr(subprocess.Popen, "_kinetic_hidden", False):
        return
    original = subprocess.Popen
    # Also cover multiprocessing and libraries which cached Popen before us.
    # This is installed by our first PyInstaller runtime hook, before Qt hooks.
    import _winapi
    if not getattr(_winapi.CreateProcess,"_kinetic_hidden",False):
        create_process=_winapi.CreateProcess
        def hidden_create_process(application,command,proc_security,thread_security,inherit,flags,environment,directory,startup):
            values=_desktop_flags({"creationflags":flags,"startupinfo":startup})
            return create_process(application,command,proc_security,thread_security,inherit,values["creationflags"],environment,directory,values["startupinfo"])
        hidden_create_process._kinetic_hidden=True
        _winapi.CreateProcess=hidden_create_process
    import inspect
    signature = inspect.signature(original)
    class DesktopPopen(original):
        _kinetic_hidden = True
        def __init__(self, *args, **kwargs):
            bound = signature.bind_partial(*args, **kwargs)
            if 'args' in bound.arguments:bound.arguments['args']=_tool_args(bound.arguments['args'])
            bound.arguments.update(_desktop_flags({"startupinfo": bound.arguments.get("startupinfo"), "creationflags": bound.arguments.get("creationflags", 0)}))
            super().__init__(*bound.args, **bound.kwargs)
    subprocess.Popen = DesktopPopen


def run(*args, **kwargs):
    if args:args=(_tool_args(args[0]),*args[1:])
    elif 'args' in kwargs:kwargs['args']=_tool_args(kwargs['args'])
    return subprocess.run(*args, **_desktop_flags(kwargs))


def popen(*args, **kwargs):
    if args:args=(_tool_args(args[0]),*args[1:])
    elif 'args' in kwargs:kwargs['args']=_tool_args(kwargs['args'])
    return subprocess.Popen(*args, **_desktop_flags(kwargs))
