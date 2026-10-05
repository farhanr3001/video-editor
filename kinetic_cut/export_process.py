"""Bounded render monitoring and Windows child lifetime ownership."""
import os,time,subprocess,tempfile
from pathlib import Path
from .process import popen,run


class ChildJob:
    def __init__(self,process):
        self.handle=None
        if os.name!='nt':return
        import ctypes
        from ctypes import wintypes as w
        class Basic(ctypes.Structure):
            _fields_=[('process_time',ctypes.c_int64),('job_time',ctypes.c_int64),('flags',w.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('process_limit',w.DWORD),('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
        class Extended(ctypes.Structure):
            _fields_=[('basic',Basic),('io',ctypes.c_uint64*6),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        self.api=ctypes.WinDLL('kernel32',use_last_error=True)
        self.api.CreateJobObjectW.restype=w.HANDLE; self.api.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR]
        self.api.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
        self.api.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]; self.api.CloseHandle.argtypes=[w.HANDLE]
        handle=self.api.CreateJobObjectW(None,None); limits=Extended(); limits.basic.flags=0x2000
        if handle and self.api.SetInformationJobObject(handle,9,ctypes.byref(limits),ctypes.sizeof(limits)) and self.api.AssignProcessToJobObject(handle,int(process._handle)):self.handle=handle
        elif handle:self.api.CloseHandle(handle)
    def close(self):
        if self.handle:self.api.CloseHandle(self.handle); self.handle=None


def stop(process,job):
    job.close()
    if process.poll() is None:
        if os.name=='nt':run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=15)
        else:process.kill()
    try:process.wait(timeout=15)
    except subprocess.TimeoutExpired:process.kill()


def render(command,duration,progress=None,cancel=None,stall_timeout=90):
    # Rich curves can exceed Windows' command-line length even on a single clip.
    # Keep the filter graph in a temporary UTF-8 file for the child's lifetime.
    if '-filter_complex' in command and len(subprocess.list2cmdline(command))>28000:
        from .config import CACHE_DIR
        directory=CACHE_DIR/'render-logs'; directory.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='filter-',dir=directory) as temporary:
            graph=Path(temporary)/'graph.txt'; index=command.index('-filter_complex'); graph.write_text(command[index+1],encoding='utf-8')
            command=list(command); command[index:index+2]=['-filter_complex_script',str(graph)]
            return _render(command,duration,progress,cancel,stall_timeout)
    return _render(command,duration,progress,cancel,stall_timeout)

def _render(command,duration,progress=None,cancel=None,stall_timeout=90):
    from .config import CACHE_DIR
    directory=CACHE_DIR/'render-logs'; directory.mkdir(parents=True,exist_ok=True)
    log=directory/(str(time.time_ns())+'.log'); tail=[]; last_frame=-1; rendered=-1.; advanced=time.monotonic(); last_notice=0.; ended=False
    with log.open('wb') as writer,log.open('r',encoding='utf-8',errors='replace') as reader:
        process=popen(command,stdout=writer,stderr=subprocess.STDOUT); job=ChildJob(process)
        try:
            while True:
                for line in reader.readlines():
                    line=line.rstrip(); tail.append(line); tail=tail[-80:]
                    if line.startswith('frame='):
                        try:
                            frame=int(line.partition('=')[2])
                            if frame>last_frame:last_frame=frame; advanced=time.monotonic()
                        except ValueError:pass
                    if line.startswith('out_time_ms='):
                        try:
                            value=int(line.partition('=')[2])/1000000
                            if value>rendered+1e-6:rendered=value; advanced=time.monotonic()
                        except ValueError:pass
                    if line=='progress=end':ended=True
                if cancel and cancel.is_set():raise RuntimeError('Export cancelled. Original media and previous output are unchanged.')
                if process.poll() is not None:break
                now=time.monotonic()
                if now-advanced>stall_timeout:raise RuntimeError(f'Export stopped advancing for {stall_timeout:g} seconds. The encoder was stopped safely. Try CPU encoding.\nLog: {log}')
                if progress and now-last_notice>.5:
                    final=ended or rendered>=duration-2/60
                    progress(min(.99,max(0,rendered)/max(.01,duration)), 'Finalizing video file…' if final else f'Rendering {max(0,rendered):.1f}s / {duration:.1f}s'); last_notice=now
                time.sleep(.1)
            return process.returncode,tail
        finally:
            if process.poll() is None:stop(process,job)
            job.close()
