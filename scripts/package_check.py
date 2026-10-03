"""Launch only our packaged editor, inspect its own window, and close the test."""
import ctypes,subprocess,time,os
from ctypes import wintypes
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ["KINETIC_CUT_HOME"]=str(ROOT/"build"/"sept-packaged-startup")
os.environ["QT_QPA_PLATFORM"]="windows"
user32=ctypes.windll.user32
callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
def text_for(handle):
    size=user32.GetWindowTextLengthW(handle)+1; buf=ctypes.create_unicode_buffer(size); user32.GetWindowTextW(handle,buf,size); return buf.value
def main():
    startup=subprocess.STARTUPINFO(); startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW; startup.wShowWindow=0
    package=Path(os.environ.get("KINETIC_CUT_PACKAGE",ROOT/"dist"/"KineticCut"/"KineticCut.exe"))
    proc=subprocess.Popen([str(package)],startupinfo=startup)
    titles=[]; owned=[]
    @callback
    def child(handle,_):
        value=text_for(handle)
        if value:print("DETAIL:",value,flush=True)
        return True
    @callback
    def window(handle,_):
        pid=wintypes.DWORD(); user32.GetWindowThreadProcessId(handle,ctypes.byref(pid))
        if pid.value==proc.pid:
            title=text_for(handle); titles.append(title); owned.append(handle); print("WINDOW:",title,flush=True)
            if "exception" in title.lower():user32.EnumChildWindows(handle,child,0)
        return True
    # Startup displays a loading window first; wait for the current editor title
    # instead of assuming six seconds or the historical subtitle in its title.
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        titles.clear(); owned.clear(); user32.EnumWindows(window,0)
        if 'Kinetic Cut' in titles or any('exception' in title.lower() for title in titles):break
        if proc.poll() is not None:break
        time.sleep(.5)
    for handle in owned:user32.PostMessageW(handle,0x0010,0,0)
    try:proc.wait(timeout=4)
    except subprocess.TimeoutExpired:proc.terminate(); proc.wait(timeout=4)
    assert 'Kinetic Cut' in titles and not any("exception" in title.lower() for title in titles),titles
    print("PASS packaged editor window",flush=True)
if __name__=="__main__":main()
