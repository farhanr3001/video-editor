"""Prepare only verified application files; bootstrap with FullSetup if the helper is damaged."""
import json,uuid
from pathlib import Path
from . import updates,update_files as files

def prepare(root,cancel,progress=lambda *_:None):
    from .config import CACHE_DIR
    root=Path(root);release=updates.repair_release()
    selection=files.plan(root,release.manifest,cancel,repair=True)
    inventory='\n'.join([*sorted(release.manifest['files']),files.MANIFEST,files.INVENTORY])+'\n'
    try:
        local=files.validate_manifest(json.loads((root/files.MANIFEST).read_text()))
        metadata_ok=local==release.manifest and (root/files.INVENTORY).read_text()==inventory
        helper_ok=files.digest(root/'KineticCutUpdater.exe',cancel)==local['files']['KineticCutUpdater.exe']['sha256']
        local_exe_ok=files.digest(root/'KineticCut.exe',cancel)==local['files']['KineticCut.exe']['sha256']
    except (OSError,ValueError,KeyError):metadata_ok=helper_ok=False
    if helper_ok and local_exe_ok and local['files']['KineticCut.exe']['sha256']!=release.manifest['files']['KineticCut.exe']['sha256']:
        return dict(unpublished=True)
    if not selection['changed'] and not selection['removed'] and metadata_ok:return None
    if not helper_ok:
        installer=updates.repair_installer()
        path=updates.download(installer,CACHE_DIR/'updates',cancel,lambda done,total:progress(round(done/total*100),'Preparing repair files…'))
        return dict(path=path,incremental=False)
    directory=CACHE_DIR/'updates'/('repair-'+uuid.uuid4().hex)
    path=files.stage_update(root,release.manifest,selection,directory,cancel,progress,download_cache=CACHE_DIR/'updates/payloads')
    return dict(path=path,incremental=True)
