"""Prefer shipped baseline weights; own new downloads, reuse legacy caches."""
from pathlib import Path


def device_options(settings):
    """Use supported CUDA when its runtime is present; keep CPU fallback exact."""
    if settings.get('caption_device','auto')=='cpu':return [('cpu','int8',[])]
    handles=[]
    try:
        import ctranslate2
        if not ctranslate2.get_cuda_device_count():return [('cpu','int8',[])]
        if 'float16' not in ctranslate2.get_supported_compute_types('cuda'):return [('cpu','int8',[])]
        import os
        if os.name=='nt':
            import ctypes
            from .config import DATA_DIR
            from .icons import resource_path
            candidates=[resource_path('assets','caption-cuda'),DATA_DIR/'components/ai-enhance-v1/Lib/site-packages/torch/lib']
            for key,value in os.environ.items():
                if key=='CUDA_PATH' or key.startswith('CUDA_PATH_V12'):candidates.append(Path(value)/'bin')
            directory=next((p for p in candidates if (p/'cublas64_12.dll').is_file() and (p/'cublasLt64_12.dll').is_file()),None)
            if directory:
                handles.append(os.add_dll_directory(str(directory)))
                handles.extend(ctypes.WinDLL(str(directory/name)) for name in ('cublasLt64_12.dll','cublas64_12.dll'))
                if (directory/'cudnn64_9.dll').is_file():handles.append(ctypes.WinDLL(str(directory/'cudnn64_9.dll')))
            else:
                handles.extend(ctypes.WinDLL(name) for name in ('cublasLt64_12.dll','cublas64_12.dll'))
        return [('cuda','float16',handles),('cpu','int8',[])]
    except (ImportError,OSError,RuntimeError,ValueError):return [('cpu','int8',[])]


def model_arguments(name):
    from .config import DATA_DIR
    from .icons import resource_path
    bundled = resource_path('assets', 'caption-models', str(name))
    if (bundled / 'model.bin').is_file():
        return str(bundled), {}
    if Path(str(name)).is_dir():
        return str(name), {}
    # Reuse an existing user's model without deleting or modifying the shared cache.
    try:
        from huggingface_hub import snapshot_download
        cached = snapshot_download('Systran/faster-whisper-' + str(name), local_files_only=True)
        if (Path(cached) / 'model.bin').is_file():return cached, {}
    except (OSError, ValueError):
        pass
    return name, {'download_root': str(DATA_DIR / 'models' / 'huggingface')}
