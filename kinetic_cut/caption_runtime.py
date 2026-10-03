"""Prefer shipped baseline weights; own new downloads, reuse legacy caches."""
from pathlib import Path


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
