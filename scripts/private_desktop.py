"""Run a native diagnostic on a private non-input desktop, never the owner's screen."""
import ctypes,json,os,subprocess,time
from pathlib import Path
from ctypes import wintypes as W

def run(args,log,cwd,timeout=600):
    if os.name!='nt':raise RuntimeError('Native desktop checks require Windows')
    import win32process,win32event,win32file,win32con,pywintypes
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.CreateDesktopW.argtypes=[W.LPCWSTR,W.LPCWSTR,ctypes.c_void_p,W.DWORD,W.DWORD,ctypes.c_void_p];user.CreateDesktopW.restype=W.HANDLE;user.CloseDesktop.argtypes=[W.HANDLE]
    name='KineticVerify'+str(os.getpid())+str(time.time_ns());desktop=user.CreateDesktopW(name,None,None,0,0xcf,None)
    if not desktop:raise ctypes.WinError(ctypes.get_last_error())
    security=pywintypes.SECURITY_ATTRIBUTES();security.bInheritHandle=True
    log=Path(log);log.parent.mkdir(parents=True,exist_ok=True)
    output=win32file.CreateFile(str(log),win32con.GENERIC_WRITE,win32con.FILE_SHARE_READ,security,win32con.CREATE_ALWAYS,0,None)
    null=win32file.CreateFile('NUL',win32con.GENERIC_READ,win32con.FILE_SHARE_READ|win32con.FILE_SHARE_WRITE,security,win32con.OPEN_EXISTING,0,None)
    info=win32process.STARTUPINFO();info.lpDesktop='Winsta0\\'+name;info.dwFlags=win32con.STARTF_USESTDHANDLES;info.hStdInput=null;info.hStdOutput=output;info.hStdError=output
    env=dict(os.environ,KINETIC_DIAGNOSTIC_PRIVATE_DESKTOP='1')
    try:
        process,thread,pid,tid=win32process.CreateProcess(str(Path(args[0]).resolve()),subprocess.list2cmdline([str(a) for a in args]),None,None,True,win32con.CREATE_NO_WINDOW,env,str(cwd),info);thread.Close()
        try:
            if win32event.WaitForSingleObject(process,int(timeout*1000))!=win32con.WAIT_OBJECT_0:
                import psutil
                for child in reversed(psutil.Process(pid).children(recursive=True)):
                    try:child.terminate()
                    except psutil.Error:pass
                win32process.TerminateProcess(process,124);raise TimeoutError('Native check exceeded its deadline')
            return win32process.GetExitCodeProcess(process)
        finally:process.Close()
    finally:output.Close();null.Close();user.CloseDesktop(desktop)
