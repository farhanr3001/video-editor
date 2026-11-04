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


# Hugging Face repositories faster-whisper uses for named models.
REPOSITORIES = {'large-v3-turbo': 'mobiuslabsgmbh/faster-whisper-large-v3-turbo'}
CHOICES = ('tiny.en', 'base.en', 'small.en', 'large-v3-turbo')
DOWNLOAD_SIZES = {'tiny.en': 75, 'base.en': 145, 'small.en': 480, 'large-v3-turbo': 1620}  # MB, approximate


def repository(name):
    return REPOSITORIES.get(str(name), 'Systran/faster-whisper-' + str(name))


def is_model_folder(path):
    try:
        folder = Path(str(path))
        return folder.is_dir() and (folder / 'model.bin').is_file() and (folder / 'config.json').is_file()
    except (OSError, ValueError):
        return False


def local_model(name):
    """Path of an already-available model (bundled, folder, own download or shared cache), else ''."""
    from .config import DATA_DIR
    from .icons import resource_path
    bundled = resource_path('assets', 'caption-models', str(name))
    if (bundled / 'model.bin').is_file():
        return str(bundled)
    if is_model_folder(name):
        return str(name)
    own = app_copy_path(name)
    if own:
        return own
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        return ''
    for cache_dir in (DATA_DIR / 'models' / 'huggingface', None):
        try:
            options = dict(local_files_only=True)
            if cache_dir is not None: options['cache_dir'] = str(cache_dir)
            cached = snapshot_download(repository(name), **options)
            if (Path(cached) / 'model.bin').is_file():
                return cached
        except Exception:
            pass
    return ''


def model_status(name):
    """('ready', path) when usable offline, ('download', MB) when a first run must download it, ('missing', '') for a bad folder."""
    found = local_model(name)
    if found:
        return 'ready', found
    if str(name) in DOWNLOAD_SIZES:
        return 'download', DOWNLOAD_SIZES[str(name)]
    return 'missing', ''


def model_arguments(name):
    from .config import DATA_DIR
    found = local_model(name)
    if found:
        return found, {}
    if Path(str(name)).is_absolute() or '/' in str(name) or '\\' in str(name):
        raise FileNotFoundError(f'Speech model folder not found or incomplete: {name}. Choose another model in Settings > Advanced.')
    return str(name), {'download_root': str(DATA_DIR / 'models' / 'huggingface')}


# --- Optional speech-model download (Optional downloads dialog) ---------------
OPTIONAL_MODEL = 'large-v3-turbo'
_WEIGHT_FILES = ['config.json', 'preprocessor_config.json', 'model.bin', 'tokenizer.json', 'vocabulary.*']


def app_model_root(name=OPTIONAL_MODEL):
    from .config import DATA_DIR
    return DATA_DIR / 'models' / 'huggingface' / ('models--' + repository(name).replace('/', '--'))


def app_copy_path(name=OPTIONAL_MODEL):
    """Folder of this app's own complete downloaded copy, else ''."""
    try:
        return next((str(f) for f in sorted((app_model_root(name) / 'snapshots').iterdir()) if is_model_folder(f)), '')
    except OSError:
        return ''


def app_copy_ready(name=OPTIONAL_MODEL):
    """True when this app's own downloaded copy is complete (other locations do not count)."""
    return bool(app_copy_path(name))


def install_model(progress, cancel, name=OPTIONAL_MODEL):
    """Download the model into the app's own model folder with byte progress and cancel."""
    import shutil
    from .config import DATA_DIR
    if app_copy_ready(name):
        progress((100, 'Already installed'))
        return str(app_model_root(name))
    cache = DATA_DIR / 'models' / 'huggingface'
    cache.mkdir(parents=True, exist_ok=True)
    needed = int(DOWNLOAD_SIZES[name] * 1.3 * 1024 ** 2)
    if shutil.disk_usage(cache).free < needed:
        raise RuntimeError('Not enough free disk space for the speech model.')
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import tqdm as hub_tqdm

    class Bar(hub_tqdm):
        def update(self, n=1):
            if cancel.is_set():
                raise InterruptedError('Speech model download cancelled')
            result = super().update(n)
            if getattr(self, 'unit', '') == 'B' and self.total and self.total > 1_000_000:
                progress((min(98, int(self.n / self.total * 98)), 'Downloading speech model ' + name))
            return result

    progress((1, 'Connecting to download ' + name))
    try:
        snapshot_download(repository(name), cache_dir=str(cache), allow_patterns=_WEIGHT_FILES, tqdm_class=Bar)
    except InterruptedError:
        raise
    except Exception as error:
        raise RuntimeError('Could not download the speech model. Check your internet connection and try again. (' + str(error)[:160] + ')') from error
    if cancel.is_set():
        raise InterruptedError('Speech model download cancelled')
    if not app_copy_ready(name):
        raise RuntimeError('The speech model download was incomplete. Please try again.')
    progress((100, name + ' ready'))
    return str(app_model_root(name))


def remove_model(name=OPTIONAL_MODEL):
    """Delete only this app's downloaded copy; never a custom folder or another program's cache."""
    import shutil
    from .config import DATA_DIR
    root = app_model_root(name)
    base = (DATA_DIR / 'models' / 'huggingface').resolve()
    if root.is_symlink() or root.resolve().parent != base:
        raise ValueError('Unsafe speech model storage path')
    if root.exists():
        shutil.rmtree(root)
